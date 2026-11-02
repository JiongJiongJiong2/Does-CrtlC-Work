"""Experimental BLE central adapter. Requires a matching foreground peripheral.

Qt cannot host the peripheral role on Windows. This module never scans until
scan() is called, does not infer direction from RSSI, and never writes clipboard.
"""

from collections import OrderedDict, deque
import secrets
import struct
import time

from PySide6.QtCore import QByteArray, QObject, QTimer, Signal
from PySide6.QtBluetooth import (QBluetoothDeviceDiscoveryAgent, QBluetoothDeviceInfo,
    QBluetoothUuid, QLowEnergyCharacteristic, QLowEnergyController, QLowEnergyService)

from core.transfer_protocol import EncryptedCodec, MAX_PACKET_BYTES, ProtocolError, TTL_SECONDS, new_message_id
from core.nearby_peers import SERVICE_UUID

WRITE_UUID = 'b7d0ca11-4d11-4e7d-901c-6e66b55f4800'
NOTIFY_UUID = 'b7d0ca12-4d11-4e7d-901c-6e66b55f4800'
_HEADER = struct.Struct('!4sIHH')


def fragment_packet(packet, value_size=20, token=None):
    if not 1 <= len(packet) <= MAX_PACKET_BYTES or not 20 <= value_size <= 512:
        raise ProtocolError('invalid BLE packet/value size')
    token = secrets.randbits(32) if token is None else token
    width = value_size - _HEADER.size
    count = (len(packet) + width - 1) // width
    return [_HEADER.pack(b'DCF1', token, index, count) + packet[index * width:(index + 1) * width]
            for index in range(count)]


class FragmentAssembler:
    """Bound both incomplete messages and bytes, accepting out-of-order fragments."""

    def __init__(self):
        self._pending = OrderedDict()

    def feed(self, frame, now=None):
        now = time.monotonic() if now is None else now
        for token, record in tuple(self._pending.items()):
            if now - record[0] > 30:
                del self._pending[token]
        if not _HEADER.size < len(frame) <= 512:
            raise ProtocolError('invalid BLE fragment size')
        magic, token, index, count = _HEADER.unpack(frame[:_HEADER.size])
        if magic != b'DCF1' or not 1 <= count <= 1024 or not 0 <= index < count:
            raise ProtocolError('invalid BLE fragment header')
        if token not in self._pending:
            if len(self._pending) >= 4:
                self._pending.popitem(last=False)
            self._pending[token] = (now, count, {})
        started, expected, parts = self._pending[token]
        data = frame[_HEADER.size:]
        if count != expected or (index in parts and parts[index] != data):
            del self._pending[token]
            raise ProtocolError('conflicting BLE fragments')
        parts[index] = data
        if sum(map(len, parts.values())) > MAX_PACKET_BYTES:
            del self._pending[token]
            raise ProtocolError('BLE packet exceeds budget')
        if len(parts) == expected:
            del self._pending[token]
            return b''.join(parts[i] for i in range(expected))
        return None


class BleTextClient(QObject):
    discovered = Signal(str, str, int)  # opaque scan ID, name, RSSI (not direction)
    scan_finished = Signal()
    status = Signal(str)
    ready = Signal()
    received = Signal(str, str)  # text, message ID
    delivered = Signal(str)
    failed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._agent = None
        self._devices = {}
        self._controller = self._service = self._codec = None
        self._generation = 0
        self._ready = False
        self._queue = deque()
        self._inflight = None
        self._pending_id = None
        self._seen = OrderedDict()
        self._sent_ids = OrderedDict()
        self._assembler = FragmentAssembler()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._abort('BLE operation timed out'))
        self._write_timer = QTimer(self)
        self._write_timer.setSingleShot(True)
        self._write_timer.timeout.connect(lambda: self._abort('BLE characteristic write timed out'))

    def scan(self):
        previous_generation = self._generation
        self.stop()
        if self._generation != previous_generation + 1:
            return  # A cancellation callback started a newer operation.
        self._devices.clear()
        self._agent = QBluetoothDeviceDiscoveryAgent(self)
        agent = self._agent
        generation = self._generation
        self._agent.setLowEnergyDiscoveryTimeout(6000)
        self._agent.deviceDiscovered.connect(lambda info: self._found(info)
                                            if generation == self._generation else None)
        self._agent.finished.connect(lambda: self.scan_finished.emit()
                                     if generation == self._generation else None)
        self._agent.errorOccurred.connect(lambda _: self.status.emit(agent.errorString())
                                         if generation == self._generation else None)
        self.status.emit('正在扫描 BLE；信号强弱不代表设备方向')
        if generation == self._generation and self._agent is agent:
            agent.start(QBluetoothDeviceDiscoveryAgent.LowEnergyMethod)

    def _found(self, info):
        if not info.coreConfigurations() & QBluetoothDeviceInfo.LowEnergyCoreConfiguration:
            return
        identity = info.address().toString() if not info.address().isNull() else info.deviceUuid().toString()
        self._devices[identity] = info
        self.discovered.emit(identity, info.name() or 'BLE device', info.rssi())

    def connect_device(self, scan_id, key):
        if scan_id not in self._devices:
            raise ValueError('Select a device from the current scan')
        info = self._devices[scan_id]
        codec = EncryptedCodec(key)
        previous_generation = self._generation
        self.stop()
        if self._generation != previous_generation + 1:
            return
        self._codec = codec
        self._controller = QLowEnergyController.createCentral(info, self)
        controller = self._controller
        generation = self._generation

        def wire(signal, callback):
            signal.connect(lambda *args: callback(*args) if generation == self._generation else None)

        wire(self._controller.connected, self._controller.discoverServices)
        wire(self._controller.discoveryFinished, self._services_found)
        wire(self._controller.disconnected, lambda: self._abort('BLE disconnected'))
        wire(self._controller.errorOccurred, lambda _: self._abort('BLE connection error'))
        self._timer.start(15000)
        self.status.emit('正在连接约定的文本服务')
        if generation == self._generation and self._controller is controller:
            controller.connectToDevice()

    def _services_found(self):
        self._service = self._controller.createServiceObject(QBluetoothUuid(SERVICE_UUID), self)
        if self._service is None:
            self._abort('目标没有 DoseCtrlC 文本服务；需要配套接收端')
            return
        generation = self._generation
        for signal, callback in (
            (self._service.stateChanged, self._details_ready),
            (self._service.descriptorWritten, self._subscribed),
            (self._service.characteristicWritten, self._written),
            (self._service.characteristicChanged, self._notification),
            (self._service.errorOccurred, lambda _: self._abort('BLE service error'))):
            signal.connect(lambda *args, cb=callback: cb(*args) if generation == self._generation else None)
        self._service.discoverDetails()

    def _details_ready(self, state):
        if state != QLowEnergyService.RemoteServiceDiscovered:
            return
        self._write = self._service.characteristic(QBluetoothUuid(WRITE_UUID))
        self._notify = self._service.characteristic(QBluetoothUuid(NOTIFY_UUID))
        if (not self._write.isValid() or not self._notify.isValid() or
                not self._write.properties() & QLowEnergyCharacteristic.Write or
                not self._notify.properties() & QLowEnergyCharacteristic.Notify):
            self._abort('BLE service characteristics do not match')
            return
        self._cccd = self._notify.descriptor(QBluetoothUuid(
            QBluetoothUuid.DescriptorType.ClientCharacteristicConfiguration))
        if not self._cccd.isValid():
            self._abort('BLE notification descriptor missing')
            return
        self._service.writeDescriptor(self._cccd, QByteArray(b'\x01\x00'))

    def _subscribed(self, descriptor, value):
        if descriptor == self._cccd and bytes(value) == b'\x01\x00':
            self._timer.stop()
            self._ready = True
            generation = self._generation
            self.status.emit('BLE 已连接，等待明确发送')
            if generation == self._generation and self._ready:
                self.ready.emit()

    def send_text(self, text):
        if not self._ready or self._pending_id:
            raise ValueError('BLE is not ready or another message is awaiting acknowledgement')
        self._expire_ids()
        if len(self._sent_ids) >= 256:
            raise ValueError('BLE message budget exhausted; wait before sending again')
        identity = new_message_id()
        packet = self._codec.encode(dict(v=1, kind='text', id=identity, ts=int(time.time()), text=text))
        self._pending_id = identity
        self._sent_ids[(self._codec.key_id, identity)] = time.monotonic()
        self._timer.start(30000)
        self._enqueue(packet)
        return identity

    def _enqueue(self, packet):
        size = max(20, min(512, self._controller.mtu() - 3))
        frames = fragment_packet(packet, size)
        if len(self._queue) + len(frames) > 2048:
            self._abort('BLE send queue full')
            return
        self._queue.extend(frames)
        self._pump()

    def _pump(self):
        if self._ready and self._inflight is None and self._queue:
            self._inflight = self._queue.popleft()
            # ACK-only writes have no pending message ID or message deadline.
            # Every GATT write therefore needs its own response watchdog.
            self._write_timer.start(5000)
            self._service.writeCharacteristic(self._write, QByteArray(self._inflight),
                                              QLowEnergyService.WriteWithResponse)

    def _written(self, characteristic, value):
        if characteristic == self._write and bytes(value) == self._inflight:
            self._write_timer.stop()
            self._inflight = None
            self._pump()

    def _notification(self, characteristic, value):
        if not self._ready or characteristic != self._notify:
            return
        try:
            packet = self._assembler.feed(bytes(value))
            if packet is None:
                return
            payload = self._codec.decode(packet)
        except ProtocolError:
            self.status.emit('忽略未认证或损坏的 BLE 消息')
            return
        identity = payload['id']
        cache_id = (self._codec.key_id, identity)
        generation = self._generation
        self._expire_ids()
        if payload['kind'] == 'ack':
            if identity == self._pending_id:
                self._pending_id = None
                self._timer.stop()
                self.delivered.emit(identity)
        else:
            if cache_id in self._sent_ids:
                return
            if cache_id not in self._seen:
                if len(self._seen) >= 256:
                    return
                self._seen[cache_id] = time.monotonic()
                self.received.emit(payload['text'], identity)
            if generation != self._generation or not self._ready or self._codec is None:
                return
            self._enqueue(self._codec.encode(dict(v=1, kind='ack', id=identity, ts=int(time.time()))))

    def _expire_ids(self):
        now = time.monotonic()
        for cache in (self._seen, self._sent_ids):
            for identity, stamp in tuple(cache.items()):
                if now - stamp > TTL_SECONDS + 10:
                    del cache[identity]

    def _abort(self, reason):
        identity = self._pending_id or ''
        self.stop(notify=False)
        self.status.emit(reason)
        self.failed.emit(identity, reason)

    def stop(self, notify=True):
        cancelled_id = self._pending_id
        self._generation += 1
        self._timer.stop()
        self._write_timer.stop()
        self._ready = False
        self._pending_id = None
        self._queue.clear()
        self._inflight = None
        self._assembler = FragmentAssembler()
        if self._agent:
            self._agent.stop()
            self._agent.deleteLater()
            self._agent = None
        if self._controller:
            self._controller.disconnectFromDevice()
            self._controller.deleteLater()
            self._controller = None
        if self._service:
            self._service.deleteLater()
            self._service = None
        self._codec = None
        self._expire_ids()
        if notify and cancelled_id:
            self.failed.emit(cancelled_id, 'BLE transfer cancelled')
