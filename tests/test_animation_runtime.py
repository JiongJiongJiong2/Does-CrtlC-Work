"""P0–P2 动画回归测试；运行前设定 QT_QPA_PLATFORM=offscreen。"""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from config import ANIMATION_DURATION, SIZES
from core.mouse_tracker import MouseTracker, SpringAnimator
from ui.animation.property_engine import PropertyEngine
from ui.animation.spring_ease import spring_ease
from ui.animation.state_machine import AnimationState, AnimationStateMachine
from ui.components.content_box import ContentBox
from ui.feedback_widget import FeedbackType, FeedbackWidget
from ui.image_layout import IMAGE_LAYOUT_CASCADE, IMAGE_LAYOUT_FAN
from ui.text_style import TextStyleResolver
from ui.tray_menu import TrayMenuPopup, create_tray_menu
from ui.windows_tray_menu import (
    ID_FEEDBACK,
    ID_HOLDING,
    ID_IMAGE_LAYOUT,
    ID_LANGUAGE,
    ID_QUIT,
    WindowsNativeTrayMenu,
)
from main import ClipboardFXApp


def core_app():
    return QApplication.instance() or QApplication([])


class AnimationStateTests(unittest.TestCase):
    def test_error_and_paste_use_short_pulse_path(self):
        core_app()
        state_machine = AnimationStateMachine()
        self.assertTrue(state_machine.transition('start'))
        self.assertTrue(state_machine.transition('done_error_paste'))
        self.assertEqual(state_machine.state, AnimationState.PULSE)
        self.assertTrue(state_machine.transition('timeout'))
        self.assertEqual(state_machine.state, AnimationState.DOT_DISAPPEAR)

    def test_image_and_stack_can_exit_while_appearing(self):
        core_app()
        state_machine = AnimationStateMachine()
        state_machine.transition('start')
        state_machine.transition('done_copy_no_text')
        self.assertEqual(state_machine.state, AnimationState.IMAGE_APPEAR)
        self.assertTrue(state_machine.transition('exit_no_stack'))
        self.assertEqual(state_machine.state, AnimationState.IMAGE_VANISH)

        state_machine.reset()
        state_machine.transition('start')
        state_machine.transition('done_copy_no_text')
        state_machine.transition('done_multi_image')
        self.assertEqual(state_machine.state, AnimationState.STACK_APPEAR)
        self.assertTrue(state_machine.transition('exit_has_stack'))
        self.assertEqual(state_machine.state, AnimationState.STACK_RETRACT)

    def test_spring_uses_normalized_time_not_old_from_to_signature(self):
        self.assertEqual(spring_ease(0.0), 0.0)
        self.assertGreater(spring_ease(0.5), 0.0)
        self.assertGreater(spring_ease(1.0), 0.9)

    def test_horizontal_follow_drags_left_but_pushes_right(self):
        spring = SpringAnimator(stiffness=500, damping=40)
        spring.reset(100, 100)
        spring.set_target(80, 100)
        left_x, _ = spring.step(0.008)
        self.assertGreater(left_x, 80)
        self.assertLess(left_x, 100)

        spring.set_target(90, 100)
        right_x, _ = spring.step(0.008)
        self.assertEqual(right_x, 90)
        self.assertEqual(spring.velocity_x, 0)


class FeedbackRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_widget_has_one_frame_clock_and_pulse_completes(self):
        widget = FeedbackWidget(FeedbackType.ERROR)
        completed = []
        widget.animation_complete.connect(lambda: completed.append(True))
        widget.start_animation()
        QTimer.singleShot(1300, self.app.quit)
        self.app.exec()
        self.assertEqual(completed, [True])
        self.assertFalse(widget._active)
        self.assertFalse(hasattr(widget, '_stack_anim_timer'))
        self.assertFalse(hasattr(widget, '_scramble_timer'))
        self.assertFalse(hasattr(widget, '_image_scramble_timer'))

    def test_holding_marker_only_applies_to_copy_feedback(self):
        copy_widget = FeedbackWidget(FeedbackType.COPY, holding_mode=True)
        paste_widget = FeedbackWidget(FeedbackType.PASTE, holding_mode=True)
        normal_copy = FeedbackWidget(FeedbackType.COPY, holding_mode=False)
        self.assertTrue(copy_widget.is_holding_copy)
        self.assertFalse(paste_widget.is_holding_copy)
        self.assertFalse(normal_copy.is_holding_copy)


class TrayAndHoldingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_normal_paste_shows_green_feedback_but_holding_paste_exits(self):
        class Widget:
            def __init__(self, holding):
                self._active = True
                self.is_holding_copy = holding
                self.exited = False

            def start_exit(self):
                self.exited = True

        class AppHarness:
            def __init__(self, widget):
                self._current_widget = widget
                self.shown = []

            def _show_feedback(self, feedback_type):
                self.shown.append(feedback_type)

        normal = AppHarness(Widget(False))
        ClipboardFXApp._on_paste(normal)
        self.assertFalse(normal._current_widget.exited)
        self.assertEqual(normal.shown, [FeedbackType.PASTE])

        holding = AppHarness(Widget(True))
        ClipboardFXApp._on_paste(holding)
        self.assertTrue(holding._current_widget.exited)
        self.assertEqual(holding.shown, [])

    def test_tray_popup_uses_compact_switches_and_language_marker(self):
        popup = TrayMenuPopup('zh')
        popup.set_state(feedback_enabled=True, holding_enabled=False,
                        image_layout_mode=IMAGE_LAYOUT_CASCADE)
        self.assertTrue(popup.feedback_switch.isChecked())
        self.assertFalse(popup.holding_switch.isChecked())
        self.assertEqual(popup.btn_en.text(), 'EN')
        self.assertEqual(popup.btn_zh.text(), '中')
        self.assertEqual(popup.image_layout_selector.mode,
                         IMAGE_LAYOUT_CASCADE)
        self.assertLessEqual(popup.sizeHint().width(), 280)
        popup.set_language('en')
        self.assertEqual(popup.holding_label.text(), 'Dismiss on Ctrl+V')

    def test_tray_quit_action_keeps_localized_text(self):
        popup = TrayMenuPopup('zh')
        self.assertEqual(popup.quit_button.text(), '退出')
        popup.set_language('en')
        self.assertEqual(popup.quit_button.text(), 'Quit')

    def test_tray_popup_uses_standard_qmenu_lifecycle(self):
        popup = TrayMenuPopup('zh')
        self.assertIsInstance(popup, QMenu)
        self.assertEqual(
            popup.testAttribute(Qt.WA_ShowWithoutActivating),
            sys.platform.startswith('win'))
        self.assertFalse(hasattr(popup, '_overflow_idle_timer'))
        self.assertFalse(hasattr(popup, '_outside_click_timer'))
        popup.popup(QPoint(100, 100))
        QApplication.processEvents()
        self.assertTrue(popup.isVisible())
        QTest.keyClick(popup, Qt.Key_Escape)
        QApplication.processEvents()
        self.assertFalse(popup.isVisible())

    def test_tray_controls_do_not_trigger_menu_action(self):
        popup = TrayMenuPopup('zh')
        popup.popup(QPoint(100, 100))
        QApplication.processEvents()
        popup.feedback_switch.click()
        QApplication.processEvents()
        self.assertTrue(popup.isVisible())
        popup.close()

    def test_image_layout_selector_toggles_without_text_button(self):
        popup = TrayMenuPopup('zh')
        changed = []
        popup.image_layout_changed.connect(changed.append)
        self.assertEqual(popup.image_layout_selector.mode, IMAGE_LAYOUT_FAN)
        popup.image_layout_selector.click()
        self.assertEqual(changed, [IMAGE_LAYOUT_CASCADE])
        self.assertEqual(popup.image_layout_selector.mode,
                         IMAGE_LAYOUT_CASCADE)
        self.assertEqual(popup.image_layout_selector.text(), '')

    def test_system_tray_uses_manual_nonactivating_context_path(self):
        app = ClipboardFXApp.__new__(ClipboardFXApp)
        app._language = 'zh'
        app.silent_mode = False
        app._holding_mode = False
        app._setup_tray()
        self.assertIsNone(app.tray.contextMenu())
        if sys.platform.startswith('win'):
            self.assertIsInstance(app.tray_menu, WindowsNativeTrayMenu)
        app.tray_menu.close()
        app.tray.deleteLater()

    def test_windows_native_menu_factory_and_commands(self):
        menu = create_tray_menu('zh')
        if not sys.platform.startswith('win'):
            self.assertIsInstance(menu, TrayMenuPopup)
            return
        self.assertIsInstance(menu, WindowsNativeTrayMenu)
        feedback = []
        holding = []
        languages = []
        layouts = []
        quitting = []
        menu.feedback_toggled.connect(feedback.append)
        menu.holding_toggled.connect(holding.append)
        menu.language_toggled.connect(languages.append)
        menu.image_layout_changed.connect(layouts.append)
        menu.quit_requested.connect(lambda: quitting.append(True))
        menu._apply_command(ID_FEEDBACK)
        menu._apply_command(ID_HOLDING)
        menu._apply_command(ID_LANGUAGE)
        menu._apply_command(ID_IMAGE_LAYOUT)
        menu._apply_command(ID_QUIT)
        self.assertEqual(feedback, [False])
        self.assertEqual(holding, [True])
        self.assertEqual(languages, ['en'])
        self.assertEqual(layouts, [IMAGE_LAYOUT_CASCADE])
        self.assertEqual(quitting, [True])
        menu.close()

    def test_context_and_left_click_open_the_same_menu(self):
        class Menu:
            def __init__(self):
                self.shown = 0

            def isVisible(self):
                return False

            def show_near_tray(self, tray):
                self.shown += 1

        app = ClipboardFXApp.__new__(ClipboardFXApp)
        app.tray = object()
        app.tray_menu = Menu()
        app._on_tray_activated(QSystemTrayIcon.ActivationReason.Context)
        app._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
        self.assertEqual(app.tray_menu.shown, 2)

    def test_image_layout_setting_is_normalized_persisted_and_synced(self):
        class Settings:
            def __init__(self):
                self.values = {}

            def setValue(self, key, value):
                self.values[key] = value

        class Tray:
            def setToolTip(self, text):
                self.tooltip = text

        class Menu:
            def set_state(self, feedback, holding, mode):
                self.state = feedback, holding, mode

        app = ClipboardFXApp.__new__(ClipboardFXApp)
        app._settings = Settings()
        app.tray = Tray()
        app.tray_menu = Menu()
        app.silent_mode = False
        app._holding_mode = False
        ClipboardFXApp._set_image_layout_mode(app, 'unknown')
        self.assertEqual(app._image_layout_mode, IMAGE_LAYOUT_FAN)
        self.assertEqual(app._settings.values['image_layout_mode'],
                         IMAGE_LAYOUT_FAN)
        self.assertEqual(app.tray_menu.state, (True, False, IMAGE_LAYOUT_FAN))

    def test_copy_full_exit_keeps_the_two_pixel_line_phase(self):
        original = ANIMATION_DURATION.copy()
        ANIMATION_DURATION.update({
            'dot_appear': 10,
            'box_expand': 10,
            'text_scramble': 10,
            'view_time': 10,
            'box_shrink': 10,
            'line_shrink': 10,
            'dot_disappear': 10,
        })
        try:
            widget = FeedbackWidget(FeedbackType.COPY, text='copy')
            widths = []
            widget.frame_tick.connect(lambda _: widths.append(widget._box_width))
            widget.start_animation()
            QTimer.singleShot(600, self.app.quit)
            self.app.exec()
            self.assertFalse(widget._active)
            self.assertTrue(any(1.5 <= width <= 2.5 for width in widths))
        finally:
            ANIMATION_DURATION.clear()
            ANIMATION_DURATION.update(original)

    def test_image_reveal_and_stack_thumbnails_are_prebuilt(self):
        image = QImage(16, 16, QImage.Format_ARGB32)
        image.fill(0xFFFFFFFF)
        widget = FeedbackWidget(FeedbackType.COPY, images=[image, image.copy()], image_count=2)
        self.assertIsNotNone(widget._main_image_cache)
        self.assertEqual(len(widget._main_image_cache.reveal_frames), 25)
        self.assertEqual(len(widget._stack_thumbnail_cache), 2)

    def test_layout_modes_keep_four_images_preloaded_but_use_own_limits(self):
        images = []
        for color in (0xFFFF0000, 0xFF00FF00, 0xFF0000FF,
                      0xFFFFFF00, 0xFFFF00FF):
            image = QImage(16, 16, QImage.Format_ARGB32)
            image.fill(color)
            images.append(image)
        fan = FeedbackWidget(
            FeedbackType.COPY, images=images, image_count=5,
            image_layout_mode=IMAGE_LAYOUT_FAN)
        cascade = FeedbackWidget(
            FeedbackType.COPY, images=images, image_count=5,
            image_layout_mode=IMAGE_LAYOUT_CASCADE)
        self.assertEqual(fan._image_count, 3)
        self.assertEqual(cascade._image_count, 4)
        self.assertEqual(len(fan._images), 4)
        self.assertEqual(len(cascade._image_render_caches), 4)
        self.assertEqual(len(cascade._image_render_caches[1].reveal_frames), 1)

    def test_animation_and_motion_clocks_stop_while_idle(self):
        engine = PropertyEngine()
        self.assertEqual(engine._timer.interval(), 8)
        self.assertFalse(engine._timer.isActive())
        engine.set_frame_active('test', True)
        self.assertTrue(engine._timer.isActive())
        engine.set_frame_active('test', False)
        self.assertFalse(engine._timer.isActive())

        tracker = MouseTracker()
        self.assertEqual(tracker._motion_timer.interval(), 8)
        self.assertFalse(tracker._motion_timer.isActive())
        tracker.start_tracking()
        self.assertTrue(tracker._motion_timer.isActive())
        tracker.stop_tracking()
        self.assertFalse(tracker._motion_timer.isActive())

    def test_active_motion_clock_updates_at_high_frequency(self):
        tracker = MouseTracker()
        ticks = []
        tracker.spring_position_changed.connect(lambda *_: ticks.append(True))
        tracker.start_tracking()
        QTimer.singleShot(120, self.app.quit)
        self.app.exec()
        tracker.stop_tracking()
        # Allow scheduling headroom on a busy test host while still proving
        # the active 8ms motion clock is receiving regular callbacks.
        self.assertGreaterEqual(len(ticks), 9)

    def test_script_aware_style_uses_ui_font_without_cjk_tracking(self):
        chinese = TextStyleResolver.resolve('复制中文测试')
        mixed = TextStyleResolver.resolve('Copy 中文 mixed')
        latin = TextStyleResolver.resolve('Copy text')
        emoji = TextStyleResolver.resolve('✅ copied')
        self.assertEqual(chinese.kind, 'ui_cjk')
        self.assertEqual(mixed.kind, 'ui_cjk')
        self.assertEqual(emoji.kind, 'ui_emoji')
        self.assertEqual(chinese.font.letterSpacing(), 0.0)
        self.assertGreater(latin.font.letterSpacing(), 0.0)

    def test_cjk_widget_uses_metrics_width_and_incremental_60fps_scramble(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='复制中文和 English 混排文本')
        expected = max(
            SIZES['box_min_width'],
            min(SIZES['box_max_width'],
                widget._text_style.horizontal_advance(widget._text) + SIZES['box_padding']))
        self.assertEqual(widget._target_width, expected)
        self.assertIsNotNone(widget._final_text_layout)

        widget._scramble_start_ms = 0
        widget._advance_text_scramble(0)
        first_refresh = widget._last_scramble_refresh_ms
        widget._advance_text_scramble(10)
        self.assertEqual(widget._last_scramble_refresh_ms, first_refresh)
        widget._advance_text_scramble(16)
        self.assertEqual(widget._last_scramble_refresh_ms, 16)
        self.assertEqual(len(widget._scramble_buffer), len(widget._text))

        widget._advance_text_scramble(600)
        solved_count = widget._scramble_solved_count
        self.assertGreater(solved_count, 0)
        solved_prefix = widget._scramble_buffer[:solved_count]
        widget._advance_text_scramble(616)
        self.assertEqual(widget._scramble_buffer[:solved_count], solved_prefix)

    def test_long_cjk_text_elides_and_cached_layout_paints(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='中文' * 100)
        self.assertLessEqual(widget._target_width, SIZES['box_max_width'])
        self.assertTrue(widget._text.endswith('…'))

        canvas = QImage(500, 80, QImage.Format_ARGB32)
        canvas.fill(0)
        painter = QPainter(canvas)
        ContentBox.paint(painter, 5, 5, widget._target_width, 28, 1.0,
                         widget._text, 1.0, widget._text_style,
                         widget._final_text_layout)
        painter.end()
