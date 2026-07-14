"""反馈窗口：由单一单调帧时钟驱动完整动画生命周期。"""

import random
from enum import Enum, auto
from typing import List, Optional

from PySide6.QtCore import QPoint, QTimer, Qt, QEasingCurve, Signal
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QPainter, QPixmap,
                           QStaticText)
from PySide6.QtWidgets import QWidget

from config import (ANIMATION_DURATION, BLOCK_CHARS, COLORS, IMAGE_STACK,
                    SCRAMBLE_CHARS, SIZES, TEXT_RENDER)
from core.taskbar_boundary import TaskbarBoundary
from ui.animation.property_engine import PropertyEngine
from ui.animation.spring_ease import spring_ease
from ui.animation.state_machine import AnimationState, AnimationStateMachine
from ui.components.content_box import ContentBox
from ui.components.dot_renderer import DotRenderer
from ui.components.image_renderer import ImageRenderCache, ImageRenderer
from ui.components.stack_layer import StackLayer
from ui.feedback_layout import (DOT_CX, DOT_CY, dock_feedback_position,
                                bottom_dock_dot_y, image_base_pos,
                                visible_content_bounds,
                                window_size)
from ui.text_style import TextStyle, TextStyleResolver


class FeedbackType(Enum):
    COPY = auto()
    PASTE = auto()
    ERROR = auto()


class FeedbackWidget(QWidget):
    animation_complete = Signal()
    frame_tick = Signal(float)

    def __init__(self, feedback_type, text="", images=None,
                 image_count=0, holding_mode=False, parent=None,
                 ui_scale=1.0, cursor_offset=None):
        super().__init__(parent)
        self._ui_scale = max(1.0, min(float(ui_scale), 1.5))
        self._cursor_offset = cursor_offset or (
            float(SIZES['mouse_offset_x']), float(SIZES['mouse_offset_y']))
        self._feedback_type = feedback_type
        self._text = text
        self._text_style: TextStyle = TextStyleResolver.resolve(text)
        self._text = self._text_style.elide(text) if text else ''
        self._final_text_layout: Optional[QStaticText] = (
            self._text_style.static_layout(self._text) if self._text else None)
        self._image_count = min(image_count, IMAGE_STACK['max_display'])
        self._total_image_count = image_count
        self._holding_mode = holding_mode
        self._active = True
        self._images: List[QImage] = []
        self._main_image: Optional[QImage] = None
        self._main_image_cache: Optional[ImageRenderCache] = None
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
        self._dock_right = False
        self._dock_bottom = False

        self._target_width = 0.0
        if feedback_type == FeedbackType.COPY and self._text:
            self._target_width = min(
                SIZES['box_max_width'],
                max(SIZES['box_min_width'],
                    self._text_style.horizontal_advance(self._text) +
                    SIZES['box_padding']))

        if feedback_type == FeedbackType.ERROR:
            self._dot_color = QColor(COLORS['dot_error'])
        elif feedback_type == FeedbackType.PASTE:
            self._dot_color = QColor(COLORS['dot_paste'])
        else:
            self._dot_color = QColor(COLORS['dot_copy'])

        self._sm = AnimationStateMachine(self)
        self._sm.action_requested.connect(self._execute_action)
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

    def move_to_position(self, x, y):
        screen = QGuiApplication.screenAt(QPoint(int(x), int(y)))
        if screen is not None:
            available = screen.availableGeometry()
            geometry = screen.geometry()
            normal_right, normal_bottom = visible_content_bounds(
                self._target_width, self._has_image, self._image_count)
            normal_bottom_edge = (y + self._cursor_offset[1] - DOT_CY * self._ui_scale +
                                  normal_bottom * self._ui_scale)
            screen_bottom = geometry.y() + geometry.height()
            if (normal_bottom_edge > available.y() + available.height() -
                    12 * self._ui_scale or
                    y > screen_bottom - 96 * self._ui_scale):
                effective_bottom = TaskbarBoundary.effective_bottom(
                    screen, int(self.winId()))
            else:
                effective_bottom = available.y() + available.height()
            bottom_docked = (normal_bottom_edge > effective_bottom -
                             12 * self._ui_scale)
            image_above = bottom_docked and self._has_image
            dot_cy = (bottom_dock_dot_y(self._image_count)
                      if image_above else DOT_CY)
            visible_right, visible_bottom = visible_content_bounds(
                self._target_width, self._has_image, self._image_count,
                dot_cy, image_above)
            win_x, win_y, dock_right = dock_feedback_position(
                x, y, self.width(), self._ui_scale, *self._cursor_offset,
                visible_right, visible_bottom,
                (available.x(), available.y(),
                 available.width(),
                 max(0, int(effective_bottom - available.y()))), dot_cy)
            if self._dock_right != dock_right or self._dock_bottom != bottom_docked:
                self._dock_right = dock_right
                self._dock_bottom = bottom_docked
                self.update()
        else:
            # This only occurs transiently while displays are reconfigured.
            visible_right, visible_bottom = visible_content_bounds(
                self._target_width, self._has_image, self._image_count)
            win_x, win_y, dock_right = dock_feedback_position(
                x, y, self.width(), self._ui_scale, *self._cursor_offset,
                visible_right, visible_bottom, (0, 0, 100000, 100000))
            self._dock_right = dock_right
            self._dock_bottom = False
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
        self._has_image = True
        self._awaiting_images = False
        self._resize_to_content()
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
        for image in (images or [])[:IMAGE_STACK['max_display']]:
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
            self._stack_thumbnail_cache = [None]
            for image in self._images[1:IMAGE_STACK['max_display']]:
                scaled = image.scaled(ImageRenderer.IMAGE_BOX_SIZE,
                                      ImageRenderer.IMAGE_BOX_SIZE,
                                      Qt.KeepAspectRatioByExpanding,
                                      Qt.FastTransformation)
                self._stack_thumbnail_cache.append(QPixmap.fromImage(scaled))

    def _resize_to_content(self) -> None:
        self.setFixedSize(*window_size(
            self._target_width, self._has_image, self._ui_scale))

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
        state = self._sm.state
        if state == AnimationState.DOT_APPEAR and prop_name == 'dot_scale':
            if self._feedback_type in (FeedbackType.ERROR, FeedbackType.PASTE):
                self._sm.transition('done_error_paste')
            elif self._text:
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
            self._sm.transition('timeout_has_stack' if
                                self._image_count >= 2 and self._stack_phase == 'visible'
                                else 'timeout_no_stack')

    def _on_holding_timeout(self):
        if self._sm.state == AnimationState.HOLDING:
            self.start_exit()

    def _stop_timed_effects(self):
        self._scramble_start_ms = None
        self._last_scramble_refresh_ms = None
        self._scramble_buffer = []
        self._scramble_solved_count = 0
        self._scramble_noise_cursor = 0
        self._image_reveal_start_ms = None
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
        direction = -1 if self._dock_right else 1
        image_above = self._dock_bottom and self._has_image
        dot_cy = (bottom_dock_dot_y(self._image_count)
                  if image_above else DOT_CY)
        logical_width = self.width() / self._ui_scale
        dot_cx = logical_width - DOT_CX if self._dock_right else DOT_CX
        if self._dot_scale > 0.01:
            DotRenderer.paint(painter, dot_cx, dot_cy, self._dot_scale, self._dot_color)
        if self._box_width > 1 and self._box_opacity > 0.01:
            ContentBox.paint(painter, dot_cx, dot_cy, self._box_width,
                             self._box_height, self._box_opacity,
                             self._display_text, self._dot_scale,
                             self._text_style,
                             self._final_text_layout if self._display_text == self._text else None,
                             direction)
        if self._has_image:
            image_x, image_y = image_base_pos(
                dot_cx, dot_cy, self._target_width, direction, image_above)
            if self._stack_progress > 0.01 and self._image_count >= 2:
                for index in range(min(self._image_count - 1, 2) - 1, -1, -1):
                    thumbnail = (self._stack_thumbnail_cache[index + 1]
                                 if index + 1 < len(self._stack_thumbnail_cache) else None)
                    StackLayer.paint(painter, image_x, image_y,
                                     ImageRenderer.IMAGE_BOX_SIZE, index,
                                     self._stack_progress, self._images, thumbnail,
                                     direction, -1 if image_above else 1)
            ImageRenderer.paint(painter, image_x, image_y, self._main_image,
                                self._image_scramble_progress, self._vanish_ratio,
                                dot_cx, dot_cy, self._main_image_cache)
        painter.end()
