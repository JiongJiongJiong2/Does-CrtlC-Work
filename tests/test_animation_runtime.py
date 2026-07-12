"""P0–P2 动画回归测试；运行前设定 QT_QPA_PLATFORM=offscreen。"""

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from config import ANIMATION_DURATION, SIZES
from core.mouse_tracker import MouseTracker
from ui.animation.property_engine import PropertyEngine
from ui.animation.spring_ease import spring_ease
from ui.animation.state_machine import AnimationState, AnimationStateMachine
from ui.components.content_box import ContentBox
from ui.feedback_widget import FeedbackType, FeedbackWidget
from ui.text_style import TextStyleResolver


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

    def test_idle_animation_clock_and_mouse_tracker_have_no_background_timer(self):
        engine = PropertyEngine()
        self.assertFalse(engine._timer.isActive())
        engine.set_frame_active('test', True)
        self.assertTrue(engine._timer.isActive())
        engine.set_frame_active('test', False)
        self.assertFalse(engine._timer.isActive())

        tracker = MouseTracker()
        self.assertFalse(hasattr(tracker, 'poll_timer'))
        self.assertFalse(hasattr(tracker, 'update_timer'))

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
