"""Cursor-size adaptation and unified-coordinate regression tests."""

import ctypes
import math
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from core.cursor_metrics import CursorMetrics, cursor_ui_scale
from core.taskbar_boundary import TaskbarBoundary
from ui.feedback_layout import (DOT_CX, bottom_dock_dot_y,
                                clamp_window_position, dock_feedback_position,
                                edge_dock_required, image_base_pos,
                                visible_content_bounds, window_size)
from ui.image_layout import cascade_layer_offset
from ui.feedback_widget import FeedbackType, FeedbackWidget


class CursorMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_scale_uses_stable_buckets_and_caps_at_one_point_five(self):
        self.assertEqual(cursor_ui_scale(32), 1.0)
        self.assertEqual(cursor_ui_scale(40), 1.0)
        self.assertEqual(cursor_ui_scale(48), 1.15)
        self.assertEqual(cursor_ui_scale(64), 1.30)
        self.assertEqual(cursor_ui_scale(96), 1.50)
        self.assertEqual(cursor_ui_scale(512), 1.50)

    def test_large_cursor_offset_grows_separately_and_is_capped(self):
        default = CursorMetrics.from_dip(32, 32)
        large = CursorMetrics.from_dip(96, 96)
        extreme = CursorMetrics.from_dip(512, 512)
        centered = CursorMetrics.from_dip(96, 96, 48, 48)
        self.assertEqual((default.offset_x, default.offset_y), (16.0, 16.0))
        self.assertGreater(large.offset_x, default.offset_x)
        self.assertLess(centered.offset_x, large.offset_x)
        self.assertEqual((extreme.offset_x, extreme.offset_y), (160.0, 160.0))
        self.assertGreater(large.offset_x, large.width_dip)

    def test_windows_accessibility_size_overrides_unchanged_cursor_resource(self):
        with patch('core.cursor_metrics.sys.platform', 'win32'), \
                patch.object(CursorMetrics, '_read_windows_cursor',
                             return_value=(32, 32, 0, 0)), \
                patch.object(CursorMetrics, '_read_windows_cursor_base_size',
                             return_value=128.0):
            metrics = CursorMetrics.detect()
        self.assertEqual((metrics.width_dip, metrics.height_dip), (128.0, 128.0))
        self.assertEqual(metrics.ui_scale, 1.5)
        self.assertGreater(metrics.offset_x, metrics.width_dip)
        self.assertGreater(metrics.offset_y, metrics.height_dip)

    def test_non_windows_detection_falls_back_without_native_calls(self):
        with patch('core.cursor_metrics.sys.platform', 'linux'):
            metrics = CursorMetrics.detect()
        self.assertEqual(metrics.ui_scale, 1.0)
        self.assertEqual((metrics.offset_x, metrics.offset_y), (16.0, 16.0))

    def test_clamp_keeps_scaled_canvas_inside_available_geometry(self):
        self.assertEqual(
            clamp_window_position(1800, 1000, 750, 270, (0, 0, 1920, 1080)),
            (1170, 810))
        self.assertEqual(
            clamp_window_position(-500, -300, 750, 270, (0, 0, 1920, 1080)),
            (0, 0))

    def test_bottom_docking_uses_visible_content_and_keeps_horizontal_following(self):
        right, bottom = visible_content_bounds(220, False)
        first = dock_feedback_position(
            500, 1050, 500, 1.0, 16, 16, right, bottom, (0, 0, 1920, 1080))
        second = dock_feedback_position(
            650, 1050, 500, 1.0, 16, 16, right, bottom, (0, 0, 1920, 1080))
        self.assertEqual(first[1], 1080 - 12 - int(bottom))
        self.assertEqual(second[1], first[1])
        self.assertGreater(second[0], first[0])
        self.assertFalse(first[2])

    def test_right_docking_places_visible_anchor_at_safe_edge_and_mirrors(self):
        right, bottom = visible_content_bounds(450, False)
        window_x, _, mirrored = dock_feedback_position(
            1500, 300, 500, 1.0, 16, 16, right, bottom, (0, 0, 1920, 1080))
        self.assertTrue(mirrored)
        self.assertEqual(window_x + 500, 1920 - 12)
        self.assertEqual(window_x + 500 - DOT_CX, 1920 - 12 - DOT_CX)

    def test_edge_docking_uses_hysteresis_before_returning_to_normal(self):
        boundary = 1920
        self.assertTrue(edge_dock_required(1910, boundary, False))
        self.assertTrue(edge_dock_required(1900, boundary, True))
        self.assertFalse(edge_dock_required(1894, boundary, True))

    def test_image_position_interpolates_between_normal_and_mirrored_above(self):
        normal = image_base_pos(DOT_CX, 5, 120)
        middle = image_base_pos(
            250, 83, 120, horizontal_progress=0.5,
            vertical_progress=0.5)
        docked = image_base_pos(
            495, 161, 120, horizontal_progress=1.0,
            vertical_progress=1.0)
        self.assertEqual(normal, (5.0, 41.0))
        self.assertEqual(middle, (190.0, 37.0))
        self.assertEqual(docked, (375.0, 33.0))

    def test_bottom_docked_image_stack_opens_above_the_content_box(self):
        dot_y = bottom_dock_dot_y(image_count=3)
        _, image_y = image_base_pos(
            DOT_CX, dot_y, target_width=120, image_above=True)
        _, bottom = visible_content_bounds(
            120, True, image_count=3, dot_cy=dot_y, image_above=True)
        self.assertLess(image_y + 120, dot_y)
        self.assertEqual(bottom, dot_y + 28)

    def test_cascade_uses_four_horizontal_slots_and_reverses_at_right_dock(self):
        self.assertEqual(cascade_layer_offset(0, 4, 0.0), 0.0)
        self.assertEqual(cascade_layer_offset(3, 4, 0.0), 60.0)
        self.assertEqual(cascade_layer_offset(0, 4, 1.0), 0.0)
        self.assertEqual(cascade_layer_offset(3, 4, 1.0), -60.0)
        fan_right, _ = visible_content_bounds(120, True, image_count=3)
        cascade_right, _ = visible_content_bounds(
            120, True, image_count=4, image_layout_mode='cascade')
        self.assertGreater(cascade_right, fan_right)
        self.assertLess(bottom_dock_dot_y(4, 'cascade'),
                        bottom_dock_dot_y(3, 'fan'))

    def test_autohide_taskbar_uses_visible_top_but_ignores_hidden_strip(self):
        class Rect:
            def __init__(self, x, y, width, height):
                self._values = x, y, width, height

            def x(self): return self._values[0]
            def y(self): return self._values[1]
            def width(self): return self._values[2]
            def height(self): return self._values[3]

        class Screen:
            def geometry(self): return Rect(0, 0, 1920, 1080)
            def availableGeometry(self): return Rect(0, 0, 1920, 1080)

        screen = Screen()
        with patch('core.taskbar_boundary.sys.platform', 'win32'), \
                patch.object(TaskbarBoundary, '_windows_autohide_top',
                             return_value=(0, 1080, 1032)):
            self.assertEqual(TaskbarBoundary.effective_bottom(screen, 1), 1032)
        with patch('core.taskbar_boundary.sys.platform', 'win32'), \
                patch.object(TaskbarBoundary, '_windows_autohide_top',
                             return_value=(0, 1080, 1078)):
            self.assertEqual(TaskbarBoundary.effective_bottom(screen, 1), 1080)

    def test_taskbar_native_failure_never_escapes_mouse_move_path(self):
        failing = Mock()
        failing.MonitorFromWindow.return_value = 1
        failing.GetMonitorInfoW.side_effect = ctypes.ArgumentError('bad type')
        libraries = Mock(user32=failing, shell32=Mock())
        with patch('core.taskbar_boundary.ctypes.windll', libraries):
            self.assertIsNone(TaskbarBoundary._windows_autohide_top(1))


class ScaledFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_default_size_is_unchanged_and_scaled_canvas_matches_painter(self):
        normal = FeedbackWidget(FeedbackType.COPY, text='copy', ui_scale=1.0)
        scaled = FeedbackWidget(FeedbackType.COPY, text='copy', ui_scale=1.5)
        expected_normal = window_size(normal._target_width, False, 1.0)
        expected_scaled = tuple(math.ceil(value * 1.5) for value in expected_normal)
        self.assertEqual((normal.width(), normal.height()), expected_normal)
        self.assertEqual((scaled.width(), scaled.height()), expected_scaled)

    def test_scaled_stack_keeps_outer_transform_and_does_not_misalign(self):
        image = QImage(32, 32, QImage.Format_ARGB32)
        image.fill(0xFFFFFFFF)
        widget = FeedbackWidget(
            FeedbackType.COPY,
            images=[image, image.copy()],
            image_count=2,
            ui_scale=1.5,
        )
        widget._dot_scale = 1.0
        widget._image_scramble_progress = 1.0
        widget._stack_progress = 1.0
        canvas = QImage(widget.size(), QImage.Format_ARGB32)
        canvas.fill(0)
        widget.render(canvas)

        # Main image ends around x=188 at 1.5x. A visible pixel farther right
        # belongs to the scaled stack layer; if StackLayer overwrites the outer
        # transform, this area remains transparent.
        self.assertGreater(canvas.pixelColor(200, 100).alpha(), 0)

    def test_scaled_four_image_cascade_keeps_its_horizontal_tail_visible(self):
        images = []
        for color in (0xFFFF0000, 0xFF00FF00, 0xFF0000FF, 0xFFFFFF00):
            image = QImage(32, 32, QImage.Format_ARGB32)
            image.fill(color)
            images.append(image)
        widget = FeedbackWidget(
            FeedbackType.COPY, images=images, image_count=4,
            image_layout_mode='cascade', ui_scale=1.5)
        widget._dot_scale = 1.0
        widget._image_scramble_progress = 1.0
        widget._stack_progress = 1.0
        canvas = QImage(widget.size(), QImage.Format_ARGB32)
        canvas.fill(0)
        widget.render(canvas)
        # The fourth card ends near 278 physical px. This point is outside the
        # 180px-wide scaled front card and therefore proves the tail scaled too.
        self.assertGreater(canvas.pixelColor(260, 100).alpha(), 0)

    def test_right_dock_draws_yellow_anchor_on_the_right_without_mirroring_text(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='copy')
        widget._dock_right = True
        widget._dot_scale = 1.0
        widget._box_width = widget._target_width
        widget._box_opacity = 1.0
        canvas = QImage(widget.size(), QImage.Format_ARGB32)
        canvas.fill(0)
        widget.render(canvas)
        # The 2px pen is centered on the canvas edge, so inspect its inner
        # pixel rather than the clipped outer half.
        right_line_x = widget.width() - DOT_CX - 1
        self.assertGreater(canvas.pixelColor(right_line_x, 20).alpha(), 0)
        self.assertEqual(canvas.pixelColor(DOT_CX, 20).alpha(), 0)
        left_box_edge = int(widget.width() - DOT_CX - widget._box_width)
        # The gradient may leave a very faint black alpha here, but it must
        # not be the duplicate yellow anchor line from the old mirror path.
        self.assertLess(canvas.pixelColor(left_box_edge, 20).red(), 100)

    def test_right_dock_mirrors_image_and_stack_to_the_left(self):
        image = QImage(32, 32, QImage.Format_ARGB32)
        image.fill(0xFFFFFFFF)
        widget = FeedbackWidget(
            FeedbackType.COPY,
            images=[image, image.copy()],
            image_count=2,
        )
        widget._dock_right = True
        widget._dot_scale = 1.0
        widget._image_scramble_progress = 1.0
        widget._stack_progress = 1.0
        canvas = QImage(widget.size(), QImage.Format_ARGB32)
        canvas.fill(0)
        widget.render(canvas)
        self.assertGreater(canvas.pixelColor(widget.width() - 80, 70).alpha(), 0)
        self.assertEqual(canvas.pixelColor(100, 70).alpha(), 0)

    def test_bottom_dock_draws_image_above_content_without_bottom_overflow(self):
        image = QImage(32, 32, QImage.Format_ARGB32)
        image.fill(0xFFFFFFFF)
        widget = FeedbackWidget(
            FeedbackType.COPY, text='copy', images=[image, image.copy()],
            image_count=2,
        )
        widget._dock_bottom = True
        widget._dot_scale = 1.0
        widget._box_width = widget._target_width
        widget._box_opacity = 1.0
        widget._image_scramble_progress = 1.0
        widget._stack_progress = 1.0
        canvas = QImage(widget.size(), QImage.Format_ARGB32)
        canvas.fill(0)
        widget.render(canvas)
        self.assertGreater(canvas.pixelColor(15, 60).alpha(), 0)
        self.assertGreater(canvas.pixelColor(20, 155).alpha(), 0)
        self.assertEqual(canvas.pixelColor(15, 198).alpha(), 0)

    def test_dock_transition_position_stays_between_both_endpoints(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='copy')
        widget._dock_initialized = True
        widget._dock_right_progress = 0.5
        widget._dock_bottom_progress = 0.5
        context = {
            'mouse_x': 1500.0,
            'mouse_y': 1000.0,
            'left': 0.0,
            'top': 0.0,
            'right': 1920.0,
            'effective_bottom': 1080.0,
            'normal_x': 1511.0,
            'normal_y': 1011.0,
            'normal_right': 120.0,
            'normal_bottom': 33.0,
        }
        widget._apply_position(context)
        docked_x = 1920 - 12 - widget.width()
        docked_y = 1080 - 12 - 33
        self.assertGreater(widget.x(), min(context['normal_x'], docked_x))
        self.assertLess(widget.x(), max(context['normal_x'], docked_x))
        self.assertGreater(widget.y(), min(context['normal_y'], docked_y))
        self.assertLess(widget.y(), max(context['normal_y'], docked_y))

    def test_reversing_dock_transition_starts_from_current_progress(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='copy')
        widget._dock_initialized = True
        widget._set_dock_target('right', True)
        widget._engine._active_anims['dock_right_progress'].current = 0.42
        widget._set_dock_target('right', False)
        descriptor = widget._engine._active_anims['dock_right_progress']
        self.assertAlmostEqual(descriptor.start, 0.42)
        self.assertEqual(descriptor.end, 0.0)
        widget._engine.stop()

    def test_mid_transition_keeps_box_and_image_visible_without_gradient_flash(self):
        image = QImage(32, 32, QImage.Format_ARGB32)
        image.fill(0xFFFFFFFF)
        widget = FeedbackWidget(
            FeedbackType.COPY, text='copy', images=[image, image.copy()],
            image_count=2)
        widget._dock_initialized = True
        widget._dock_right_progress = 0.5
        widget._dock_bottom_progress = 0.5
        widget._dot_scale = 1.0
        widget._box_width = widget._target_width
        widget._box_opacity = 1.0
        widget._display_text = widget._text
        widget._image_scramble_progress = 1.0
        widget._stack_progress = 1.0
        canvas = QImage(widget.size(), QImage.Format_ARGB32)
        canvas.fill(0)
        widget.render(canvas)

        dot_x = widget.width() // 2
        box_left = int(dot_x - widget._box_width / 2)
        box_right = int(dot_x + widget._box_width / 2) - 1
        self.assertGreater(canvas.pixelColor(box_left, 90).alpha(), 0)
        self.assertGreater(canvas.pixelColor(box_right, 90).alpha(), 0)
        self.assertGreater(canvas.pixelColor(dot_x, 45).alpha(), 0)


if __name__ == '__main__':
    unittest.main()
