"""Regression tests for the bounded copied-text viewport."""

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from config import SIZES, TEXT_VIEW
from ui.animation.state_machine import AnimationState
from ui.feedback_widget import FeedbackType, FeedbackWidget
from ui.feedback_layout import image_base_pos
from ui.text_viewport import TextViewport


def app():
    return QApplication.instance() or QApplication([])


class TextViewportTests(unittest.TestCase):
    def test_switches_lines_without_copying_all_line_text(self):
        viewport = TextViewport('first\nsecond\n', visible_chars=4)

        self.assertEqual(viewport.line_count, 3)
        self.assertEqual(viewport.visible_text, 'firs')
        self.assertTrue(viewport.move_line(1))
        self.assertEqual(viewport.visible_text, 'seco')
        self.assertTrue(viewport.move_line(1))
        self.assertEqual(viewport.visible_text, '')
        self.assertFalse(viewport.move_line(1))

    def test_any_line_can_use_the_shared_horizontal_viewport_column(self):
        viewport = TextViewport('abcdef\nuvwxyz', visible_chars=4)

        self.assertEqual(viewport.line_slice(1, 4, column=2), 'wxyz')

    def test_visible_slice_is_bounded_by_visible_window(self):
        viewport = TextViewport('abcdefghij', visible_chars=4)

        viewport.set_column(3)
        self.assertEqual(viewport.visible_text, 'defg')
        viewport.set_column(99)
        self.assertEqual(viewport.visible_text, 'ghij')
        viewport.set_column(-99)
        self.assertEqual(viewport.visible_text, 'abcd')


class FeedbackViewportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app()

    def test_long_text_uses_fixed_box_and_bounded_render_slice(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='x' * 1000)

        self.assertEqual(widget._target_width, SIZES['box_max_width'])
        self.assertEqual(len(widget._raw_text), 1000)
        self.assertEqual(len(widget._text), TEXT_VIEW['render_chars'])

    def test_medium_cjk_line_can_scroll_by_pixels(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='中' * 60)
        widget._sm._state = AnimationState.VIEWING

        self.assertTrue(widget.can_navigate_text)
        self.assertTrue(widget.navigate_text('right'))

    def test_navigation_updates_only_the_local_viewport(self):
        widget = FeedbackWidget(
            FeedbackType.COPY, text=('a' * 195) + 'WXYZ\nsecond')
        widget._sm._state = AnimationState.VIEWING

        self.assertTrue(widget.navigate_text('right'))
        self.assertTrue(widget._engine.has_active('text_scroll_offset'))
        self.assertGreater(widget._pending_scroll_column, 0)
        self.assertGreater(len(widget._text), TEXT_VIEW['render_chars'])
        widget._complete_text_scroll()
        self.assertGreater(widget._viewport.column, 0)
        self.assertTrue(widget.navigate_text('down'))
        self.assertEqual(widget._visible_line_count, 2)
        self.assertEqual(widget._display_lines[1], 'second'[widget._viewport.column:])
        self.assertTrue(widget.navigate_text('up'))
        self.assertEqual(widget._visible_line_count, 1)

    def test_expanded_lines_refresh_at_the_same_horizontal_column(self):
        widget = FeedbackWidget(
            FeedbackType.COPY, text=('abcdef' * 20) + '\n' + ('uvwxyz' * 20))
        widget._sm._state = AnimationState.VIEWING
        widget.navigate_text('down')
        self.assertTrue(widget.navigate_text('right'))
        widget._complete_text_scroll()

        for index, line in enumerate(widget._display_lines):
            self.assertEqual(
                line, widget._viewport.line_slice(
                    index, TEXT_VIEW['render_chars'], widget._viewport.column))

    def test_arrow_during_box_expand_finishes_intro_and_navigates(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='x' * 1000)
        widget._sm._state = AnimationState.BOX_EXPAND

        self.assertTrue(widget.navigate_text('right'))
        self.assertIn(widget._sm.state, (AnimationState.VIEWING,
                                         AnimationState.IMAGE_APPEAR,
                                         AnimationState.STACK_APPEAR))

    def test_short_text_uses_its_actual_width(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='中')
        expected = widget._text_style.horizontal_advance('中') + SIZES['box_padding']

        self.assertAlmostEqual(widget._target_width, expected)
        self.assertLess(widget._target_width, SIZES['box_min_width'])

    def test_image_base_tracks_expanded_content_height(self):
        _, compact_y = image_base_pos(5, 5, 120, box_height=28)
        _, expanded_y = image_base_pos(5, 5, 120, box_height=84)

        self.assertEqual(expanded_y - compact_y, 56)

    def test_down_expands_all_available_lines_up_to_the_limit(self):
        widget = FeedbackWidget(
            FeedbackType.COPY, text='\n'.join(str(index) for index in range(8)))
        widget._sm._state = AnimationState.VIEWING

        self.assertTrue(widget.navigate_text('down'))
        self.assertEqual(widget._visible_line_count, TEXT_VIEW['max_visible_lines'])
        self.assertEqual(len(widget._display_lines), TEXT_VIEW['max_visible_lines'])
        self.assertTrue(widget.navigate_text('up'))
        self.assertEqual(widget._visible_line_count, 1)

    def test_expanded_view_defers_timeout_until_the_user_collapses_it(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='one\ntwo\nthree')
        widget._sm._state = AnimationState.VIEWING
        self.assertTrue(widget.navigate_text('down'))

        widget._on_state_timer()
        self.assertEqual(widget._sm.state, AnimationState.VIEWING)
        self.assertTrue(widget._timeout_while_expanded)
        self.assertTrue(widget.navigate_text('up'))
        widget._on_prop_finished('box_height')
        self.assertFalse(widget._timeout_while_expanded)
        self.assertNotEqual(widget._sm.state, AnimationState.VIEWING)

    def test_first_line_width_is_compact_until_multiline_content_expands(self):
        widget = FeedbackWidget(
            FeedbackType.COPY, text='short\n' + ('long text ' * 80))
        widget._sm._state = AnimationState.VIEWING

        self.assertLess(widget._collapsed_width, widget._expanded_width)
        self.assertEqual(widget._target_width, widget._collapsed_width)
        self.assertTrue(widget.navigate_text('down'))
        self.assertEqual(widget._target_width, widget._expanded_width)
        self.assertTrue(widget._engine.has_active('box_width'))

        widget._box_width = widget._expanded_width
        self.assertTrue(widget.navigate_text('up'))
        self.assertEqual(widget._target_width, widget._collapsed_width)


    def test_expanded_lines_use_a_compact_step_after_the_first_row(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='one\ntwo\nthree')
        widget._sm._state = AnimationState.VIEWING

        self.assertTrue(widget.navigate_text('down'))
        expected = (SIZES['box_height'] +
                    (widget._visible_line_count - 1) *
                    widget._expanded_line_step())
        self.assertEqual(widget._target_box_height(), expected)
        self.assertLess(widget._expanded_line_step(), SIZES['box_height'])

    def test_terminal_scroll_aligns_the_last_character_to_the_content_edge(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='W' * 100)

        self.assertGreaterEqual(widget._viewport.max_column,
                                len(widget._raw_text) - TEXT_VIEW['scroll_window_chars'])
        widget._viewport.set_column(widget._viewport.max_column)
        widget._text_alignment_offset = widget._terminal_text_alignment
        widget._refresh_viewport_text()
        rendered_width = widget._text_style.horizontal_advance(widget._text)
        self.assertAlmostEqual(rendered_width + widget._text_alignment_offset,
                               widget._text_content_width(), places=3)

    def test_repeated_horizontal_input_queues_one_smooth_follow_up_step(self):
        widget = FeedbackWidget(FeedbackType.COPY, text='x' * 1000)
        widget._sm._state = AnimationState.VIEWING

        self.assertTrue(widget.navigate_text('right'))
        first_target = widget._pending_scroll_column
        self.assertTrue(widget.navigate_text('right'))
        self.assertEqual(widget._pending_scroll_column, first_target)
        self.assertEqual(widget._queued_scroll_direction, 1)
        widget._complete_text_scroll()
        self.assertTrue(widget._engine.has_active('text_scroll_offset'))
