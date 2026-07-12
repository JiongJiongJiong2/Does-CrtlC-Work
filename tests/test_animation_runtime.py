"""P0–P2 动画回归测试；运行前设定 QT_QPA_PLATFORM=offscreen。"""

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from config import ANIMATION_DURATION
from core.mouse_tracker import MouseTracker
from ui.animation.property_engine import PropertyEngine
from ui.animation.spring_ease import spring_ease
from ui.animation.state_machine import AnimationState, AnimationStateMachine
from ui.feedback_widget import FeedbackType, FeedbackWidget


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
