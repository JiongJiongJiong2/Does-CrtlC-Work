"""Event-order and session ownership regressions, without OS hooks or networking."""

import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QByteArray, QObject, QMimeData, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from core.clipboard_monitor import ClipboardMonitor


def snapshot(text='copied'):
    return (text, [], 0, [], [], [], [])


class FakeClipboard(QObject):
    dataChanged = Signal()


class ClipboardSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.monitor = ClipboardMonitor()
        self.monitor._is_monitoring = True
        self.sequence = 100
        self.monitor._get_clipboard_sequence = lambda: self.sequence
        self.monitor._read_clipboard_snapshot = lambda: snapshot()
        self.events = []
        self.monitor.copy_rich.connect(lambda *args: self.events.append('copy'))
        self.monitor.copy_failed.connect(lambda: self.events.append('unconfirmed'))

    def tearDown(self):
        self.monitor.stop_monitoring()
        self.app.processEvents()

    def test_event_before_queued_intent_does_not_report_failure(self):
        with patch('core.clipboard_monitor.time.monotonic', return_value=10.1):
            self.monitor._on_clipboard_changed()
            self.monitor._handle_ctrl_c(10.0, 99, 0)
        self.monitor._on_confirmation_timeout()
        self.assertEqual(self.events, ['copy'])
        self.assertFalse(self.monitor._confirmation_timer.isActive())

    def test_keyboard_dispatch_after_event_consumes_recent_sequence_once(self):
        with patch('core.clipboard_monitor.time.monotonic', return_value=10.0):
            self.monitor._on_clipboard_changed()
        with patch('core.clipboard_monitor.time.monotonic', return_value=10.1):
            self.monitor._handle_ctrl_c(10.1, 100, 0)
        self.assertIsNone(self.monitor._pending_copy_sequence)
        # A separate copy intent cannot keep reusing the same observed event.
        with patch('core.clipboard_monitor.time.monotonic', return_value=10.2):
            self.monitor._handle_ctrl_c(10.2, 100, 0)
        self.monitor._on_confirmation_timeout()
        self.assertEqual(self.events, ['copy', 'unconfirmed'])

    def test_event_before_intent_without_native_sequence_is_correlated(self):
        self.sequence = 0
        with patch('core.clipboard_monitor.time.monotonic', return_value=10.0):
            self.monitor._on_clipboard_changed()
        with patch('core.clipboard_monitor.time.monotonic', return_value=10.1):
            self.monitor._handle_ctrl_c(10.1, 0, 0)
        self.monitor._on_confirmation_timeout()
        self.assertEqual(self.events, ['copy'])

    def test_unrelated_old_event_does_not_confirm_new_intent(self):
        with patch('core.clipboard_monitor.time.monotonic', return_value=10.0):
            self.monitor._on_clipboard_changed()
        with patch('core.clipboard_monitor.time.monotonic', return_value=11.0):
            self.monitor._handle_ctrl_c(11.0, 100, 0)
        self.monitor._on_confirmation_timeout()
        self.assertEqual(self.events, ['copy', 'unconfirmed'])

    def test_new_success_cancels_old_retry_and_duplicate_delivery(self):
        self.monitor._read_clipboard_snapshot = Mock(side_effect=[None, snapshot()])
        self.monitor._on_clipboard_changed()
        obsolete_session = self.monitor._image_request_id
        self.assertTrue(self.monitor._event_retry_timer.isActive())
        self.sequence += 1
        self.monitor._on_clipboard_changed()
        self.assertFalse(self.monitor._event_retry_timer.isActive())
        self.monitor._process_clipboard_event(obsolete_session)
        self.monitor._process_clipboard_event()
        self.assertEqual(self.events, ['copy'])
        self.assertEqual(self.monitor._read_clipboard_snapshot.call_count, 2)

    def test_new_unreadable_event_immediately_invalidates_old_images(self):
        received = []
        self.monitor.images_for_session.connect(lambda *args: received.append(args))
        self.monitor._on_clipboard_changed()
        old_session = self.monitor._image_request_id
        self.monitor._read_clipboard_snapshot = lambda: None
        self.sequence += 1
        self.monitor._on_clipboard_changed()
        self.monitor._on_images_ready(old_session, [object()], 1)
        self.assertEqual(received, [])
        self.assertNotEqual(old_session, self.monitor._image_request_id)

    def test_session_identity_is_carried_from_copy_to_image_result(self):
        received = []
        self.monitor.copy_session.connect(
            lambda session, *args: received.append(('copy', session)))
        self.monitor.images_for_session.connect(
            lambda session, *args: received.append(('image', session)))
        self.monitor._on_clipboard_changed()
        session = self.monitor._image_request_id
        self.monitor._on_images_ready(session, [object()], 1)
        self.assertEqual(received, [('copy', session), ('image', session)])

    def test_paste_invalidates_pending_images_and_copy_timeout(self):
        received = []
        self.monitor.images_updated.connect(lambda *args: received.append(args))
        self.monitor._handle_ctrl_c()
        session = self.monitor._image_request_id
        self.monitor._handle_ctrl_v()
        self.monitor._on_images_ready(session, [object()], 1)
        self.monitor._on_confirmation_timeout()
        self.assertEqual(received, [])
        self.assertEqual(self.events, [])

    def test_stopped_monitor_ignores_queued_images_and_keyboard_callbacks(self):
        received = []
        self.monitor.images_updated.connect(lambda *args: received.append(args))
        generation = self.monitor._lifecycle_generation
        session = self.monitor._image_request_id
        self.monitor.stop_monitoring()
        self.monitor._on_images_ready(session, [object()], 1)
        self.monitor._on_raw_ready(session, [b'ignored'], 1)
        self.monitor._handle_ctrl_c(10.0, 100, generation)
        self.monitor._handle_ctrl_v(generation)
        self.assertEqual(received, [])
        self.assertIsNone(self.monitor._pending_copy_sequence)

    def test_keyboard_callback_only_mutates_state_after_qt_delivery(self):
        callback = threading.Thread(target=self.monitor._capture_copy_intent)
        callback.start()
        callback.join(timeout=2)
        self.assertFalse(callback.is_alive())
        self.assertIsNone(self.monitor._pending_copy_sequence)
        self.app.processEvents()
        self.assertEqual(self.monitor._pending_copy_sequence, 100)
        self.assertTrue(self.monitor._confirmation_timer.isActive())

    def test_copy_callback_queued_before_paste_cannot_restart_failure_timer(self):
        self.monitor._handle_ctrl_v(0, 10.1)
        self.monitor._handle_ctrl_c(10.0, 100, 0)
        self.monitor._on_confirmation_timeout()
        self.assertEqual(self.events, [])
        self.assertFalse(self.monitor._confirmation_timer.isActive())

    def test_previous_registration_callback_is_ignored_after_restart(self):
        self.monitor._is_monitoring = False
        clipboard = FakeClipboard()
        callbacks = []

        def register(shortcut, callback, **kwargs):
            callbacks.append(callback)
            return callback

        with patch('core.clipboard_monitor.QGuiApplication',
                   SimpleNamespace(clipboard=lambda: clipboard)), \
                patch('core.clipboard_monitor.keyboard.add_hotkey', side_effect=register), \
                patch('core.clipboard_monitor.keyboard.remove_hotkey'):
            self.monitor.start_monitoring()
            old_copy_callback = callbacks[0]
            self.monitor.stop_monitoring()
            self.monitor.start_monitoring()
            old_copy_callback()
            self.app.processEvents()
            self.assertIsNone(self.monitor._pending_copy_sequence)
            self.monitor.stop_monitoring()

    def test_hook_failure_keeps_clipboard_connected_and_cleans_only_own_handle(self):
        self.monitor._is_monitoring = False
        clipboard = FakeClipboard()
        with patch('core.clipboard_monitor.QGuiApplication',
                   SimpleNamespace(clipboard=lambda: clipboard)), \
                patch('core.clipboard_monitor.keyboard.add_hotkey',
                      side_effect=['own-copy-handle', PermissionError('denied')]), \
                patch('core.clipboard_monitor.keyboard.remove_hotkey') as remove, \
                patch('core.clipboard_monitor.keyboard.unhook_all_hotkeys') as remove_all:
            self.monitor.start_monitoring()
            self.sequence += 1
            clipboard.dataChanged.emit()
            self.assertTrue(self.monitor._is_monitoring)
            self.assertEqual(self.events, ['copy'])
            self.assertTrue(self.monitor.stop_monitoring())
            remove.assert_called_once_with('own-copy-handle')
            remove_all.assert_not_called()

    def test_shutdown_can_be_retried_after_monitoring_stops(self):
        service = Mock()
        service.shutdown.side_effect = [False, True, True]
        self.monitor._preview_service = service
        self.assertFalse(self.monitor.stop_monitoring())
        self.assertTrue(self.monitor.stop_monitoring())
        self.assertEqual(service.shutdown.call_count, 2)

    def test_remote_url_preview_is_disabled_by_default(self):
        mime = QMimeData()
        mime.setText('https://example.invalid/private-link')
        self.monitor._clipboard = SimpleNamespace(mimeData=lambda: mime, dataChanged=Mock())
        result = ClipboardMonitor._read_clipboard_snapshot(self.monitor)
        self.assertEqual(result[2], 0)
        self.assertEqual(result[3], [])
        # Opting into HTML image fallback does not turn ordinary links into GETs.
        self.monitor._remote_previews = True
        result = ClipboardMonitor._read_clipboard_snapshot(self.monitor)
        self.assertEqual(result[2], 0)
        self.assertEqual(result[3], [])

    def test_bitmap_or_raw_representation_wins_over_files_and_html(self):
        for representation in ('bitmap', 'raw'):
            with self.subTest(representation=representation):
                mime = QMimeData()
                image = QImage(2, 2, QImage.Format.Format_ARGB32)
                image.fill(0)
                if representation == 'bitmap':
                    mime.setImageData(image)
                else:
                    mime.setData('image/png', QByteArray(b'clipboard-bytes'))
                mime.setUrls([QUrl.fromLocalFile('C:/copy/image.png')])
                mime.setHtml('<img src="data:image/png;base64,YQ==">'
                             '<img src="https://example.invalid/image.png">')
                self.monitor._remote_previews = True
                self.monitor._clipboard = SimpleNamespace(
                    mimeData=lambda: mime,
                    image=lambda: image if representation == 'bitmap' else QImage(),
                    dataChanged=Mock())
                result = ClipboardMonitor._read_clipboard_snapshot(self.monitor)
                self.assertEqual(result[2], 1)
                self.assertEqual(result[3:6], ([], [], []))
                self.assertEqual(len(result[1]) + len(result[6]), 1)

    def test_local_file_list_wins_over_html_and_keeps_distinct_files(self):
        mime = QMimeData()
        first = QUrl.fromLocalFile('C:/copy/first.png')
        second = QUrl.fromLocalFile('C:/copy/second.png')
        mime.setUrls([first, second, first])
        mime.setHtml('<img src="data:image/png;base64,YQ==">'
                     '<img src="https://example.invalid/first.png">')
        self.monitor._remote_previews = True
        self.monitor._clipboard = SimpleNamespace(mimeData=lambda: mime, dataChanged=Mock())
        result = ClipboardMonitor._read_clipboard_snapshot(self.monitor)
        self.assertEqual(result[2], 2)
        self.assertEqual(result[3:5], ([], []))
        self.assertEqual(result[5], [first.toLocalFile(), second.toLocalFile()])

    def test_html_keeps_distinct_sources_and_deduplicates_repeated_src(self):
        mime = QMimeData()
        data = 'data:image/png;base64,YQ=='
        first = 'https://example.invalid/first.png'
        second = 'https://example.invalid/second.png'
        mime.setHtml(''.join(f'<img src="{source}">'
                             for source in (data, first, first, second, data)))
        self.monitor._remote_previews = True
        self.monitor._clipboard = SimpleNamespace(mimeData=lambda: mime, dataChanged=Mock())
        result = ClipboardMonitor._read_clipboard_snapshot(self.monitor)
        self.assertEqual(result[2], 3)
        self.assertEqual(result[3], [first, second])
        self.assertEqual(result[4], [data])
        self.assertEqual(result[5], [])


if __name__ == '__main__':
    unittest.main()
