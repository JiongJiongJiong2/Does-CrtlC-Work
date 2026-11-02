"""No-configuration nearby discovery lifecycle; no UI or text transmission."""

import sys

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from core.nearby_peers import NearbyRegistry
from core.windows_nearby import WindowsNearby


class NearbyDiscovery(QObject):
    """Keep discovery alive across radio changes without blocking the GUI.

    The registry contains untrusted observations, not paired peers. A sole
    candidate is useful to a future automatic connection flow but does not
    trigger clipboard reads, connections, key exchange or transmissions here.
    """

    status = Signal(str)
    peer_count_changed = Signal(int)

    def __init__(self, parent=None, *, backend_factory=WindowsNearby,
                 registry=None, platform=None):
        super().__init__(parent)
        self.registry = registry if registry is not None else NearbyRegistry()
        self._platform = sys.platform if platform is None else platform
        self._backend = backend_factory(self, instance_id=self.registry.instance_id)
        self._backend.peer_seen.connect(self._on_peer)
        self._backend.availability.connect(self._on_availability)
        self._active = False
        self._available = False
        self._last_status = None
        self._peer_count = 0
        self._retry = QTimer(self)
        self._retry.setInterval(15_000)
        self._retry.timeout.connect(self._try_start)
        self._expiry = QTimer(self)
        self._expiry.setInterval(3000)
        self._expiry.timeout.connect(self._refresh_peers)

    @property
    def available(self):
        return self._available

    def start(self):
        if self._active:
            return
        self._active = True
        if self._platform != 'win32':
            self._on_availability(False, '自动蓝牙发现目前仅支持 Windows 原生后端')
            return
        self._expiry.start()
        self._retry.start()
        self._try_start()

    @Slot()
    def _try_start(self):
        if self._active and not self._backend.is_running:
            self._backend.start()

    @Slot(bool, str)
    def _on_availability(self, available, reason):
        if not self._active:
            return
        self._available = available
        if not available:
            self.registry.clear()
            self._refresh_peers()
        if reason != self._last_status:
            self._last_status = reason
            self.status.emit(reason)

    @Slot(bytes, str, int)
    def _on_peer(self, identity, address, rssi):
        if not self._active:
            return
        try:
            self.registry.observe_identity(identity, address, rssi)
        except ValueError:
            return
        self._refresh_peers()

    @Slot()
    def _refresh_peers(self):
        count = len(self.registry.peers())
        if count != self._peer_count:
            self._peer_count = count
            self.peer_count_changed.emit(count)
            self.status.emit(f'附近运行本工具的设备：{count}；尚未建立传送连接')

    def stop(self, wait_ms=0):
        self._active = self._available = False
        self._retry.stop()
        self._expiry.stop()
        self.registry.clear()
        self._refresh_peers()
        return self._backend.stop(wait_ms=wait_ms)
