"""Windows discovery lifecycle tests; all native APIs are fake, no radio use."""

import asyncio
from enum import IntEnum
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from PySide6.QtCore import QCoreApplication

from core.nearby_peers import SERVICE_UUID, encode_advertisement
from core.windows_nearby import (IDENTITY_UUID, NearbyUnavailable, WindowsNearby,
                                WinRTNearbyBackend)


class ProviderStatus(IntEnum):
    CREATED = 0
    STOPPED = 1
    STARTED = 2
    ABORTED = 3
    STARTED_WITHOUT_ALL_ADVERTISEMENT_DATA = 4


class WatcherStatus(IntEnum):
    CREATED = 0
    STARTED = 1
    STOPPING = 2
    STOPPED = 3
    ABORTED = 4


class Buffer(bytes):
    @property
    def length(self):
        return len(self)


class Writer:
    def write_bytes(self, data):
        self.data = data

    def detach_buffer(self):
        return Buffer(self.data)

    def close(self):
        pass


class Events:
    def __init__(self):
        self.callbacks = {}
        self.removed = []
        self.next_token = 0

    def add(self, name, callback):
        self.next_token += 1
        self.callbacks[self.next_token] = (name, callback)
        return self.next_token

    def remove(self, name, token):
        assert self.callbacks[token][0] == name
        del self.callbacks[token]
        self.removed.append((name, token))

    def fire(self, name, args):
        for event, callback in tuple(self.callbacks.values()):
            if event == name:
                callback(self, args)


class Provider(Events):
    def __init__(self, start_status=ProviderStatus.STARTED):
        super().__init__()
        self.advertisement_status = ProviderStatus.CREATED
        self.start_status = start_status
        self.parameters = None
        self.stop_calls = 0
        self.service = self
        self.identity = None

    async def create_characteristic_async(self, uuid, parameters):
        self.identity = (uuid, parameters)
        return SimpleNamespace(error=0, characteristic=object())

    def add_advertisement_status_changed(self, callback):
        return self.add('advertisement_status_changed', callback)

    def remove_advertisement_status_changed(self, token):
        self.remove('advertisement_status_changed', token)

    def start_advertising(self, parameters):
        self.parameters = parameters
        self.advertisement_status = self.start_status
        self.fire('advertisement_status_changed', SimpleNamespace(status=self.start_status))

    def stop_advertising(self):
        self.stop_calls += 1
        self.advertisement_status = ProviderStatus.STOPPED
        self.fire('advertisement_status_changed', SimpleNamespace(status=self.advertisement_status))


class Watcher(Events):
    def __init__(self, start_status=WatcherStatus.STARTED):
        super().__init__()
        self.status = WatcherStatus.CREATED
        self.start_status = start_status
        self.stop_calls = 0

    def add_received(self, callback):
        return self.add('received', callback)

    def remove_received(self, token):
        self.remove('received', token)

    def add_stopped(self, callback):
        return self.add('stopped', callback)

    def remove_stopped(self, token):
        self.remove('stopped', token)

    def start(self):
        self.status = self.start_status

    def stop(self):
        self.stop_calls += 1
        self.status = WatcherStatus.STOPPED
        self.fire('stopped', SimpleNamespace())


def fake_api(*, low_energy=True, peripheral=True,
             provider_status=ProviderStatus.STARTED, watcher_status=WatcherStatus.STARTED):
    provider = Provider(provider_status)
    watcher = Watcher(watcher_status)
    created = []

    async def get_default_async():
        return SimpleNamespace(is_low_energy_supported=low_energy,
                               is_peripheral_role_supported=peripheral,
                               bluetooth_address=0x010203040506)

    async def create_async(uuid):
        created.append(uuid)
        return SimpleNamespace(error=0, service_provider=provider)

    return SimpleNamespace(
        Adapter=SimpleNamespace(get_default_async=get_default_async),
        Provider=SimpleNamespace(create_async=create_async),
        Error=SimpleNamespace(SUCCESS=0),
        ProviderStatus=ProviderStatus, WatcherStatus=WatcherStatus,
        Watcher=lambda: watcher, Parameters=SimpleNamespace,
        ScanMode=SimpleNamespace(ACTIVE=1), Writer=Writer,
        CharacteristicParameters=SimpleNamespace,
        CharacteristicProperties=SimpleNamespace(READ=2),
        ProtectionLevel=SimpleNamespace(PLAIN=0),
        provider=provider, watcher=watcher, created=created)


def received(identity=b'peer01', *, data=None, data_type=0x21, address=0xAABBCCDDEEFF, rssi=-58):
    if data is None:
        data = encode_advertisement(identity)
    return SimpleNamespace(
        advertisement=SimpleNamespace(service_uuids=[], data_sections=[
            SimpleNamespace(data_type=data_type, data=Buffer(data))]),
        bluetooth_address=address, raw_signal_strength_in_dbm=rssi)


class NativeDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_service_uuid_read_only_identity_and_native_cleanup(self):
        api = fake_api()
        stop = threading.Event()
        events = []

        def emit(kind, values):
            events.append((kind, values))
            stop.set()

        backend = WinRTNearbyBackend(b'own-id', emit, api_loader=lambda: api)
        await backend.run(stop)
        self.assertEqual(api.created, [UUID(SERVICE_UUID)])
        self.assertFalse(hasattr(api.provider.parameters, 'service_data'))
        self.assertTrue(api.provider.parameters.is_connectable)
        self.assertTrue(api.provider.parameters.is_discoverable)
        identity_uuid, identity = api.provider.identity
        self.assertEqual(identity_uuid, UUID(IDENTITY_UUID))
        self.assertEqual(bytes(identity.static_value), b'\x01own-id')
        self.assertEqual(identity.characteristic_properties, api.CharacteristicProperties.READ)
        self.assertEqual(identity.read_protection_level, api.ProtectionLevel.PLAIN)
        self.assertEqual(api.watcher.scanning_mode, api.ScanMode.ACTIVE)
        self.assertEqual(events[0][0], 'availability')
        self.assertTrue(events[0][1][0])
        self.assertEqual(api.provider.stop_calls, 1)
        self.assertEqual(api.watcher.stop_calls, 1)
        self.assertEqual(api.provider.callbacks, {})
        self.assertEqual(api.watcher.callbacks, {})
        self.assertEqual(len(api.provider.removed), 1)
        self.assertEqual(len(api.watcher.removed), 2)
        backend.close()
        self.assertEqual(api.provider.stop_calls, 1)

    async def test_missing_adapter_features_never_create_service(self):
        for low_energy, peripheral in ((False, True), (True, False)):
            with self.subTest(low_energy=low_energy, peripheral=peripheral):
                api = fake_api(low_energy=low_energy, peripheral=peripheral)
                emit = Mock()
                backend = WinRTNearbyBackend(b'own-id', emit, api_loader=lambda: api)
                with self.assertRaises(NearbyUnavailable):
                    await backend.run(threading.Event())
                self.assertEqual(api.created, [])
                self.assertIsNone(api.provider.parameters)
                emit.assert_not_called()

    async def test_aborted_or_incomplete_advertisements_are_not_available(self):
        for state in (ProviderStatus.ABORTED, ProviderStatus.STARTED_WITHOUT_ALL_ADVERTISEMENT_DATA):
            with self.subTest(state=state):
                api = fake_api(provider_status=state)
                emit = Mock()
                backend = WinRTNearbyBackend(b'own-id', emit, api_loader=lambda: api)
                with self.assertRaises(NearbyUnavailable):
                    await backend.run(threading.Event())
                emit.assert_not_called()
                self.assertEqual(api.provider.stop_calls, 1)
                self.assertEqual(api.watcher.stop_calls, 1)
                self.assertEqual(api.provider.callbacks, {})
                self.assertEqual(api.watcher.callbacks, {})

    async def test_create_failure_keeps_native_error_for_diagnosis(self):
        class Error(IntEnum):
            SUCCESS = 0
            RADIO_NOT_AVAILABLE = 1

        api = fake_api()

        async def create_async(_uuid):
            return SimpleNamespace(error=Error.RADIO_NOT_AVAILABLE, service_provider=None)

        api.Provider.create_async = create_async
        backend = WinRTNearbyBackend(b'own-id', Mock(), api_loader=lambda: api)
        with self.assertRaisesRegex(NearbyUnavailable, 'RADIO_NOT_AVAILABLE, 1'):
            await backend.run(threading.Event())
        self.assertIsNone(api.provider.parameters)

    async def test_watcher_aborted_cleans_up_provider(self):
        api = fake_api(watcher_status=WatcherStatus.ABORTED)
        emit = Mock()
        backend = WinRTNearbyBackend(b'own-id', emit, api_loader=lambda: api)
        with self.assertRaises(NearbyUnavailable):
            await backend.run(threading.Event())
        emit.assert_not_called()
        self.assertEqual(api.provider.stop_calls, 1)

    async def test_native_stop_callback_retires_backend_after_success(self):
        api = fake_api()
        events = []

        def emit(kind, values):
            events.append((kind, values))
            # Model a native event before its status property catches up.
            api.watcher.fire('stopped', SimpleNamespace())

        backend = WinRTNearbyBackend(b'own-id', emit, api_loader=lambda: api)
        with self.assertRaisesRegex(NearbyUnavailable, '扫描已停止'):
            await backend.run(threading.Event())
        self.assertEqual(len(events), 1)
        self.assertEqual(api.watcher.callbacks, {})

    async def test_transient_startup_aborted_with_success_does_not_mask_started(self):
        api = fake_api()
        original_start = api.provider.start_advertising

        def start(parameters):
            api.provider.fire('advertisement_status_changed', SimpleNamespace(
                status=ProviderStatus.ABORTED, error=api.Error.SUCCESS))
            original_start(parameters)

        api.provider.start_advertising = start
        stop = threading.Event()
        events = []

        def emit(kind, values):
            events.append((kind, values))
            stop.set()

        backend = WinRTNearbyBackend(b'own-id', emit, api_loader=lambda: api)
        await backend.run(stop)
        self.assertEqual(events[0][1][0], True)

    async def test_persistent_aborted_with_success_has_bounded_startup_grace(self):
        api = fake_api()

        def start(_parameters):
            api.provider.advertisement_status = ProviderStatus.ABORTED
            api.provider.fire('advertisement_status_changed', SimpleNamespace(
                status=ProviderStatus.ABORTED, error=api.Error.SUCCESS))

        api.provider.start_advertising = start
        emit = Mock()
        backend = WinRTNearbyBackend(b'own-id', emit, api_loader=lambda: api)
        with self.assertRaisesRegex(NearbyUnavailable, '广播已中止'):
            await asyncio.wait_for(backend.run(threading.Event()), 2)
        emit.assert_not_called()
        self.assertEqual(api.provider.stop_calls, 1)

    async def test_cancel_during_provider_creation_does_not_start_radio(self):
        api = fake_api()
        entered = asyncio.Event()

        async def create_async(_uuid):
            entered.set()
            await asyncio.Event().wait()

        api.Provider.create_async = create_async
        backend = WinRTNearbyBackend(b'own-id', Mock(), api_loader=lambda: api)
        task = asyncio.create_task(backend.run(threading.Event()))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(api.provider.parameters)
        self.assertTrue(backend._closed)


class AdvertisementFilteringTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.backend = WinRTNearbyBackend(b'own-id', lambda *args: self.events.append(args))

    def test_only_matching_service_payload_emits_peer_identity(self):
        for args in (
                received(b'own-id'), received(data_type=0xFF),
                received(data=b'wrong'), received(data=bytes(23)),
                received(data=encode_advertisement(b'peer01') + b'extra'),
                received(data=encode_advertisement(b'peer01')[:16] + b'\x02peer01'),
                received(address=0), received(rssi=127)):
            self.backend._received(None, args)
        self.assertEqual(self.events, [])
        self.backend._received(None, received())
        self.assertEqual(self.events, [('peer', (bytes.fromhex('AABBCCDDEEFF'), 'AABBCCDDEEFF', -58))])

    def test_uuid_only_advertisement_uses_address_as_temporary_identity(self):
        args = received(data=b'')
        args.advertisement.service_uuids = [UUID(SERVICE_UUID)]
        self.backend._received(None, args)
        self.assertEqual(self.events, [('peer', (bytes.fromhex('AABBCCDDEEFF'), 'AABBCCDDEEFF', -58))])

    def test_service_data_and_uuid_only_do_not_create_different_peer_keys(self):
        args = received(data=b'')
        args.advertisement.service_uuids = [UUID(SERVICE_UUID)]
        with patch('core.windows_nearby.time.monotonic', side_effect=[1, 1.3]):
            self.backend._received(None, received())
            self.backend._received(None, args)
        self.assertEqual(self.events[0][1][0], self.events[1][1][0])

    def test_offline_sentinel_and_local_address_do_not_refresh_discovery(self):
        self.backend._own_address = 0xAABBCCDDEE01
        for args in (received(rssi=-127), received(address=self.backend._own_address)):
            self.backend._received(None, args)
        self.assertEqual(self.events, [])
        self.assertEqual(len(self.backend._last_peers), 0)

    def test_repeated_radio_events_are_throttled_before_qt_queue(self):
        with patch('core.windows_nearby.time.monotonic', side_effect=[1, 1.1, 1.25]):
            for _ in range(3):
                self.backend._received(None, received())
        self.assertEqual(len(self.events), 2)

    def test_incoming_identity_storage_is_bounded(self):
        with patch('core.windows_nearby.time.monotonic', return_value=1):
            for i in range(100):
                self.backend._received(None, received(i.to_bytes(6, 'little'), address=i+1))
        self.assertEqual(len(self.events), 64)
        self.assertEqual(len(self.backend._last_peers), 64)
        with patch('core.windows_nearby.time.monotonic', return_value=13):
            self.backend._received(None, received(b'new-id'))
        self.assertEqual(len(self.events), 65)
        self.assertEqual(len(self.backend._last_peers), 64)

    def test_late_native_callback_after_close_is_ignored(self):
        self.backend.close()
        self.backend._received(None, received())
        self.assertEqual(self.events, [])


class WindowsNearbyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.facades = []

    def tearDown(self):
        for facade in self.facades:
            facade.stop()
        self.app.processEvents()

    def facade(self, **kwargs):
        facade = WindowsNearby(instance_id=b'own-id', platform='win32', **kwargs)
        self.facades.append(facade)
        return facade

    def wait_for(self, predicate, seconds=2):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate())

    def test_non_windows_is_explicitly_unavailable_without_loading_backend(self):
        factory = Mock()
        facade = WindowsNearby(platform='linux', backend_factory=factory)
        events = []
        facade.availability.connect(lambda *args: events.append(args))
        self.assertFalse(facade.start())
        self.assertFalse(events[0][0])
        self.assertIn('Windows', events[0][1])
        factory.assert_not_called()

    def test_missing_winrt_is_reported_without_crashing(self):
        facade = self.facade(backend_factory=Mock(side_effect=ImportError()))
        events = []
        facade.availability.connect(lambda *args: events.append(args))
        self.assertTrue(facade.start())
        self.wait_for(lambda: events)
        self.assertEqual(events, [(False, '未安装 Windows 原生蓝牙依赖')])
        self.assertTrue(facade.stop())

    def test_worker_events_arrive_on_qt_owner_thread(self):
        native_threads = []
        finished = threading.Event()

        class Backend:
            def __init__(self, _id, emit):
                self.emit = emit

            async def run(self, _stop):
                try:
                    native_threads.append(threading.get_ident())
                    self.emit('peer', (b'peer01', 'AABBCCDDEEFF', -60))
                    await asyncio.Event().wait()
                finally:
                    finished.set()

        owner_thread = threading.get_ident()
        received_threads = []
        facade = self.facade(backend_factory=Backend)
        facade.peer_seen.connect(lambda *_: received_threads.append(threading.get_ident()))
        facade.start()
        self.assertFalse(facade.start())
        self.wait_for(lambda: received_threads)
        self.assertEqual(received_threads, [owner_thread])
        self.assertNotEqual(native_threads, [owner_thread])
        self.assertTrue(facade.stop())
        self.assertTrue(finished.is_set())

    def test_stop_cancels_startup_and_rejects_already_queued_callbacks(self):
        entered = threading.Event()
        cleaned = threading.Event()

        class Backend:
            def __init__(self, _id, emit):
                self.emit = emit

            async def run(self, _stop):
                try:
                    self.emit('availability', (True, 'ready'))
                    self.emit('peer', (b'peer01', 'AABBCCDDEEFF', -60))
                    entered.set()
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()

        facade = self.facade(backend_factory=Backend)
        events = []
        facade.peer_seen.connect(lambda *args: events.append(args))
        facade.availability.connect(lambda *args: events.append(args))
        facade.start()
        self.assertTrue(entered.wait(1))  # Do not process Qt events until stop.
        self.assertTrue(facade.stop())
        self.app.processEvents()
        self.assertTrue(cleaned.is_set())
        self.assertEqual(events, [])
        self.assertFalse(facade.is_running)

    def test_stop_can_be_polled_while_cleanup_finishes_without_force_kill(self):
        entered = threading.Event()
        release = threading.Event()

        class Backend:
            def __init__(self, *_):
                pass

            async def run(self, _stop):
                try:
                    entered.set()
                    await asyncio.Event().wait()
                finally:
                    # Simulate a synchronous native cleanup that takes time.
                    release.wait(2)

        facade = self.facade(backend_factory=Backend)
        facade.start()
        self.assertTrue(entered.wait(1))
        try:
            started = time.monotonic()
            self.assertFalse(facade.stop(wait_ms=0))
            self.assertLess(time.monotonic() - started, 0.1)
            self.assertTrue(facade.is_running)
            self.assertFalse(facade.start())
        finally:
            release.set()
        self.assertTrue(facade.stop())
        self.assertTrue(facade.stop(wait_ms=0))

    def test_availability_handler_stopping_prevents_following_status(self):
        entered = threading.Event()

        class Backend:
            def __init__(self, _id, emit):
                self.emit = emit

            async def run(self, _stop):
                self.emit('availability', (True, 'ready'))
                entered.set()
                await asyncio.Event().wait()

        facade = self.facade(backend_factory=Backend)
        statuses = []
        availability = []
        facade.status.connect(statuses.append)

        def stop(*args):
            availability.append(args)
            facade.stop()

        facade.availability.connect(stop)
        facade.start()
        self.wait_for(lambda: availability)
        self.assertEqual(statuses, [])
        self.assertFalse(facade.is_running)


if __name__ == '__main__':
    unittest.main()
