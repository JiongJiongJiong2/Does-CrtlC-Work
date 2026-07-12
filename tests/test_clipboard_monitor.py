"""P3 剪贴板事件与图片 worker 的离屏回归测试。"""

import base64
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from core.clipboard_monitor import ClipboardMonitor, _ImageDataWorker


def app():
    return QApplication.instance() or QApplication([])


class ClipboardMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app()
        cls.clipboard = QGuiApplication.clipboard()

    def setUp(self):
        self.monitor = ClipboardMonitor()
        self.monitor._clipboard = self.clipboard
        self.monitor._is_monitoring = True

    def tearDown(self):
        self.monitor.stop_monitoring = lambda: None
        self.monitor._cancel_image_workers()

    def test_clipboard_event_emits_rich_copy_without_keyboard_polling(self):
        received = []
        self.monitor.copy_rich.connect(lambda text, images, count: received.append((text, images, count)))
        self.clipboard.setText('clipboard event')
        self.monitor._on_clipboard_changed()
        self.assertEqual(received, [('clipboard event', [], 0)])

    def test_sequence_number_deduplicates_duplicate_events(self):
        received = []
        self.monitor.copy_rich.connect(lambda *args: received.append(args))
        self.monitor._get_clipboard_sequence = lambda: 42
        self.monitor._last_sequence = 41
        self.clipboard.setText('one event')
        self.monitor._on_clipboard_changed()
        self.monitor._on_clipboard_changed()
        self.assertEqual(len(received), 1)

    def test_pending_ctrl_c_is_confirmed_by_clipboard_event(self):
        received = []
        self.monitor.copy_rich.connect(lambda *args: received.append(args))
        self.monitor._get_clipboard_sequence = lambda: 100
        self.monitor._last_sequence = 100
        self.monitor._handle_ctrl_c()
        self.assertTrue(self.monitor._confirmation_timer.isActive())
        self.monitor._get_clipboard_sequence = lambda: 101
        self.clipboard.setText('confirmed')
        self.monitor._on_clipboard_changed()
        self.assertIsNone(self.monitor._pending_copy_sequence)
        self.assertFalse(self.monitor._confirmation_timer.isActive())
        self.assertEqual(len(received), 1)


class ImageWorkerTests(unittest.TestCase):
    def test_data_uris_keep_source_order(self):
        first = b'first'
        second = b'second'
        first_uri = 'data:image/png;base64,' + base64.b64encode(first).decode()
        second_uri = 'data:image/png;base64,' + base64.b64encode(second).decode()
        worker = _ImageDataWorker(request_id=7, max_images=2)
        worker.set_tasks([], [first_uri, second_uri], [])
        received = []
        worker.raw_images_ready.connect(lambda request_id, raw: received.append((request_id, raw)))
        worker.run()
        self.assertEqual(received, [(7, [first, second])])

    def test_cancelled_worker_does_not_emit_stale_result(self):
        worker = _ImageDataWorker(request_id=8, max_images=1)
        worker.set_tasks([], ['data:image/png;base64,YQ=='], [])
        received = []
        worker.raw_images_ready.connect(lambda *args: received.append(args))
        worker.cancel()
        worker.run()
        self.assertEqual(received, [])
