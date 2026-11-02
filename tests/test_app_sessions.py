"""UI command threading and copy-session regressions, without global hooks."""

import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from main import ClipboardFXApp, _NavigationBridge
from ui.feedback_widget import FeedbackWidget, FeedbackType


class AppSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_external_command_runs_only_on_gui_thread(self):
        observed = []
        bridge = _NavigationBridge(lambda value: observed.append((value, threading.get_ident())))
        worker = threading.Thread(target=lambda: bridge.requested.emit('silent'))
        worker.start()
        worker.join()
        self.assertEqual(observed, [])
        self.app.processEvents()
        self.assertEqual(observed, [('silent', threading.get_ident())])

    def test_stale_images_cannot_enter_another_session(self):
        observed = []
        controller = SimpleNamespace(_feedback_session_id=22,
                                     _on_images_updated=lambda *args: observed.append(args))
        ClipboardFXApp._on_session_images(controller, 21, ['old'], 1)
        self.assertEqual(observed, [])
        ClipboardFXApp._on_session_images(controller, 22, ['current'], 1)
        self.assertEqual(observed, [(['current'], 1)])

    def test_paste_widget_refuses_image_update(self):
        image = QImage(4, 4, QImage.Format_ARGB32)
        image.fill(0xFFFFFFFF)
        widget = FeedbackWidget(FeedbackType.PASTE)
        widget.update_images([image], 1)
        self.assertEqual(widget._images, [])
        widget.stop()

    def test_images_deduplicate_original_source_and_cap_total(self):
        images = []
        for color in range(8):
            image = QImage(4, 4, QImage.Format_ARGB32)
            image.fill(0xFF000000 + color)
            images.append(image)
        widget = FeedbackWidget(FeedbackType.COPY, images=[images[0]], image_count=1)
        widget.update_images([images[0]], 1)
        self.assertEqual(len(widget._images), 1)
        widget.update_images(images[1:4], 4)
        widget.update_images(images[4:], 8)
        self.assertEqual(len(widget._images), 4)
        widget.stop()

    def test_navigation_does_not_register_bare_arrow_keys(self):
        controller = ClipboardFXApp.__new__(ClipboardFXApp)
        controller._navigation_hotkeys = []
        controller._navigation_bridge = _NavigationBridge(lambda _: None)
        with patch('main.keyboard.add_hotkey', return_value='handle') as add:
            controller._register_navigation_hotkeys()
        self.assertEqual([call.args[0] for call in add.call_args_list],
                         ['ctrl+alt+left', 'ctrl+alt+right', 'ctrl+alt+up', 'ctrl+alt+down'])

    def test_quit_keeps_qt_alive_until_preview_cleanup_finishes(self):
        controller = ClipboardFXApp.__new__(ClipboardFXApp)
        controller.clipboard_monitor = Mock()
        controller.clipboard_monitor.shutdown_preview.side_effect = [False, True]
        controller.tray = Mock()
        controller.app = Mock()
        with patch('main.QTimer.singleShot') as schedule:
            controller._finish_quit()
            controller.app.quit.assert_not_called()
            controller.tray.hide.assert_not_called()
            schedule.assert_called_once()
            controller._finish_quit()
        controller.app.quit.assert_called_once()
        controller.tray.hide.assert_called_once()
