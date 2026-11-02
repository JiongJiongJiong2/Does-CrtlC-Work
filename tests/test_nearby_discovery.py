"""Automatic discovery lifecycle, with no radio or clipboard access."""

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from core.nearby_discovery import NearbyDiscovery
from core.nearby_peers import NearbyRegistry


class FakeBackend(QObject):
    peer_seen = Signal(bytes, str, int)
    availability = Signal(bool, str)

    def __init__(self, parent, *, instance_id):
        super().__init__(parent)
        self.instance_id = instance_id
        self.is_running = False
        self.starts = 0
        self.cleanup_finished = True

    def start(self):
        self.starts += 1
        self.is_running = True

    def stop(self, wait_ms=0):
        self.is_running = not self.cleanup_finished
        return self.cleanup_finished


class NearbyDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.now = 0
        self.discovery = NearbyDiscovery(
            backend_factory=FakeBackend, platform='win32',
            registry=NearbyRegistry(b'local1', clock=lambda: self.now))
        self.backend = self.discovery._backend

    def tearDown(self):
        self.backend.cleanup_finished = True
        self.discovery.stop()

    def test_background_start_needs_no_configuration_and_does_not_duplicate_worker(self):
        self.discovery.start()
        self.discovery.start()
        self.discovery._try_start()
        self.assertEqual(self.backend.starts, 1)
        self.assertEqual(self.backend.instance_id, b'local1')
        self.assertFalse(self.discovery.available)
        self.backend.availability.emit(True, 'active')
        self.assertTrue(self.discovery.available)

    def test_radio_failure_clears_stale_peers_and_recovers_on_retry(self):
        self.discovery.start()
        self.backend.peer_seen.emit(b'other1', '000000000001', -60)
        self.assertIsNotNone(self.discovery.registry.candidate)
        self.backend.is_running = False
        self.backend.availability.emit(False, 'radio off')
        self.assertEqual(self.discovery.registry.peers(), ())
        self.discovery._try_start()
        self.assertEqual(self.backend.starts, 2)
        self.backend.availability.emit(True, 'active')
        self.assertTrue(self.discovery.available)

    def test_candidates_ignore_self_expire_and_never_select_strongest_of_two(self):
        counts = []
        self.discovery.peer_count_changed.connect(counts.append)
        self.discovery.start()
        self.backend.peer_seen.emit(b'local1', '000000000001', -30)
        self.backend.peer_seen.emit(b'other1', '000000000002', -45)
        self.backend.peer_seen.emit(b'other2', '000000000003', -100)
        self.assertIsNone(self.discovery.registry.candidate)
        self.assertEqual(counts, [1, 2])
        self.now = 13
        self.discovery._refresh_peers()
        self.assertEqual(counts, [1, 2, 0])

    def test_stop_ignores_late_callbacks_and_waits_for_native_cleanup(self):
        self.discovery.start()
        self.backend.cleanup_finished = False
        self.assertFalse(self.discovery.stop())
        self.backend.peer_seen.emit(b'other1', '000000000001', -60)
        self.backend.availability.emit(True, 'late event')
        self.discovery._try_start()
        self.assertEqual(self.backend.starts, 1)
        self.assertEqual(self.discovery.registry.peers(), ())
        self.assertFalse(self.discovery.available)
        self.backend.cleanup_finished = True
        self.assertTrue(self.discovery.stop())

    def test_unsupported_platform_never_starts_radio_or_retry_timer(self):
        discovery = NearbyDiscovery(backend_factory=FakeBackend, platform='darwin')
        try:
            discovery.start()
            self.assertEqual(discovery._backend.starts, 0)
            self.assertFalse(discovery._retry.isActive())
            self.assertFalse(discovery._expiry.isActive())
        finally:
            discovery.stop()
