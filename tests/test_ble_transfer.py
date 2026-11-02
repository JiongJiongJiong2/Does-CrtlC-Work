"""BLE framing/central lifecycle tests. No radio scanning or device connection."""

import io
import time
import unittest
from unittest.mock import Mock, patch
from PySide6.QtCore import QCoreApplication
from core.ble_transfer import BleTextClient, FragmentAssembler, fragment_packet
from core.transfer_protocol import EncryptedCodec, ProtocolError, new_message_id, new_pairing_key


class BleTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_out_of_order_fragments_reassemble_once(self):
        packet = b'example' * 500
        frames = fragment_packet(packet, 20, token=1)
        assembler = FragmentAssembler()
        results = [result for frame in reversed(frames)
                   if (result := assembler.feed(frame, now=0)) is not None]
        self.assertEqual(results, [packet])

    def test_conflicting_fragment_and_invalid_count_are_rejected(self):
        frames = fragment_packet(b'hello' * 10, 20, token=1)
        assembler = FragmentAssembler()
        assembler.feed(frames[0])
        with self.assertRaises(ProtocolError):
            assembler.feed(frames[0][:-1] + b'X')
        with self.assertRaises(ProtocolError):
            assembler.feed(b'bad')

    def test_incomplete_fragment_memory_and_lifetime_are_bounded(self):
        assembler = FragmentAssembler()
        for token in range(10):
            assembler.feed(fragment_packet(b'x' * 100, token=token)[0], now=0)
        self.assertEqual(len(assembler._pending), 4)
        assembler.feed(fragment_packet(b'y' * 100, token=11)[0], now=31)
        self.assertEqual(len(assembler._pending), 1)

    def test_constructor_does_not_scan_and_stop_clears_state(self):
        client = BleTextClient()
        self.assertIsNone(client._agent)
        self.assertIsNone(client._controller)
        with self.assertRaises(ValueError):
            client.send_text('text')
        client.stop()
        self.assertFalse(client._ready)

    def test_characteristic_write_is_not_delivery_ack(self):
        client = BleTextClient()
        client._codec = EncryptedCodec(new_pairing_key())
        client._ready = True
        client._controller = Mock()
        client._controller.mtu.return_value = 23
        client._service = Mock()
        client._write = Mock()
        delivered, failed = [], []
        client.delivered.connect(delivered.append)
        client.failed.connect(lambda *args: failed.append(args))
        identity = client.send_text('hello')
        client._written(client._write, client._inflight)
        self.assertEqual(delivered, [])
        client.stop()
        self.assertEqual(failed, [(identity, 'BLE transfer cancelled')])

    def _ready_client(self):
        client = BleTextClient()
        client._codec = EncryptedCodec(new_pairing_key())
        client._ready = True
        client._controller = Mock()
        client._controller.mtu.return_value = 23
        client._service = Mock()
        client._write = object()
        client._notify = object()
        self.addCleanup(client.stop, notify=False)
        return client

    def test_ack_only_characteristic_write_has_an_independent_watchdog(self):
        client = self._ready_client()
        failed, received = [], []
        client.failed.connect(lambda *args: failed.append(args))
        client.received.connect(lambda *args: received.append(args))
        packet = client._codec.encode(dict(v=1, kind='text', id=new_message_id(),
                                           ts=int(time.time()), text='incoming'))
        for frame in fragment_packet(packet):
            client._notification(client._notify, frame)
        self.assertEqual(len(received), 1)
        self.assertIsNone(client._pending_id)
        self.assertFalse(client._timer.isActive())
        self.assertIsNotNone(client._inflight)
        self.assertTrue(client._write_timer.isActive())

        # The response watchdog must fail even without an outbound text message.
        client._write_timer.timeout.emit()
        self.assertEqual(failed, [('', 'BLE characteristic write timed out')])
        self.assertFalse(client._ready)
        self.assertFalse(client._write_timer.isActive())
        self.assertIsNone(client._controller)
        self.assertEqual(list(client._queue), [])

    def test_each_write_rearms_watchdog_without_resetting_message_deadline(self):
        client = self._ready_client()
        identity = client.send_text('hello')
        message_remaining = client._timer.remainingTime()
        first_frame = client._inflight
        client._write_timer.start(1)
        client._written(object(), first_frame)
        self.assertEqual(client._inflight, first_frame)
        self.assertEqual(client._write_timer.interval(), 1)
        client._written(client._write, first_frame)
        self.assertTrue(client._write_timer.isActive())
        self.assertEqual(client._write_timer.interval(), 5000)
        self.assertEqual(client._timer.interval(), 30000)
        self.assertLessEqual(client._timer.remainingTime(), message_remaining)

        while client._inflight is not None:
            client._written(client._write, client._inflight)
        self.assertFalse(client._write_timer.isActive())
        self.assertTrue(client._timer.isActive())
        self.assertEqual(client._pending_id, identity)

    def test_probe_rejects_empty_key_before_creating_client_or_accessing_radio(self):
        from tools import ble_probe
        with patch('sys.argv', ['ble_probe.py', '--device', 'test-device', '--send', 'hello']), \
                patch('tools.ble_probe.getpass', return_value=''), \
                patch('core.ble_transfer.BleTextClient') as client, \
                patch('PySide6.QtCore.QCoreApplication') as app, \
                patch('sys.stderr', new=io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                ble_probe.main()
        self.assertEqual(result.exception.code, 2)
        client.assert_not_called()
        app.assert_not_called()

    def test_probe_rejects_invalid_text_before_prompting_or_accessing_radio(self):
        from tools import ble_probe
        for text in ('', 'x' * 4097, '中' * 1366):
            with self.subTest(length=len(text)), \
                    patch('sys.argv', ['ble_probe.py', '--device', 'test-device', '--send', text]), \
                    patch('tools.ble_probe.getpass') as prompt, \
                    patch('core.ble_transfer.BleTextClient') as client, \
                    patch('PySide6.QtCore.QCoreApplication') as app, \
                    patch('sys.stderr', new=io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    ble_probe.main()
                self.assertEqual(result.exception.code, 2)
                prompt.assert_not_called()
                client.assert_not_called()
                app.assert_not_called()
