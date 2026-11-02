"""BLE replay and callback lifecycle regressions, with no access to the radio."""

import time
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication

from core.ble_transfer import BleTextClient, fragment_packet
from core.transfer_protocol import EncryptedCodec, new_message_id, new_pairing_key


class FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in tuple(self.callbacks):
            callback(*args)


def fake_agent():
    return Mock(deviceDiscovered=FakeSignal(), finished=FakeSignal(),
                errorOccurred=FakeSignal())


def fake_controller():
    return Mock(connected=FakeSignal(), discoveryFinished=FakeSignal(),
                disconnected=FakeSignal(), errorOccurred=FakeSignal())


class BleLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.client = BleTextClient()
        self.codec = EncryptedCodec(new_pairing_key())
        self.received = []
        self.client.received.connect(lambda text, identity: self.received.append((text, identity)))
        self.client._enqueue = Mock()

    def tearDown(self):
        self.client.stop(notify=False)

    def _ready(self, codec=None):
        self.client._codec = codec or self.codec
        self.client._ready = True
        self.client._notify = object()

    def _packet(self, text='hello', identity=None, codec=None):
        return (codec or self.codec).encode(dict(
            v=1, kind='text', id=identity or new_message_id(),
            ts=int(time.time()), text=text))

    def _feed(self, packet):
        characteristic = self.client._notify
        for frame in fragment_packet(packet, value_size=200):
            self.client._notification(characteristic, frame)

    def test_reconnect_does_not_deliver_an_authenticated_replay_twice(self):
        self._ready()
        packet = self._packet()
        self._feed(packet)
        self.client.stop()
        self._ready()
        self._feed(packet)

        self.assertEqual(len(self.received), 1)
        # A retransmission must still receive an ACK so a lost ACK can recover.
        self.assertEqual(self.client._enqueue.call_count, 2)
        for call in self.client._enqueue.call_args_list:
            ack = self.codec.decode(call.args[0])
            self.assertEqual((ack['kind'], ack['id']), ('ack', self.received[0][1]))

    def test_reflection_of_sent_ciphertext_stays_rejected_after_reconnect(self):
        self._ready()
        self.client.send_text('outgoing')
        packet = self.client._enqueue.call_args.args[0]
        self.client.stop(notify=False)
        self.client._enqueue.reset_mock()
        self._ready()
        self._feed(packet)

        self.assertEqual(self.received, [])
        self.client._enqueue.assert_not_called()

    def test_replay_identity_is_scoped_to_the_pairing_key(self):
        identity = new_message_id()
        self._ready()
        self._feed(self._packet('first peer', identity))
        self.client.stop()
        second_codec = EncryptedCodec(new_pairing_key())
        self._ready(second_codec)
        self._feed(self._packet('second peer', identity, second_codec))

        self.assertEqual(self.received, [('first peer', identity), ('second peer', identity)])

    def test_only_an_authenticated_matching_ack_confirms_delivery(self):
        self._ready()
        delivered = []
        self.client.delivered.connect(delivered.append)
        identity = self.client.send_text('outgoing')
        ack = dict(v=1, kind='ack', id=identity, ts=int(time.time()))

        self._feed(EncryptedCodec(new_pairing_key()).encode(ack))
        self._feed(self.codec.encode(dict(ack, id=new_message_id())))
        packet = self.codec.encode(ack)
        self._feed(packet[:-1] + bytes([packet[-1] ^ 1]))
        self.assertEqual(delivered, [])
        self.assertEqual(self.client._pending_id, identity)

        self._feed(packet)
        self._feed(packet)
        self.assertEqual(delivered, [identity])
        self.assertIsNone(self.client._pending_id)
        self.assertFalse(self.client._timer.isActive())

    def test_stop_from_scan_status_prevents_starting_the_cancelled_agent(self):
        agent = fake_agent()
        self.client.status.connect(lambda _: self.client.stop())
        with patch('core.ble_transfer.QBluetoothDeviceDiscoveryAgent', return_value=agent):
            self.client.scan()

        agent.start.assert_not_called()
        self.assertIsNone(self.client._agent)
        self.assertFalse(self.client._timer.isActive())

    def test_stop_from_connect_status_prevents_connecting_the_cancelled_controller(self):
        controller = fake_controller()
        self.client._devices['test-device'] = object()
        self.client.status.connect(lambda _: self.client.stop())
        with patch('core.ble_transfer.QLowEnergyController.createCentral', return_value=controller):
            self.client.connect_device('test-device', new_pairing_key())

        controller.connectToDevice.assert_not_called()
        self.assertIsNone(self.client._controller)
        self.assertFalse(self.client._timer.isActive())

    def test_stop_from_subscribed_status_does_not_emit_ready(self):
        self.client._cccd = object()
        ready = []
        self.client.ready.connect(lambda: ready.append(True))
        self.client.status.connect(lambda _: self.client.stop())
        self.client._subscribed(self.client._cccd, b'\x01\x00')

        self.assertEqual(ready, [])
        self.assertFalse(self.client._ready)

    def test_stop_from_received_callback_prevents_ack_on_closed_connection(self):
        self._ready()
        self.client.received.connect(lambda *_: self.client.stop())
        self._feed(self._packet())

        self.assertEqual(len(self.received), 1)
        self.client._enqueue.assert_not_called()
        self.assertFalse(self.client._ready)

    def test_reconnect_inside_received_callback_does_not_ack_on_new_connection(self):
        self._ready()
        replacement = EncryptedCodec(new_pairing_key())

        def reconnect(*_):
            self.client.stop()
            self._ready(replacement)

        self.client.received.connect(reconnect)
        self._feed(self._packet())

        self.assertEqual(len(self.received), 1)
        self.assertIs(self.client._codec, replacement)
        self.client._enqueue.assert_not_called()

    def test_callbacks_from_retired_scanner_do_not_affect_the_new_scan(self):
        retired, current = fake_agent(), fake_agent()
        discoveries, completions = [], []
        self.client.discovered.connect(lambda *args: discoveries.append(args))
        self.client.scan_finished.connect(lambda: completions.append(True))
        with patch('core.ble_transfer.QBluetoothDeviceDiscoveryAgent', side_effect=[retired, current]):
            self.client.scan()
            self.client.scan()
            retired.deviceDiscovered.emit(object())
            retired.finished.emit()

        self.assertEqual(discoveries, [])
        self.assertEqual(completions, [])
        self.assertEqual(self.client._devices, {})
        self.assertIs(self.client._agent, current)
        current.start.assert_called_once()

    def test_reconnect_from_cancellation_callback_supersedes_outer_connection(self):
        outer_info, replacement_info = object(), object()
        self.client._devices.update(outer=outer_info, replacement=replacement_info)
        self.client._pending_id = new_message_id()
        replacement, unwanted = fake_controller(), fake_controller()
        key = new_pairing_key()
        self.client.failed.connect(lambda *_: self.client.connect_device('replacement', key))

        with patch('core.ble_transfer.QLowEnergyController.createCentral',
                   side_effect=[replacement, unwanted]) as create:
            self.client.connect_device('outer', key)

        create.assert_called_once_with(replacement_info, self.client)
        self.assertIs(self.client._controller, replacement)
        replacement.connectToDevice.assert_called_once()
        unwanted.connectToDevice.assert_not_called()

    def test_reconnect_from_cancellation_callback_supersedes_outer_scan(self):
        self.client._devices['replacement'] = object()
        self.client._pending_id = new_message_id()
        replacement = fake_controller()
        self.client.failed.connect(lambda *_: self.client.connect_device('replacement', new_pairing_key()))

        with patch('core.ble_transfer.QLowEnergyController.createCentral', return_value=replacement), \
                patch('core.ble_transfer.QBluetoothDeviceDiscoveryAgent') as create_agent:
            self.client.scan()

        create_agent.assert_not_called()
        self.assertIs(self.client._controller, replacement)
        replacement.connectToDevice.assert_called_once()


if __name__ == '__main__':
    unittest.main()
