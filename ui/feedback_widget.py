"""反馈窗口：由单一单调帧时钟驱动完整动画生命周期。"""

import random
from enum import Enum, auto
from typing import List, Optional

from PySide6.QtCore import QPoint, QTimer, Qt, QEasingCurve, Signal
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QPainter, QPixmap,
                           QStaticText)
from PySide6.QtWidgets import QWidget

from config import (ANIMATION_DURATION, BLOCK_CHARS, COLORS, DOCK_TRANSITION,
                    IMAGE_STACK, SCRAMBLE_CHARS, SIZES, TEXT_RENDER, TEXT_VIEW)
from core.taskbar_boundary import TaskbarBoundary
from ui.animation.property_engine import PropertyEngine
from ui.animation.spring_ease import spring_ease
from ui.animation.state_machine import AnimationState, AnimationStateMachine
from ui.components.content_box import ContentBox
from ui.components.dot_renderer import DotRenderer
from ui.components.image_renderer import ImageRenderCache, ImageRenderer
from ui.components.stack_layer import StackLayer
from ui.feedback_layout import (DOT_CX, DOT_CY, EDGE_DOCK_MARGIN,
                                bottom_dock_dot_y, edge_dock_required,
                                image_base_pos, mouse_to_window,
                                visible_content_bounds, window_size)
from ui.image_layout import (IMAGE_LAYOUT_CASCADE, cascade_layer_offset,
                             image_display_limit, normalize_image_layout)
from ui.text_style import TextStyle, TextStyleResolver
from ui.text_viewport import TextViewport


class FeedbackType(Enum):
    COPY = auto()
    PASTE = auto()
    ERROR = auto()


class FeedbackWidget(QWidget):
    animation_complete = Signal()
    frame_tick = Signal(float)
    navigation_active_changed = Signal(bool)

    def __init__(self, feedback_type, text="", images=None,
                 image_count=0, holding_mode=False, parent=None,
                 ui_scale=1.0, cursor_offset=None,
                 image_layout_mode='fan'):
        super().__init__(parent)
        self._ui_scale = max(1.0, min(float(ui_scale), 1.5))
        self._cursor_offset = cursor_offset or (
            float(SIZES['mouse_offset_x']), float(SIZES['mouse_offset_y']))
        self._feedback_type = feedback_type
        self._raw_text = text if feedback_type == FeedbackType.COPY else ''
        self._viewport = (TextViewport(self._raw_text,
                                       TEXT_VIEW['scroll_window_chars'])
                          if self._raw_text else None)
        self._has_horizontal_overflow = False
        self._text = ''
        self._text_style: TextStyle = TextStyleResolver.resolve(self._raw_text)
        self._final_text_layout: Optional[QStaticText] = None
        self._visible_line_count = 1
        self._display_lines = []
        self._line_layouts = []
        self._refresh_viewport_text()
        self._image_layout_mode = normalize_image_layout(image_layout_mode)
        self._image_display_limit = image_display_limit(self._image_layout_mode)
        requested_image_count = max(int(image_count or 0), len(images or []))
        self._image_count = min(requested_image_count,
                                self._image_display_limit)
        self._total_image_count = requested_image_count
        self._holding_mode = holding_mode
        self._active = True
        self._images: List[QImage] = []
        self._main_image: Optional[QImage] = None
        self._main_image_cache: Optional[ImageRenderCache] = None
        self._image_render_caches: List[Optional[ImageRenderCache]] = []
        self._stack_thumbnail_cache: List[Optional[QPixmap]] = []
        self._append_images(images)
        self._has_image = bool(self._images) or image_count > 0
        self._awaiting_images = image_count > 0 and not self._images

        self._dot_scale = 0.0
        self._box_width = 0.0
        self._box_height = float(SIZES['box_height'])
        self._box_opacity = 0.0
        self._stack_progress = 0.0
        self._stack_phase = 'hidden'
        self._stack_anim_start_ms = 0.0
        self._stack_anim_duration = ANIMATION_DURATION['stack_appear']
        self._stack_anim_from = 0.0
        self._stack_anim_to = 1.0
        self._scramble_start_ms: Optional[float] = None
        self._last_scramble_refresh_ms: Optional[float] = None
        self._scramble_buffer: List[str] = []
        self._scramble_solved_count = 0
        self._scramble_noise_cursor = 0
        self._image_reveal_start_ms: Optional[float] = None
        self._image_scramble_progress = 0.0
        self._vanish_ratio = 1.0
        self._display_text = ""
        self._text_scroll_offset = 0.0
        self._text_alignment_offset = 0.0
        self._terminal_text_alignment = 0.0
        self._pending_scroll_column = None
        self._pending_scroll_alignment = 0.0
        self._queued_scroll_direction = 0
        self._timeout_while_expanded = False
        self._exit_after_collapse = False
        self._dock_right = False
        self._dock_bottom = False
        self._dock_right_progress = 0.0
        self._dock_bottom_progress = 0.0
        self._dock_initialized = False
        self._position_context = None

        self._target_width = 0.0
        self._collapsed_width = 0.0
        self._expanded_width = 0.0
        if feedback_type == FeedbackType.COPY and self._raw_text:
            self._collapsed_width = self._resolve_target_width(1, True)
            self._expanded_width = self._resolve_target_width(
                TEXT_VIEW['max_visible_lines'])
            self._target_width = self._collapsed_width
            self._configure_horizontal_scroll_limit()

        if feedback_type == FeedbackType.ERROR:
            self._dot_color = QColor(COLORS['dot_error'])
        elif feedback_type == FeedbackType.PASTE:
            self._dot_color = QColor(COLORS['dot_paste'])
        else:
            self._dot_color = QColor(COLORS['dot_copy'])

        self._sm = AnimationStateMachine(self)
        self._sm.action_requested.connect(self._execute_action)
        self._sm.state_changed.connect(self._on_animation_state_changed)
        self._engine = PropertyEngine(self)
        self._engine.tick.connect(self._on_frame)
        self._engine.finished.connect(self._on_prop_finished)

        self._holding_timer = QTimer(self)
        self._holding_timer.setSingleShot(True)
        self._holding_timer.timeout.connect(self._on_holding_timeout)
        self._state_timer = QTimer(self)
        self._state_timer.setSingleShot(True)
        self._state_timer.timeout.connect(self._on_state_timer)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._resize_to_content()

    def start_animation(self):
        self.show()
        self._engine.set_frame_active('widget_lifecycle', True)
        self._sm.transition('start')
        if self._has_image:
            self._start_image_reveal()

    def start_exit(self):
        """任意可见阶段都可安全退出，防止粘贴/holding 造成状态卡死。"""
        state = self._sm.state
        if state in (AnimationState.IDLE, AnimationState.COMPLETE,
                     AnimationState.DOT_DISAPPEAR, AnimationState.STACK_RETRACT,
                     AnimationState.IMAGE_VANISH, AnimationState.BOX_SHRINK,
                     AnimationState.LINE_SHRINK):
            return
        self._stop_timed_effects()
        if state in (AnimationState.DOT_APPEAR, AnimationState.PULSE):
            self._sm.transition('exit')
            return
        if state == AnimationState.STACK_APPEAR and self._stack_progress > 0.01:
            self._sm.transition('exit_has_stack')
            return
        if self._image_count >= 2 and self._stack_phase == 'visible':
            self._sm.transition('exit_has_stack')
        else:
            self._sm.transition('exit_no_stack')

    @property
    def is_holding_copy(self) -> bool:
        """Whether this feedback instance represents a copy waiting for Ctrl+V."""
        return self._holding_mode and self._feedback_type == FeedbackType.COPY

    @property
    def can_navigate_text(self) -> bool:
        return bool(self._viewport and (
            self._viewport.line_count > 1 or self._has_horizontal_overflow))

    def navigate_text(self, direction: str) -> bool:
        """Move the local text viewport; never access the system clipboard."""
        if not self.can_navigate_text:
            return False
        self._make_text_interactive()
        if self._sm.state not in (AnimationState.IMAGE_APPEAR,
                                  AnimationState.STACK_APPEAR,
                                  AnimationState.VIEWING,
                                  AnimationState.HOLDING):
            return False
        if direction == 'left':
            changed = self._start_horizontal_scroll(-1)
        elif direction == 'right':
            changed = self._start_horizontal_scroll(1)
        elif direction == 'up':
            self._complete_text_scroll(run_queued=False)
            changed = self._change_visible_line_count(-1)
        elif direction == 'down':
            self._complete_text_scroll(run_queued=False)
            changed = self._change_visible_line_count(1)
        else:
            return False
        if not changed:
            return False
        if (self._sm.state == AnimationState.VIEWING and
                not self._timeout_while_expanded):
            self._state_timer.start(ANIMATION_DURATION['view_time'])
        elif (self._sm.state == AnimationState.HOLDING and
              not self._timeout_while_expanded):
            self._holding_timer.start(ANIMATION_DURATION['holding_max'])
        self.update()
        return True

    def _make_text_interactive(self) -> None:
        """Finish the introductory text phase when the user presses an arrow."""
        if self._sm.state == AnimationState.BOX_EXPAND:
            self._engine.cancel('box_width')
            self._box_width = self._target_width
            self._sm.transition('done')
        if self._sm.state == AnimationState.TEXT_REVEAL:
            self._scramble_start_ms = None
            self._last_scramble_refresh_ms = None
            self._engine.set_frame_active('text_scramble', False)
            self._display_text = self._text
            self._continue_after_text()

    def _start_horizontal_scroll(self, direction: int) -> bool:
        if self._engine.has_active('text_scroll_offset'):
            # Keep at most one queued step. Holding an arrow key then yields
            # continuous motion without building a long post-release backlog.
            self._queued_scroll_direction = direction
            return True
        current_column = self._viewport.column
        target_column = self._pixel_step_target(direction)
        if target_column == current_column:
            return False
        start_alignment = (self._text_alignment_offset
                           if current_column == self._viewport.max_column else 0.0)
        target_alignment = (self._terminal_text_alignment
                            if target_column == self._viewport.max_column else 0.0)
        if direction > 0:
            render_column = current_column
            translation_start = start_alignment
            translation_end = -self._text_style.horizontal_advance(
                self._viewport.text_between(current_column, target_column)) + target_alignment
        else:
            render_column = target_column
            translation_start = -self._text_style.horizontal_advance(
                self._viewport.text_between(target_column, current_column)) + start_alignment
            translation_end = target_alignment
        self._refresh_viewport_text(
            render_column,
            TEXT_VIEW['render_chars'] + TEXT_VIEW['scroll_buffer_chars'])
        self._display_text = self._text
        self._text_scroll_offset = translation_start
        self._pending_scroll_column = target_column
        self._pending_scroll_alignment = target_alignment
        self._engine.animate(
            'text_scroll_offset', translation_start, translation_end,
            TEXT_VIEW['scroll_duration'],
            QEasingCurve(QEasingCurve.OutCubic),
            on_finished=self._complete_text_scroll)
        return True

    def _pixel_step_target(self, direction: int) -> int:
        current = self._viewport.column
        boundary = self._viewport.max_column
        if direction > 0:
            target = current
            distance = 0.0
            while target < boundary and distance < TEXT_VIEW['scroll_pixels']:
                next_target = target + 1
                distance += self._text_style.horizontal_advance(
                    self._viewport.text_between(target, next_target))
                target = next_target
            return target
        target = current
        distance = 0.0
        while target > 0 and distance < TEXT_VIEW['scroll_pixels']:
            previous_target = target - 1
            distance += self._text_style.horizontal_advance(
                self._viewport.text_between(previous_target, target))
            target = previous_target
        return target

    def _complete_text_scroll(self, run_queued: bool = True) -> None:
        if self._pending_scroll_column is None:
            return
        if self._engine.has_active('text_scroll_offset'):
            self._engine.cancel('text_scroll_offset')
        self._viewport.set_column(self._pending_scroll_column)
        self._pending_scroll_column = None
        self._text_alignment_offset = self._pending_scroll_alignment
        self._pending_scroll_alignment = 0.0
        self._text_scroll_offset = 0.0
        self._refresh_viewport_text()
        self._display_text = self._text
        self.update()
        queued_direction = self._queued_scroll_direction if run_queued else 0
        self._queued_scroll_direction = 0
        if queued_direction:
            self._start_horizontal_scroll(queued_direction)

    def _refresh_viewport_text(self, column: int = None,
                               visible_chars: int = None) -> None:
        viewport_column = (self._viewport.column
                           if self._viewport is not None and column is None
                           else (column or 0))
        if self._viewport:
            visible = self._viewport.text_slice(
                viewport_column,
                TEXT_VIEW['render_chars'] if visible_chars is None else visible_chars)
        else:
            visible = ''
        self._text = visible
        style_source = visible or self._raw_text
        self._text_style = TextStyleResolver.resolve(style_source)
        self._final_text_layout = (
            self._text_style.static_layout(visible) if visible else None)
        self._display_lines = [visible]
        self._line_layouts = [self._final_text_layout]
        if self._viewport:
            visible_lines = min(self._visible_line_count,
                                self._viewport.line_count)
            for line_index in range(1, visible_lines):
                line = self._viewport.line_slice(
                    line_index, TEXT_VIEW['render_chars'], viewport_column)
                self._display_lines.append(line)
                self._line_layouts.append(
                    self._text_style.static_layout(line) if line else None)

    def _resolve_target_width(self, line_limit: int = 1,
                              track_horizontal: bool = False) -> float:
        """Measure only the lines visible in the collapsed or expanded mode."""
        content_limit = SIZES['box_max_width'] - SIZES['box_padding']
        widest = 0.0
        for index, (sample, truncated) in enumerate(self._viewport.width_probe(
                TEXT_VIEW['width_probe_chars'])):
            if index >= max(1, int(line_limit)):
                break
            sample_width = self._text_style.horizontal_advance(sample)
            if truncated or sample_width >= content_limit:
                if track_horizontal:
                    self._has_horizontal_overflow = True
                return float(SIZES['box_max_width'])
            widest = max(widest, sample_width)
        return min(SIZES['box_max_width'], max(
            SIZES['box_text_min_width'], widest + SIZES['box_padding']))

    def _configure_horizontal_scroll_limit(self) -> None:
        if not self._viewport or not self._has_horizontal_overflow:
            return
        terminal_column = self._viewport.suffix_start_for_width(
            self._text_style.horizontal_advance, self._text_content_width())
        self._viewport.set_max_column(terminal_column)
        terminal_text = self._viewport.text_between(
            terminal_column, self._viewport.current_line_length)
        self._terminal_text_alignment = max(
            0.0, self._text_content_width() -
            self._text_style.horizontal_advance(terminal_text))

    def _text_content_width(self) -> float:
        # ContentBox clips at x + 8 while normal text starts at x + 10 and
        # ends at x + width - 4, leaving this precise drawable width.
        return max(1.0, self._target_width - 14.0)

    def _change_visible_line_count(self, delta: int) -> bool:
        maximum = min(TEXT_VIEW['max_visible_lines'], self._viewport.line_count)
        target = maximum if delta > 0 else 1
        if target == self._visible_line_count:
            return False
        if target == 1 and self._timeout_while_expanded:
            self._exit_after_collapse = True
        self._visible_line_count = target
        self._refresh_viewport_text()
        self._display_text = self._text
        self._target_width = (self._expanded_width if target > 1
                              else self._collapsed_width)
        self._engine.animate(
            'box_width', self._box_width, self._target_width,
            TEXT_VIEW['line_expand_duration'],
            QEasingCurve(QEasingCurve.OutCubic))
        self._engine.animate(
            'box_height', self._box_height,
            self._target_box_height(), TEXT_VIEW['line_expand_duration'],
            QEasingCurve(QEasingCurve.OutCubic))
        return True

    def _target_box_height(self) -> float:
        return float(SIZES['box_height'] + (
            self._visible_line_count - 1) * self._expanded_line_step())

    def _expanded_line_step(self) -> float:
        return max(float(TEXT_VIEW['expanded_line_step']),
                   float(self._text_style.metrics.height()))

    def _max_box_height(self) -> float:
        if not self._viewport:
            return float(SIZES['box_height'])
        maximum = min(TEXT_VIEW['max_visible_lines'], self._viewport.line_count)
        return float(SIZES['box_height'] + (
            maximum - 1) * self._expanded_line_step())

    def _on_animation_state_changed(self, state: AnimationState) -> None:
        self.navigation_active_changed.emit(
            self.can_navigate_text and state in (
                AnimationState.BOX_EXPAND, AnimationState.TEXT_REVEAL,
                AnimationState.IMAGE_APPEAR, AnimationState.STACK_APPEAR,
                AnimationState.VIEWING, AnimationState.HOLDING))

    def move_to_position(self, x, y):
        context = self._build_position_context(x, y)
        self._position_context = context
        self._update_dock_targets(context)
        self._apply_position(context)

    def _build_position_context(self, x, y):
        screen = QGuiApplication.screenAt(QPoint(int(x), int(y)))
        if screen is not None:
            available = screen.availableGeometry()
            geometry = screen.geometry()
            normal_right, normal_bottom = visible_content_bounds(
                self._target_width, self._has_image, self._image_count,
                image_layout_mode=self._image_layout_mode,
                box_height=self._box_height)
            normal_x, normal_y = mouse_to_window(
                x, y, self._ui_scale, *self._cursor_offset, DOT_CY)
            normal_bottom_edge = normal_y + normal_bottom * self._ui_scale
            screen_bottom = geometry.y() + geometry.height()
            # Keep using the raised taskbar edge while a bottom dock is
            # unwinding. Otherwise the old 96px probe window can switch the
            # boundary from taskbar-top back to screen-bottom mid-transition,
            # visibly snapping the content down before it follows the cursor.
            taskbar_boundary_active = (
                self._dock_bottom or self._dock_bottom_progress > 0.01)
            if (taskbar_boundary_active or
                    normal_bottom_edge > available.y() + available.height() -
                    EDGE_DOCK_MARGIN * self._ui_scale or
                    y > screen_bottom - 96 * self._ui_scale):
                effective_bottom = TaskbarBoundary.effective_bottom(
                    screen, int(self.winId()))
            else:
                effective_bottom = available.y() + available.height()
            return {
                'mouse_x': float(x),
                'mouse_y': float(y),
                'left': available.x(),
                'top': available.y(),
                'right': available.x() + available.width(),
                'effective_bottom': float(effective_bottom),
                'normal_x': float(normal_x),
                'normal_y': float(normal_y),
                'normal_right': float(normal_right),
                'normal_bottom': float(normal_bottom),
            }

        # This only occurs transiently while displays are reconfigured.
        normal_right, normal_bottom = visible_content_bounds(
            self._target_width, self._has_image, self._image_count,
            image_layout_mode=self._image_layout_mode,
            box_height=self._box_height)
        normal_x, normal_y = mouse_to_window(
            x, y, self._ui_scale, *self._cursor_offset, DOT_CY)
        return {
            'mouse_x': float(x),
            'mouse_y': float(y),
            'left': 0.0,
            'top': 0.0,
            'right': 100000.0,
            'effective_bottom': 100000.0,
            'normal_x': float(normal_x),
            'normal_y': float(normal_y),
            'normal_right': float(normal_right),
            'normal_bottom': float(normal_bottom),
        }

    def _update_dock_targets(self, context) -> None:
        right_edge = (context['normal_x'] +
                      context['normal_right'] * self._ui_scale)
        bottom_edge = (context['normal_y'] +
                       context['normal_bottom'] * self._ui_scale)
        dock_right = edge_dock_required(
            right_edge, context['right'], self._dock_right, self._ui_scale)
        dock_bottom = edge_dock_required(
            bottom_edge, context['effective_bottom'], self._dock_bottom,
            self._ui_scale)

        if not self._dock_initialized:
            self._dock_initialized = True
            self._dock_right = dock_right
            self._dock_bottom = dock_bottom
            self._dock_right_progress = 1.0 if dock_right else 0.0
            self._dock_bottom_progress = 1.0 if dock_bottom else 0.0
            return

        self._set_dock_target('right', dock_right)
        self._set_dock_target('bottom', dock_bottom)

    def _set_dock_target(self, edge: str, docked: bool) -> None:
        state_attr = f'_dock_{edge}'
        progress_attr = f'_dock_{edge}_progress'
        prop = f'dock_{edge}_progress'
        if getattr(self, state_attr) == docked:
            return
        setattr(self, state_attr, docked)
        current = (self._engine.get_value(prop, getattr(self, progress_attr))
                   if self._engine.has_active(prop)
                   else getattr(self, progress_attr))
        setattr(self, progress_attr, current)
        target = 1.0 if docked else 0.0
        distance = abs(target - current)
        duration = max(40, round(
            DOCK_TRANSITION[f'{edge}_duration'] * distance))
        self._engine.animate(
            prop, current, target, duration,
            QEasingCurve(QEasingCurve.OutCubic))

    def _dock_progress(self, edge: str) -> float:
        if not self._dock_initialized:
            return 1.0 if getattr(self, f'_dock_{edge}') else 0.0
        return max(0.0, min(
            float(getattr(self, f'_dock_{edge}_progress')), 1.0))

    def _apply_position(self, context) -> None:
        right_progress = self._dock_progress('right')
        bottom_progress = self._dock_progress('bottom')
        scale = self._ui_scale
        margin = EDGE_DOCK_MARGIN * scale

        normal_x = context['normal_x']
        normal_y = context['normal_y']
        docked_x = context['right'] - margin - self.width()

        dock_dot_cy = (bottom_dock_dot_y(
            self._image_count, self._image_layout_mode)
                       if self._has_image else DOT_CY)
        _, dock_visible_bottom = visible_content_bounds(
            self._target_width, self._has_image, self._image_count,
            dock_dot_cy, self._has_image, self._image_layout_mode,
            self._box_height)
        docked_y = (context['effective_bottom'] - margin -
                    dock_visible_bottom * scale)

        win_x = normal_x + (docked_x - normal_x) * right_progress
        win_y = normal_y + (docked_y - normal_y) * bottom_progress
        current_dot_cy = DOT_CY + (dock_dot_cy - DOT_CY) * bottom_progress
        win_x = max(context['left'] - DOT_CX * scale, win_x)
        win_y = max(context['top'] - current_dot_cy * scale, win_y)
        win_x, win_y = int(round(win_x)), int(round(win_y))
        if self.x() != win_x or self.y() != win_y:
            self.move(win_x, win_y)

    def update_images(self, images, image_count):
        if not self._active or not images:
            return
        before = len(self._images)
        self._append_images(images)
        if len(self._images) == before:
            return
        self._total_image_count = image_count
        self._image_count = min(max(int(image_count or 0), len(self._images)),
                                self._image_display_limit)
        self._has_image = True
        self._awaiting_images = False
        self._resize_to_content()
        if self._position_context is not None:
            self.move_to_position(
                self._position_context['mouse_x'],
                self._position_context['mouse_y'])
        self._start_image_reveal()
        self.update()

    def stop(self):
        self._active = False
        self._stop_timed_effects()
        self._engine.stop()
        self._sm.reset()
        self._state_timer.stop()
        self._holding_timer.stop()
        self.close()

    def _append_images(self, images) -> None:
        known_keys = {image.cacheKey() for image in self._images}
        for image in (images or [])[:IMAGE_STACK['max_preload']]:
            if not isinstance(image, QImage) or image.isNull():
                continue
            copy = image.copy()
            if copy.cacheKey() in known_keys:
                continue
            self._images.append(copy)
            known_keys.add(copy.cacheKey())
        if self._images:
            self._main_image = self._images[0]
            self._main_image_cache = ImageRenderer.build_cache(self._main_image)
            self._image_render_caches = [self._main_image_cache]
            self._image_render_caches.extend(
                ImageRenderer.build_cache(image, include_reveal=False)
                for image in self._images[1:IMAGE_STACK['max_preload']])
            self._stack_thumbnail_cache = [None]
            for image in self._images[1:IMAGE_STACK['max_preload']]:
                scaled = image.scaled(ImageRenderer.IMAGE_BOX_SIZE,
                                      ImageRenderer.IMAGE_BOX_SIZE,
                                      Qt.KeepAspectRatioByExpanding,
                                      Qt.FastTransformation)
                self._stack_thumbnail_cache.append(QPixmap.fromImage(scaled))

    def _resize_to_content(self) -> None:
        self.setFixedSize(*window_size(
            max(self._collapsed_width, self._expanded_width), self._has_image,
            self._ui_scale,
            self._max_box_height()))

    def _execute_action(self, action):
        dispatch = {
            'animate_dot_appear': self._act_dot_appear,
            'animate_box_expand': self._act_box_expand,
            'start_scramble': self._act_start_scramble,
            'enter_image_or_viewing': self._act_enter_image_or_viewing,
            'animate_stack': self._act_stack_appear,
            'start_view_timer': self._act_view_timer,
            'start_pulse_timer': self._act_pulse_timer,
            'start_holding_timer': self._act_holding_timer,
            'retract_stack': self._act_stack_retract,
            'animate_image_vanish': self._act_image_vanish,
            'animate_box_shrink': self._act_box_shrink,
            'animate_line_shrink': self._act_line_shrink,
            'animate_dot_disappear': self._act_dot_disappear,
            'emit_complete': self._act_complete,
        }
        fn = dispatch.get(action)
        if fn:
            fn()

    def _act_dot_appear(self):
        self._engine.animate('dot_scale', 0.0, 1.0,
                             ANIMATION_DURATION['dot_appear'],
                             QEasingCurve(QEasingCurve.OutBack))

    def _act_box_expand(self):
        self._box_opacity = 1.0
        self._engine.animate('box_width', 0.0, self._target_width,
                             ANIMATION_DURATION['box_expand'],
                             QEasingCurve(QEasingCurve.OutQuad))

    def _act_start_scramble(self):
        if not self._text:
            self._continue_after_text()
            return
        self._scramble_start_ms = self._engine.now_ms
        self._last_scramble_refresh_ms = None
        self._reset_scramble_buffer()
        self._engine.set_frame_active('text_scramble', True)

    def _act_enter_image_or_viewing(self):
        if self._has_image or self._awaiting_images:
            if self._image_count >= 2:
                self._sm.transition('done_multi_image')
            elif self._holding_mode:
                self._sm.transition('done_holding_single')
            else:
                self._sm.transition('done_normal_single')
        elif self._holding_mode:
            self._sm.transition('done_holding_single')
        else:
            self._sm.transition('done_normal_single')

    def _act_stack_appear(self):
        self._stack_phase = 'appearing'
        self._stack_anim_from = 0.0
        self._stack_anim_to = 1.0
        self._stack_anim_start_ms = self._engine.now_ms
        self._stack_anim_duration = ANIMATION_DURATION['stack_appear']
        self._engine.set_frame_active('stack', True)

    def _act_view_timer(self):
        self._state_timer.start(ANIMATION_DURATION['view_time'])

    def _act_pulse_timer(self):
        self._state_timer.start(ANIMATION_DURATION['error_display'])

    def _act_holding_timer(self):
        self._holding_timer.start(ANIMATION_DURATION['holding_max'])

    def _act_stack_retract(self):
        self._stack_phase = 'retracting'
        self._stack_anim_from = self._stack_progress
        self._stack_anim_to = 0.0
        self._stack_anim_start_ms = self._engine.now_ms
        self._stack_anim_duration = ANIMATION_DURATION['stack_retract']
        self._engine.set_frame_active('stack', True)

    def _act_image_vanish(self):
        self._stop_timed_effects()
        if not self._has_image:
            self._sm.transition('done')
            return
        self._engine.animate('vanish_ratio', self._vanish_ratio, 0.0,
                             ANIMATION_DURATION.get('image_vanish', 200),
                             QEasingCurve(QEasingCurve.InQuad))

    def _act_box_shrink(self):
        if self._box_width <= 2.0:
            self._sm.transition('done')
            return
        self._box_opacity = 1.0
        self._engine.animate('box_width', self._box_width, 2.0,
                             ANIMATION_DURATION['box_shrink'],
                             QEasingCurve(QEasingCurve.InQuad))

    def _act_line_shrink(self):
        if self._box_width <= 1.0 or self._box_height <= 0.0:
            self._sm.transition('done')
            return
        self._engine.animate('box_height', self._box_height, 0.0,
                             ANIMATION_DURATION['line_shrink'],
                             QEasingCurve(QEasingCurve.Linear))
        self._engine.animate('box_opacity', self._box_opacity, 0.0,
                             ANIMATION_DURATION['line_shrink'],
                             QEasingCurve(QEasingCurve.Linear))

    def _act_dot_disappear(self):
        self._engine.animate('dot_scale', self._dot_scale, 0.0,
                             ANIMATION_DURATION['dot_disappear'],
                             QEasingCurve(QEasingCurve.InBack))

    def _act_complete(self):
        self._active = False
        self._engine.stop()
        self.animation_complete.emit()
        self.close()

    def _on_frame(self):
        if not self._active:
            return
        self._sync_engine_properties()
        if (self._position_context is not None and
                (self._engine.has_active('dock_right_progress') or
                 self._engine.has_active('dock_bottom_progress') or
                 self._engine.has_active('box_width') or
                 self._engine.has_active('box_height'))):
            self._position_context = self._build_position_context(
                self._position_context['mouse_x'],
                self._position_context['mouse_y'])
            self._update_dock_targets(self._position_context)
            self._apply_position(self._position_context)
        now_ms = self._engine.now_ms
        self._advance_text_scramble(now_ms)
        self._advance_image_reveal(now_ms)
        self._advance_stack(now_ms)
        self.frame_tick.emit(now_ms)
        self.update()

    def _sync_engine_properties(self):
        values = {
            'dot_scale': '_dot_scale',
            'box_width': '_box_width',
            'box_height': '_box_height',
            'box_opacity': '_box_opacity',
            'vanish_ratio': '_vanish_ratio',
            'dock_right_progress': '_dock_right_progress',
            'dock_bottom_progress': '_dock_bottom_progress',
            'text_scroll_offset': '_text_scroll_offset',
        }
        for prop, attr in values.items():
            if self._engine.has_active(prop):
                setattr(self, attr, self._engine.get_value(prop, getattr(self, attr)))

    def _advance_text_scramble(self, now_ms: float):
        if self._scramble_start_ms is None:
            return
        duration = ANIMATION_DURATION['text_scramble']
        progress = min((now_ms - self._scramble_start_ms) / duration, 1.0)
        if (progress < 1.0 and self._last_scramble_refresh_ms is not None and
                now_ms - self._last_scramble_refresh_ms <
                TEXT_RENDER['scramble_refresh_ms']):
            return
        self._last_scramble_refresh_ms = now_ms
        solved_count = int(progress * len(self._text))
        if not self._scramble_buffer:
            self._reset_scramble_buffer()

        # 已解码字符只写入一次。未解码区保留上一帧的内容，并仅轮换少量
        # 噪声字符，避免每帧重建整段随机文本造成不连续的视觉闪烁。
        for index in range(self._scramble_solved_count, solved_count):
            self._scramble_buffer[index] = self._text[index]
        self._scramble_solved_count = solved_count

        block_end = min(solved_count + 4, len(self._text))
        for index in range(solved_count, block_end):
            self._scramble_buffer[index] = random.choice(BLOCK_CHARS)

        noise_start = block_end
        noise_length = len(self._text) - noise_start
        if noise_length:
            for offset in range(min(TEXT_RENDER['scramble_mutations_per_frame'],
                                    noise_length)):
                index = noise_start + ((self._scramble_noise_cursor + offset) %
                                       noise_length)
                self._scramble_buffer[index] = self._random_scramble_char()
            self._scramble_noise_cursor += TEXT_RENDER['scramble_mutations_per_frame']

        self._display_text = ''.join(self._scramble_buffer)
        if progress >= 1.0:
            self._display_text = self._text
            self._scramble_start_ms = None
            self._last_scramble_refresh_ms = None
            self._engine.set_frame_active('text_scramble', False)
            self._continue_after_text()

    def _reset_scramble_buffer(self):
        self._scramble_buffer = [self._random_scramble_char() for _ in self._text]
        self._scramble_solved_count = 0
        self._scramble_noise_cursor = 0
        self._display_text = ''.join(self._scramble_buffer)

    @staticmethod
    def _random_scramble_char() -> str:
        if random.random() < 0.6:
            return random.choice(SCRAMBLE_CHARS)
        return random.choice(BLOCK_CHARS[2:6])

    def _continue_after_text(self):
        if self._has_image:
            self._sm.transition('done_has_image')
        elif self._holding_mode:
            self._sm.transition('done_holding_no_image')
        else:
            self._sm.transition('done_normal_no_image')

    def _start_image_reveal(self):
        self._image_scramble_progress = 0.0
        self._image_reveal_start_ms = self._engine.now_ms
        self._engine.set_frame_active('image_reveal', True)

    def _advance_image_reveal(self, now_ms: float):
        if self._image_reveal_start_ms is None:
            return
        duration = ANIMATION_DURATION.get('image_reveal', 1000)
        self._image_scramble_progress = min(
            (now_ms - self._image_reveal_start_ms) / duration, 1.0)
        if self._image_scramble_progress >= 1.0:
            self._image_reveal_start_ms = None
            self._engine.set_frame_active('image_reveal', False)

    def _advance_stack(self, now_ms: float):
        if self._stack_phase not in ('appearing', 'retracting'):
            return
        raw = min((now_ms - self._stack_anim_start_ms) /
                  self._stack_anim_duration, 1.0)
        if self._stack_phase == 'appearing':
            eased = spring_ease(raw, stiffness=180, damping=14)
        else:
            eased = raw * raw
        self._stack_progress = self._stack_anim_from + (
            self._stack_anim_to - self._stack_anim_from) * eased
        if raw < 1.0:
            return
        self._stack_progress = self._stack_anim_to
        phase = self._stack_phase
        self._stack_phase = 'visible' if phase == 'appearing' else 'hidden'
        self._engine.set_frame_active('stack', False)
        if phase == 'appearing':
            self._sm.transition('done_holding' if self._holding_mode else 'done_normal')
        else:
            self._sm.transition('done')

    def _on_prop_finished(self, prop_name):
        if prop_name == 'box_height' and self._exit_after_collapse:
            self._exit_after_collapse = False
            self._timeout_while_expanded = False
            self.start_exit()
            return
        state = self._sm.state
        if state == AnimationState.DOT_APPEAR and prop_name == 'dot_scale':
            if self._feedback_type in (FeedbackType.ERROR, FeedbackType.PASTE):
                self._sm.transition('done_error_paste')
            elif self._raw_text:
                self._sm.transition('done_copy_with_text')
            else:
                self._sm.transition('done_copy_no_text')
        elif state == AnimationState.BOX_EXPAND and prop_name == 'box_width':
            self._sm.transition('done')
        elif state == AnimationState.BOX_SHRINK and prop_name == 'box_width':
            self._sm.transition('done')
        elif state == AnimationState.IMAGE_VANISH and prop_name == 'vanish_ratio':
            self._sm.transition('done')
        elif state == AnimationState.LINE_SHRINK and prop_name == 'box_height':
            self._sm.transition('done')
        elif state == AnimationState.DOT_DISAPPEAR and prop_name == 'dot_scale':
            self._sm.transition('done')

    def _on_state_timer(self):
        if self._sm.state == AnimationState.PULSE:
            self._sm.transition('timeout')
        elif self._sm.state == AnimationState.VIEWING:
            if self._defer_exit_while_expanded():
                return
            self._sm.transition('timeout_has_stack' if
                                self._image_count >= 2 and self._stack_phase == 'visible'
                                else 'timeout_no_stack')

    def _on_holding_timeout(self):
        if self._sm.state == AnimationState.HOLDING:
            if self._defer_exit_while_expanded():
                return
            self.start_exit()

    def _defer_exit_while_expanded(self) -> bool:
        if self._visible_line_count <= 1:
            return False
        self._timeout_while_expanded = True
        return True

    def _stop_timed_effects(self):
        self._scramble_start_ms = None
        self._last_scramble_refresh_ms = None
        self._scramble_buffer = []
        self._scramble_solved_count = 0
        self._scramble_noise_cursor = 0
        self._image_reveal_start_ms = None
        self._engine.cancel('text_scroll_offset')
        self._pending_scroll_column = None
        self._pending_scroll_alignment = 0.0
        self._text_alignment_offset = 0.0
        self._queued_scroll_direction = 0
        self._timeout_while_expanded = False
        self._exit_after_collapse = False
        self._text_scroll_offset = 0.0
        self._engine.set_frame_active('text_scramble', False)
        self._engine.set_frame_active('image_reveal', False)
        self._state_timer.stop()
        self._holding_timer.stop()

    def paintEvent(self, event):
        if not self._active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # All renderers keep using one logical coordinate system. Scaling once
        # here preserves their relative positions and the existing animation
        # properties; the QWidget canvas and mouse anchor use the same factor.
        painter.scale(self._ui_scale, self._ui_scale)
        right_progress = self._dock_progress('right')
        bottom_progress = (self._dock_progress('bottom')
                           if self._has_image else 0.0)
        direction = -1 if right_progress >= 0.5 else 1
        vertical_direction = -1 if bottom_progress >= 0.5 else 1
        dock_dot_cy = (bottom_dock_dot_y(
            self._image_count, self._image_layout_mode)
                       if self._has_image else DOT_CY)
        dot_cy = DOT_CY + (dock_dot_cy - DOT_CY) * bottom_progress
        logical_width = self.width() / self._ui_scale
        dot_cx = DOT_CX + (logical_width - 2 * DOT_CX) * right_progress
        if self._dot_scale > 0.01:
            DotRenderer.paint(painter, dot_cx, dot_cy, self._dot_scale, self._dot_color)
        if self._box_width > 1 and self._box_opacity > 0.01:
            final_text = self._display_text == self._text
            ContentBox.paint(painter, dot_cx, dot_cy, self._box_width,
                             self._box_height, self._box_opacity,
                             self._display_text, self._dot_scale,
                             self._text_style,
                             self._final_text_layout if final_text else None,
                             direction, right_progress,
                             viewport_text=self.can_navigate_text,
                             text_translation_x=(self._text_alignment_offset +
                                                 self._text_scroll_offset),
                             display_lines=(self._display_lines if final_text
                                            else [self._display_text]),
                             line_layouts=(self._line_layouts if final_text
                                           else None),
                             expanded_line_step=self._expanded_line_step())
        if self._has_image:
            image_x, image_y = image_base_pos(
                dot_cx, dot_cy, self._box_width, direction,
                bottom_progress >= 0.5, right_progress, bottom_progress,
                self._box_height)
            if self._image_layout_mode == IMAGE_LAYOUT_CASCADE:
                self._paint_cascade_images(
                    painter, image_x, image_y, dot_cx, dot_cy,
                    right_progress)
            elif self._stack_progress > 0.01 and self._image_count >= 2:
                for index in range(min(self._image_count - 1, 2) - 1, -1, -1):
                    thumbnail = (self._stack_thumbnail_cache[index + 1]
                                 if index + 1 < len(self._stack_thumbnail_cache) else None)
                    StackLayer.paint(painter, image_x, image_y,
                                     ImageRenderer.IMAGE_BOX_SIZE, index,
                                     self._stack_progress, self._images, thumbnail,
                                     direction, vertical_direction,
                                     right_progress, bottom_progress)
            if self._image_layout_mode != IMAGE_LAYOUT_CASCADE:
                ImageRenderer.paint(
                    painter, image_x, image_y, self._main_image,
                    self._image_scramble_progress, self._vanish_ratio,
                    dot_cx, dot_cy, self._main_image_cache)
        painter.end()

    def _paint_cascade_images(self, painter, image_x, image_y,
                              dot_cx, dot_cy, right_progress):
        """Paint horizontal cards back-to-front; image zero stays topmost."""
        count = max(1, self._image_count)
        opacities = IMAGE_STACK['cascade_opacities']
        for index in range(count - 1, -1, -1):
            if index > 0 and self._stack_progress <= 0.01:
                continue
            offset_x = cascade_layer_offset(
                index, count, right_progress, self._box_width,
                self._stack_progress)
            layer_opacity = float(opacities[min(index, len(opacities) - 1)])
            if index > 0:
                layer_opacity *= self._stack_progress
            image = self._images[index] if index < len(self._images) else None
            cache = (self._image_render_caches[index]
                     if index < len(self._image_render_caches) else None)
            ImageRenderer.paint(
                painter, image_x + offset_x, image_y, image,
                self._image_scramble_progress, self._vanish_ratio,
                dot_cx, dot_cy, cache, layer_opacity)
