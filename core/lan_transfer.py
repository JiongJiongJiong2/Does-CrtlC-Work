"""Explicit, paired UDP text transfer. Receiving never touches the clipboard."""

from dataclasses import dataclass
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QUdpSocket

from core.transfer_protocol import (EncryptedCodec, FUTURE_SKEW_SECONDS,
                                    MAX_PACKET_BYTES, ProtocolError, TTL_SECONDS,
                                    Peer, new_message_id, new_pairing_key, packet_key_id,
                                    peer_address)


@dataclass
class _Pending:
    peer: Peer
    codec: EncryptedCodec
    packet: bytes
    timer: QTimer
    attempts: int = 0


class LanTransfer(QObject):
    received = Signal(str, str, str)
    delivered = Signal(str, str)
    failed = Signal(str, str)
    status = Signal(str)

    def __init__(self, parent=None, *, retry_ms=800, max_attempts=3, replay_limit=1024):
        super().__init__(parent)
        if not 1 <= max_attempts <= 3 or retry_ms < 1 or replay_limit < 1:
            raise ValueError('Invalid transfer limits')
        self._retry_ms, self._max_attempts = retry_ms, max_attempts
        self._replay_limit = replay_limit
        self._socket = QUdpSocket(self)
        self._socket.readyRead.connect(self._read_pending)
        self._listening = False
        self._peers = {}
        self._pending = {}
        self._seen = {}
        self._sent = {}
        self._epoch = 0

    @property
    def is_listening(self):
        return self._listening

    @property
    def local_port(self):
        return int(self._socket.localPort())

    def configure_peers(self, peers):
        configured = {}
        names = set()
        for peer in peers:
            if not isinstance(peer, Peer):
                raise ValueError('Expected Peer records')
            codec = EncryptedCodec(peer.key)
            if codec.key_id in configured or peer.name in names:
                raise ValueError('Each peer needs a distinct name and pairing key')
            configured[codec.key_id] = (peer, codec)
            names.add(peer.name)
        changed = configured.keys() != self._peers.keys() or any(
            entry[0] != self._peers[key][0] for key, entry in configured.items())
        self._peers = configured
        if changed:
            self._epoch += 1
            self._cancel_pending('Peer configuration changed')

    def listen(self, port=45873, host='0.0.0.0'):
        try:
            peer_address(host, bind=True)
            if type(port) is not int or not 0 <= port <= 65535:
                raise ValueError('Invalid listening port')
        except ValueError as error:
            self.status.emit(str(error))
            return False
        self.stop()
        if not self._socket.bind(QHostAddress(host), port, QAbstractSocket.DontShareAddress):
            self.status.emit('Unable to listen on the selected address and port')
            return False
        self._listening = True
        self.status.emit(f'Listening on UDP port {self.local_port}')
        return True

    def stop(self):
        self._epoch += 1
        self._listening = False
        self._socket.close()
        self._cancel_pending('Transfer stopped')
        # Keep bounded replay entries across a stop/start of the same instance.
        self.status.emit('Receiving stopped')

    def send_text(self, peer, text):
        message_id = new_message_id()
        try:
            if not isinstance(peer, Peer):
                raise ValueError('Select a configured peer')
            codec = EncryptedCodec(peer.key)
            if codec.key_id not in self._peers or self._peers[codec.key_id][0] != peer:
                raise ValueError('Select a configured peer')
            for old_id, pending in tuple(self._pending.items()):
                if pending.codec.key_id == codec.key_id:
                    self._finish(old_id, reason='Superseded by a new send')
            packet = codec.encode(dict(v=1, kind='text', id=message_id,
                                       ts=int(time.time()), text=text))
            self._prune_replays()
            if len(self._sent) >= self._replay_limit:
                raise ValueError('Send budget is full; wait for earlier messages to expire')
            if self._socket.state() == QAbstractSocket.UnconnectedState:
                address = QHostAddress.AnyIPv4 if peer_address(peer.host).version == 4 else QHostAddress.AnyIPv6
                if not self._socket.bind(address, 0, QAbstractSocket.DontShareAddress):
                    raise ValueError('Unable to open a temporary acknowledgement port')
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._transmit(message_id))
            self._sent[(codec.key_id, message_id)] = time.monotonic() + TTL_SECONDS + FUTURE_SKEW_SECONDS
            self._pending[message_id] = _Pending(peer, codec, packet, timer)
            # Delay the initial send so callers can register the returned ID.
            timer.start(0)
        except (ValueError, UnicodeError) as error:
            reason = str(error)
            QTimer.singleShot(0, lambda: self.failed.emit(message_id, reason))
        return message_id

    def _transmit(self, message_id):
        pending = self._pending.get(message_id)
        if pending is None:
            return
        if pending.attempts >= self._max_attempts:
            self._finish(message_id, reason='No authenticated acknowledgement received')
            return
        pending.attempts += 1
        count = self._socket.writeDatagram(pending.packet, QHostAddress(pending.peer.host), pending.peer.port)
        if count != len(pending.packet):
            self._finish(message_id, reason='Unable to send the datagram')
            return
        pending.timer.start(self._retry_ms)

    def _read_pending(self):
        for _ in range(64):
            if not self._socket.hasPendingDatagrams():
                return
            if self._socket.pendingDatagramSize() > MAX_PACKET_BYTES:
                self._socket.receiveDatagram(0)
                continue
            datagram = self._socket.receiveDatagram(MAX_PACKET_BYTES)
            packet = bytes(datagram.data())
            try:
                key_id = packet_key_id(packet)
                peer, codec = self._peers[key_id]
                payload = codec.decode(packet)
            except (ProtocolError, KeyError):
                continue
            source = datagram.senderAddress()
            if not source.isEqual(QHostAddress(peer.host), QHostAddress.ConvertV4MappedToIPv4):
                continue
            message_id = payload['id']
            if payload['kind'] == 'ack':
                pending = self._pending.get(message_id)
                if (pending and pending.codec.key_id == key_id and
                        datagram.senderPort() == pending.peer.port):
                    self._finish(message_id)
            elif self._listening:
                self._receive_text(peer, codec, payload, source, datagram.senderPort())
        if self._socket.hasPendingDatagrams():
            QTimer.singleShot(0, self._read_pending)

    def _receive_text(self, peer, codec, payload, source, port):
        self._prune_replays()
        now = time.monotonic()
        identity = (codec.key_id, payload['id'])
        if identity in self._sent:
            return  # An authenticated reflection of our own ciphertext is not a new message.
        epoch = self._epoch
        if identity not in self._seen:
            # Never evict a live ID: otherwise a burst could make replays valid.
            if len(self._seen) >= self._replay_limit:
                return
            self._seen[identity] = now + TTL_SECONDS + FUTURE_SKEW_SECONDS
            self.received.emit(peer.name, payload['text'], payload['id'])
        if (self._listening and epoch == self._epoch and
                self._socket.state() == QAbstractSocket.BoundState):
            ack = codec.encode(dict(v=1, kind='ack', id=payload['id'], ts=int(time.time())))
            self._socket.writeDatagram(ack, source, port)

    def _finish(self, message_id, reason=None):
        pending = self._pending.pop(message_id, None)
        if pending is None:
            return
        pending.timer.stop()
        pending.timer.deleteLater()
        if reason is None:
            self.delivered.emit(message_id, pending.peer.name)
        else:
            self.failed.emit(message_id, reason)
        if not self._listening and not self._pending:
            self._socket.close()

    def _cancel_pending(self, reason):
        for message_id in tuple(self._pending):
            self._finish(message_id, reason)

    def cancel_pending(self):
        """UI calls this when edited input invalidates previously queued sends."""
        self._cancel_pending('Send input changed')

    def _prune_replays(self):
        now = time.monotonic()
        self._seen = {key: expiry for key, expiry in self._seen.items() if expiry > now}
        self._sent = {key: expiry for key, expiry in self._sent.items() if expiry > now}
