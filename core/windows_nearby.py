"""Windows-native BLE discovery only: no pairing, clipboard or text transport.

Qt's Windows backend cannot advertise as a peripheral. Native GATT advertises
our service UUID; its READ-only identity characteristic exposes version + id6.
Keeping ServiceData out of the legacy packet avoids Windows dropping it when
the system also adds the UUID list. Discovery can use a temporary Bluetooth
address identity, and never implies a verified process identity or pairing.
"""

import asyncio
from collections import OrderedDict
import sys
import threading
import time
from types import SimpleNamespace
from uuid import UUID

from PySide6.QtCore import QObject, Qt, Signal, Slot

from core.nearby_peers import (SERVICE_UUID, decode_advertisement,
                              encode_advertisement, process_instance_id)

IDENTITY_UUID = 'b7d0ca13-4d11-4e7d-901c-6e66b55f4800'


class NearbyUnavailable(RuntimeError):
    pass


def _load_winrt():
    # Import lazily on one worker thread. Merely importing this module cannot
    # activate the radio and remains safe on non-Windows installations.
    from winrt.windows.devices.bluetooth import BluetoothAdapter, BluetoothError
    from winrt.windows.devices.bluetooth.advertisement import (
        BluetoothLEAdvertisementWatcher, BluetoothLEAdvertisementWatcherStatus,
        BluetoothLEScanningMode)
    from winrt.windows.devices.bluetooth.genericattributeprofile import (
        GattServiceProvider, GattServiceProviderAdvertisingParameters,
        GattServiceProviderAdvertisementStatus, GattLocalCharacteristicParameters,
        GattCharacteristicProperties, GattProtectionLevel)
    from winrt.windows.storage.streams import DataWriter
    return SimpleNamespace(
        Adapter=BluetoothAdapter, Error=BluetoothError,
        Watcher=BluetoothLEAdvertisementWatcher,
        WatcherStatus=BluetoothLEAdvertisementWatcherStatus,
        ScanMode=BluetoothLEScanningMode, Provider=GattServiceProvider,
        Parameters=GattServiceProviderAdvertisingParameters,
        ProviderStatus=GattServiceProviderAdvertisementStatus, Writer=DataWriter,
        CharacteristicParameters=GattLocalCharacteristicParameters,
        CharacteristicProperties=GattCharacteristicProperties,
        ProtectionLevel=GattProtectionLevel)


class WinRTNearbyBackend:
    """An asyncio-owned native backend; dependencies are injectable for tests."""

    def __init__(self, instance_id, emit, *, api_loader=_load_winrt):
        self.instance_id = instance_id
        self._payload = encode_advertisement(instance_id)
        self._emit = emit
        self._load = api_loader
        self._watcher = self._provider = None
        self._identity_characteristic = None
        self._own_address = None
        self._tokens = []
        self._closed = False
        self._failure = None
        self._peer_lock = threading.Lock()
        self._last_peers = OrderedDict()

    @staticmethod
    def _buffer(api, data):
        writer = api.Writer()
        try:
            writer.write_bytes(data)
            return writer.detach_buffer()
        finally:
            writer.close()

    async def run(self, stop_event):
        try:
            api = self._load()
            adapter = await asyncio.wait_for(api.Adapter.get_default_async(), 8)
            if adapter is None or not adapter.is_low_energy_supported:
                raise NearbyUnavailable('没有可用的 Windows BLE 适配器')
            if not adapter.is_peripheral_role_supported:
                raise NearbyUnavailable('此蓝牙适配器不支持 peripheral，无法双向自动发现')
            self._own_address = adapter.bluetooth_address
            if stop_event.is_set():
                return
            result = await asyncio.wait_for(api.Provider.create_async(UUID(SERVICE_UUID)), 8)
            if result.error != api.Error.SUCCESS or result.service_provider is None:
                error = result.error
                name = getattr(error, 'name', str(error))
                hint = '；请确认系统蓝牙已打开' if int(error) == 1 else ''
                raise NearbyUnavailable(
                    f'Windows 无法创建附近设备发现服务（{name}, {int(error)}{hint}）')
            self._provider = result.service_provider
            if stop_event.is_set():
                return
            identity = api.CharacteristicParameters()
            identity.characteristic_properties = api.CharacteristicProperties.READ
            identity.read_protection_level = api.ProtectionLevel.PLAIN
            identity.static_value = self._buffer(api, self._payload[16:])
            characteristic = await asyncio.wait_for(
                self._provider.service.create_characteristic_async(UUID(IDENTITY_UUID), identity), 8)
            if characteristic.error != api.Error.SUCCESS or characteristic.characteristic is None:
                error = characteristic.error
                name = getattr(error, 'name', str(error))
                raise NearbyUnavailable(f'Windows 无法创建发现标识（{name}, {int(error)}）')
            self._identity_characteristic = characteristic.characteristic
            if stop_event.is_set():
                return
            self._watcher = api.Watcher()
            self._watcher.scanning_mode = api.ScanMode.ACTIVE
            loop = asyncio.get_running_loop()

            def signal_failure(reason):
                if not self._closed:
                    try:
                        loop.call_soon_threadsafe(self._set_failure, reason)
                    except RuntimeError:
                        pass  # Loop has already completed its shutdown.

            def advertisement_status(_sender, args):
                if args.status == api.ProviderStatus.ABORTED:
                    # Real Windows drivers can emit ABORTED/SUCCESS immediately
                    # before STARTED. Poll the settled state during startup.
                    error = getattr(args, 'error', None)
                    if error != api.Error.SUCCESS:
                        signal_failure(f'Windows BLE 广播已中止（{error}）')
                elif args.status == api.ProviderStatus.STARTED_WITHOUT_ALL_ADVERTISEMENT_DATA:
                    signal_failure('广播空间不足，发现标识未能完整发布')
                elif args.status == api.ProviderStatus.STOPPED:
                    signal_failure('Windows BLE 广播已停止')

            self._subscribe(self._provider, 'advertisement_status_changed', advertisement_status)
            self._subscribe(self._watcher, 'received', self._received)
            self._subscribe(self._watcher, 'stopped',
                            lambda *_: signal_failure('Windows BLE 扫描已停止'))
            parameters = api.Parameters()
            # Windows needs both flags to advertise the service UUID. The only
            # attribute is a public READ-only discovery identity, not text I/O.
            # ServiceData competes with the UUID list even with a 7-byte body;
            # do not require Extended Advertising for this legacy discovery.
            parameters.is_discoverable = True
            parameters.is_connectable = True
            self._provider.start_advertising(parameters)
            self._watcher.start()
            started_at = time.monotonic()
            announced = False
            while not stop_event.is_set():
                if self._failure:
                    raise NearbyUnavailable(self._failure)
                provider_status = self._provider.advertisement_status
                watcher_status = self._watcher.status
                if provider_status == api.ProviderStatus.STARTED_WITHOUT_ALL_ADVERTISEMENT_DATA:
                    raise NearbyUnavailable('广播空间不足，发现标识未能完整发布')
                if watcher_status == api.WatcherStatus.ABORTED:
                    raise NearbyUnavailable('Windows 蓝牙广播或扫描不可用')
                if (provider_status == api.ProviderStatus.ABORTED and
                        (announced or time.monotonic() - started_at >= 1)):
                    raise NearbyUnavailable('Windows BLE 广播已中止')
                active = (provider_status == api.ProviderStatus.STARTED and
                          watcher_status == api.WatcherStatus.STARTED)
                if active and not announced:
                    announced = True
                    self._emit('availability', (True, '本机广播和扫描已启动；发现不等于配对或信任'))
                elif not announced and time.monotonic() - started_at > 8:
                    raise NearbyUnavailable('等待 Windows 启动广播和扫描超时')
                elif announced and not active:
                    raise NearbyUnavailable('Windows 蓝牙广播或扫描已经停止')
                await asyncio.sleep(0.1)
        finally:
            self.close()

    def _set_failure(self, reason):
        if not self._closed:
            self._failure = reason

    def _subscribe(self, source, event, callback):
        token = getattr(source, 'add_' + event)(callback)
        self._tokens.append((source, event, token))

    def _received(self, _sender, args):
        if self._closed:
            return
        try:
            address = int(args.bluetooth_address)
            rssi = int(args.raw_signal_strength_in_dbm)
            # WinRT uses -127 as an out-of-range/offline indication. Replaying
            # that old advertisement must not renew the peer's live TTL.
            if (not 0 < address < 1 << 48 or address == self._own_address or
                    not -127 < rssi <= 20):
                return
            identity = None
            # Do not read names, manufacturer sections or payloads of other apps.
            for section in args.advertisement.data_sections:
                if section.data_type != 0x21 or section.data.length != 23:
                    continue
                try:
                    identity = decode_advertisement(bytes(section.data))
                except ValueError:
                    continue
                if identity == self.instance_id:
                    return
                break
            if identity is None:
                if UUID(SERVICE_UUID) not in args.advertisement.service_uuids:
                    return
            # Always use one address-derived discovery key, including for AD0x21,
            # so scan responses and service-data packets cannot duplicate a peer.
            # This is never proof of the remote GATT process identity.
            identity = address.to_bytes(6, 'big')
            # Bound callback traffic before handing events to Qt. This is
            # discovery throttling, not authentication or peer selection.
            now = time.monotonic()
            with self._peer_lock:
                if now - self._last_peers.get(identity, float('-inf')) < 0.25:
                    return
                if identity not in self._last_peers and len(self._last_peers) >= 64:
                    oldest, stamp = next(iter(self._last_peers.items()))
                    if now - stamp < 12:
                        return
                    del self._last_peers[oldest]
                self._last_peers[identity] = now
                self._last_peers.move_to_end(identity)
            if not self._closed:
                self._emit('peer', (identity, f'{address:012X}', rssi))
        except (AttributeError, OSError, TypeError, ValueError):
            return  # Ignore malformed/unavailable radio data without logging it.

    def close(self):
        if self._closed:
            return
        self._closed = True
        for source, event, token in reversed(self._tokens):
            try:
                getattr(source, 'remove_' + event)(token)
            except (OSError, RuntimeError):
                pass
        self._tokens.clear()
        for source, method in ((self._watcher, 'stop'), (self._provider, 'stop_advertising')):
            if source is not None:
                try:
                    getattr(source, method)()
                except (OSError, RuntimeError):
                    pass
        self._watcher = self._provider = None
        self._identity_characteristic = None


class WindowsNearby(QObject):
    """GUI-thread facade. start() needs no device/configuration inputs.

    availability describes this machine's advertising/scanning state, never a
    secure connection. stop() returns False if native cleanup is still running;
    keep the owner alive and retry instead of destroying a live worker.
    peer_seen's first argument is a temporary six-byte Bluetooth address key.
    """

    peer_seen = Signal(bytes, str, int)
    status = Signal(str)
    availability = Signal(bool, str)
    _event = Signal(int, str, object)

    def __init__(self, parent=None, *, instance_id=None, backend_factory=None, platform=None):
        super().__init__(parent)
        self.instance_id = process_instance_id() if instance_id is None else instance_id
        encode_advertisement(self.instance_id)
        self._factory = backend_factory or WinRTNearbyBackend
        self._platform = sys.platform if platform is None else platform
        self._generation = 0
        self._thread = None
        self._stop_event = None
        self._event.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running:
            return False
        if self._platform != 'win32':
            self.availability.emit(False, '自动蓝牙发现目前仅支持 Windows 原生后端')
            return False
        self._generation += 1
        generation = self._generation
        stop_event = self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._worker, args=(generation, stop_event),
                                        name='DoseCtrlC-nearby', daemon=False)
        self._thread.start()
        return True

    def _worker(self, generation, stop_event):
        def emit(kind, values):
            if not stop_event.is_set():
                self._event.emit(generation, kind, values)

        async def run():
            backend = self._factory(self.instance_id, emit)
            operation = asyncio.create_task(backend.run(stop_event))
            try:
                while not operation.done() and not stop_event.is_set():
                    await asyncio.sleep(0.05)
                if stop_event.is_set() and not operation.done():
                    operation.cancel()
                await operation
            finally:
                if not operation.done():
                    operation.cancel()
                    try:
                        await operation
                    except asyncio.CancelledError:
                        pass

        try:
            asyncio.run(run())
        except asyncio.CancelledError:
            pass
        except ImportError:
            emit('availability', (False, '未安装 Windows 原生蓝牙依赖'))
        except NearbyUnavailable as error:
            emit('availability', (False, str(error)))
        except Exception as error:
            emit('availability', (False, f'Windows 蓝牙初始化失败（{type(error).__name__}）'))

    @Slot(int, str, object)
    def _dispatch(self, generation, kind, values):
        if generation != self._generation:
            return
        if kind == 'peer':
            self.peer_seen.emit(*values)
        elif kind == 'availability':
            self.availability.emit(*values)
            if generation == self._generation:
                self.status.emit(values[1])
        elif kind == 'status':
            self.status.emit(*values)

    def stop(self, wait_ms=1000):
        if self._stop_event is not None and not self._stop_event.is_set():
            self._generation += 1
            self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(max(0, min(int(wait_ms), 5000)) / 1000)
        if thread is not None and thread.is_alive():
            return False
        self._thread = None
        return True
