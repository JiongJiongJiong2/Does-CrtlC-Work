"""Real loopback UDP tests: no LAN broadcasts, discovery or clipboard access."""

import os
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QUdpSocket
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.lan_transfer import LanTransfer, Peer
from core.transfer_protocol import EncryptedCodec, new_message_id, new_pairing_key


class LanTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.key = new_pairing_key()
        self.codec = EncryptedCodec(self.key)
        self.a = LanTransfer(retry_ms=30)
        self.b = LanTransfer(retry_ms=30)
        self.assertTrue(self.a.listen(0, '127.0.0.1'))
        self.assertTrue(self.b.listen(0, '127.0.0.1'))
        self.peer_b = Peer('B', '127.0.0.1', self.b.local_port, self.key)
        self.peer_a = Peer('A', '127.0.0.1', self.a.local_port, self.key)
        self.a.configure_peers([self.peer_b])
        self.b.configure_peers([self.peer_a])
        self.a_received, self.b_received, self.delivered, self.failed = [], [], [], []
        self.a.received.connect(lambda *args: self.a_received.append(args))
        self.b.received.connect(lambda *args: self.b_received.append(args))
        self.a.delivered.connect(lambda *args: self.delivered.append(args))
        self.a.failed.connect(lambda *args: self.failed.append(args))
        self.raw = QUdpSocket()
        self.assertTrue(self.raw.bind(QHostAddress.LocalHost, 0, QAbstractSocket.DontShareAddress))

    def tearDown(self):
        self.a.stop()
        self.b.stop()
        self.raw.close()
        self.a.deleteLater()
        self.b.deleteLater()
        self.app.processEvents()

    def wait_for(self, predicate, timeout=1):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(5)
        self.assertTrue(predicate(), 'Timed out waiting for loopback event')

    def text_packet(self, text='hello', message_id=None):
        return self.codec.encode(dict(v=1, kind='text', id=message_id or new_message_id(),
                                      ts=int(time.time()), text=text))

    def send_raw(self, packet, receiver=None):
        receiver = receiver or self.b
        self.assertEqual(self.raw.writeDatagram(packet, QHostAddress.LocalHost, receiver.local_port),
                         len(packet))

    def test_two_real_endpoints_deliver_only_after_authenticated_ack(self):
        message_id = self.a.send_text(self.peer_b, '你好，loopback')
        self.assertEqual(self.delivered, [])
        self.wait_for(lambda: bool(self.delivered))
        self.assertEqual(self.b_received, [('A', '你好，loopback', message_id)])
        self.assertEqual(self.delivered, [(message_id, 'B')])
        self.assertEqual(self.failed, [])

    def test_duplicate_packet_is_acknowledged_again_but_received_once(self):
        packet = self.text_packet()
        for _ in range(2):
            self.send_raw(packet)
            self.wait_for(self.raw.hasPendingDatagrams)
            reply = bytes(self.raw.receiveDatagram().data())
            self.assertEqual(self.codec.decode(reply)['kind'], 'ack')
        self.assertEqual(len(self.b_received), 1)

    def test_unknown_key_bad_mac_oversize_and_expired_packets_are_silent(self):
        now = int(time.time())
        wrong = EncryptedCodec(new_pairing_key()).encode(
            dict(v=1, kind='text', id=new_message_id(), ts=now, text='wrong key'))
        good = self.text_packet()
        bad_mac = good[:-1] + bytes([good[-1] ^ 1])
        expired = self.codec.encode(dict(v=1, kind='text', id=new_message_id(),
                                         ts=now - 70, text='old'), now=now - 70)
        for packet in (wrong, bad_mac, b'bad', b'x' * 8193, expired):
            self.send_raw(packet)
        QTest.qWait(40)
        self.assertEqual(self.b_received, [])
        self.assertFalse(self.raw.hasPendingDatagrams())

    def test_wrong_peer_key_times_out_after_at_most_three_attempts(self):
        self.b.configure_peers([Peer('A', '127.0.0.1', self.a.local_port, new_pairing_key())])
        message_id = self.a.send_text(self.peer_b, 'private')
        pending = self.a._pending[message_id]
        self.wait_for(lambda: bool(self.failed))
        self.assertEqual(pending.attempts, 3)
        self.assertEqual(self.failed[0][0], message_id)
        self.assertEqual(self.b_received, [])
        self.assertEqual(self.delivered, [])

    def test_sender_only_socket_ignores_text_but_accepts_ack(self):
        self.a.stop()
        self.b.received.connect(lambda *_: self.b._socket.writeDatagram(
            self.text_packet('unsolicited'), QHostAddress.LocalHost, self.a.local_port))
        message_id = self.a.send_text(self.peer_b, 'explicit send')
        self.assertFalse(self.a.is_listening)
        self.wait_for(lambda: bool(self.delivered))
        self.assertEqual(self.delivered, [(message_id, 'B')])
        self.assertEqual(self.a_received, [])
        self.assertEqual(self.a.local_port, 0)

    def test_authenticated_reflection_of_own_text_is_not_received(self):
        message_id = self.a.send_text(self.peer_b, 'outgoing')
        packet = self.a._pending[message_id].packet
        self.wait_for(lambda: bool(self.delivered))
        self.b._socket.writeDatagram(packet, QHostAddress.LocalHost, self.a.local_port)
        QTest.qWait(30)
        self.assertEqual(self.a_received, [])

    def test_ack_needs_matching_identifier_key_and_source_endpoint(self):
        self.a._retry_ms = 200
        self.b._listening = False  # Keep bound port, suppress the automatic text ACK.
        message_id = self.a.send_text(self.peer_b, 'pending')
        QTest.qWait(10)
        ack = dict(v=1, kind='ack', id=message_id, ts=int(time.time()))
        packets = (self.codec.encode(dict(ack, id=new_message_id())),
                   EncryptedCodec(new_pairing_key()).encode(ack))
        for packet in packets:
            self.b._socket.writeDatagram(packet, QHostAddress.LocalHost, self.a.local_port)
        self.raw.writeDatagram(self.codec.encode(ack), QHostAddress.LocalHost, self.a.local_port)
        QTest.qWait(20)
        self.assertEqual(self.delivered, [])
        self.b._socket.writeDatagram(self.codec.encode(ack), QHostAddress.LocalHost, self.a.local_port)
        self.wait_for(lambda: bool(self.delivered))

    def test_stop_and_peer_edits_cancel_queued_sends(self):
        first = self.a.send_text(self.peer_b, 'cancel on edit')
        replacement = Peer('B', '127.0.0.1', self.b.local_port, new_pairing_key())
        self.a.configure_peers([replacement])
        second = self.a.send_text(replacement, 'cancel on stop')
        self.a.stop()
        QTest.qWait(120)
        self.assertEqual([entry[0] for entry in self.failed], [first, second])
        self.assertEqual(self.b_received, [])
        self.assertEqual(self.delivered, [])
        self.assertEqual(self.a.local_port, 0)

    def test_new_text_replaces_old_pending_send(self):
        first = self.a.send_text(self.peer_b, 'superseded')
        second = self.a.send_text(self.peer_b, 'latest')
        self.wait_for(lambda: bool(self.delivered))
        self.assertEqual(self.failed[0][0], first)
        self.assertEqual(self.delivered, [(second, 'B')])
        self.assertEqual(self.b_received, [('A', 'latest', second)])

    def test_full_replay_cache_refuses_new_messages_without_eviction(self):
        self.b._replay_limit = 1
        packet = self.text_packet('first')
        self.send_raw(packet)
        self.wait_for(self.raw.hasPendingDatagrams)
        self.raw.receiveDatagram()
        self.send_raw(self.text_packet('over budget'))
        QTest.qWait(30)
        self.assertFalse(self.raw.hasPendingDatagrams())
        self.send_raw(packet)
        self.wait_for(self.raw.hasPendingDatagrams)
        self.assertEqual(len(self.b_received), 1)

    def test_sent_id_budget_is_bounded_and_invalid_input_is_asynchronous(self):
        self.a._replay_limit = 1
        self.a.send_text(self.peer_b, 'first')
        self.wait_for(lambda: bool(self.delivered))
        message_id = self.a.send_text(self.peer_b, 'full')
        self.assertEqual(self.failed, [])
        self.wait_for(lambda: bool(self.failed))
        self.assertEqual(self.failed[0][0], message_id)
        self.assertEqual(len(self.a._sent), 1)
        self.assertEqual(len(self.b_received), 1)

    def test_received_callback_can_stop_without_reopening_socket_or_sending_ack(self):
        self.b.received.connect(lambda *_: self.b.stop())
        self.send_raw(self.text_packet())
        self.wait_for(lambda: bool(self.b_received))
        QTest.qWait(20)
        self.assertFalse(self.b.is_listening)
        self.assertEqual(self.b.local_port, 0)
        self.assertFalse(self.raw.hasPendingDatagrams())

    def test_received_callback_can_revoke_pairing_without_sending_old_key_ack(self):
        self.b.received.connect(lambda *_: self.b.configure_peers([]))
        self.send_raw(self.text_packet())
        self.wait_for(lambda: bool(self.b_received))
        QTest.qWait(20)
        self.assertTrue(self.b.is_listening)
        self.assertFalse(self.raw.hasPendingDatagrams())


if __name__ == '__main__':
    unittest.main()
