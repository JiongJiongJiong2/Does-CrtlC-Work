"""
FeedbackWidget - 自恢复多态动画窗口容器（重构版）
驱动"亮灯-舒展-文字揭现-多图堆叠-持留-退场"全生命周期动画
"""

import random
import time
from enum import Enum, auto
from PySide6.QtCore import QTimer, Qt, QEasingCurve, Signal
from PySide6.QtGui import QPainter, QColor, QImage
from PySide6.QtWidgets import QWidget

from config import (COLORS, SIZES, ANIMATION_DURATION,
                    BLOCK_CHARS, SCRAMBLE_CHARS, IMAGE_STACK)
from ui.animation.state_machine import AnimationStateMachine, AnimationState
from ui.animation.property_engine import PropertyEngine
from ui.animation.spring_ease import spring_ease
from ui.components.dot_renderer import DotRenderer
from ui.components.content_box import ContentBox
from ui.components.image_renderer import ImageRenderer
from ui.components.stack_layer import StackLayer
from ui.feedback_layout import DOT_CX, DOT_CY, window_size, image_base_pos, mouse_to_window


class FeedbackType(Enum):
    COPY = auto()
    PASTE = auto()
    ERROR = auto()


class FeedbackWidget(QWidget):
    animation_complete = Signal()

    def __init__(self, feedback_type, text="", images=None,
                 image_count=0, holding_mode=False, parent=None):
        super().__init__(parent)
        self._feedback_type = feedback_type
        self._text = text
        self._image_count = min(image_count, IMAGE_STACK['max_display'])
        self._total_image_count = image_count
        self._holding_mode = holding_mode
        self._active = True
        self._images = []
        if images:
            for img in images[:IMAGE_STACK['max_display']]:
                if isinstance(img, QImage) and not img.isNull():
                    self._images.append(img.copy())
        self._has_image = len(self._images) > 0 or image_count > 0
        self._main_image = self._images[0] if self._images else None
        self._awaiting_images = image_count > 0 and len(self._images) == 0
        self._dot_scale = 0.0
        self._box_width = 0.0
        self._box_height = SIZES['box_height']
        self._box_opacity = 0.0
        self._stack_progress = 0.0
        self._stack_phase = 'hidden'
        self._stack_anim_start = 0.0
        self._stack_anim_duration = 220
        self._stack_anim_from = 0.0
        self._stack_anim_to = 1.0
        if feedback_type == FeedbackType.COPY and text:
            self._target_width = min(SIZES['box_max_width'],
                max(SIZES['box_min_width'],
                    len(text) * SIZES['char_width'] + SIZES['box_padding']))
        else:
            self._target_width = 0
        if feedback_type == FeedbackType.ERROR:
            self._dot_color = QColor(COLORS['dot_error'])
        elif feedback_type == FeedbackType.PASTE:
            self._dot_color = QColor(COLORS['dot_paste'])
        else:
            self._dot_color = QColor(COLORS['dot_copy'])
        self._image_scramble_progress = 0.0
        self._vanish_ratio = 1.0  # 图片退场收缩比例 (1.0=完整, 0.0=消失)
        self._display_text = ""
        self._scramble_start_time = 0
        self._sm = AnimationStateMachine(self)
        self._sm.action_requested.connect(self._execute_action)
        self._engine = PropertyEngine(self)
        self._engine.tick.connect(self._sync_engine_props)
        self._engine.finished.connect(self._on_prop_finished)
        self._stack_anim_timer = QTimer(self)
        self._stack_anim_timer.timeout.connect(self._stack_anim_tick)
        self._stack_anim_timer.setInterval(16)
        self._scramble_timer = QTimer(self)
        self._scramble_timer.timeout.connect(self._scramble_tick)
        self._scramble_timer.setInterval(16)
        self._image_scramble_timer = QTimer(self)
        self._image_scramble_timer.timeout.connect(self._image_scramble_tick)
        self._image_scramble_timer.setInterval(40)
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
        w, h = window_size(self._target_width, self._has_image)
        self.setFixedSize(w, h)

    # === 公共接口 ===
    def start_animation(self):
        self._sm.transition('start')
        if self._has_image:
            self._image_scramble_progress = 0.0
            self._image_scramble_timer.start()
        self.show()

    def start_exit(self):
        if self._sm.state in (AnimationState.VIEWING, AnimationState.HOLDING,
                              AnimationState.STACK_APPEAR, AnimationState.IMAGE_APPEAR):
            if self._image_count >= 2 and self._stack_phase == 'visible':
                self._sm.transition('exit_has_stack')
            else:
                self._sm.transition('exit_no_stack')

    def move_to_position(self, x, y):
        self.move(*mouse_to_window(x, y))

    def update_images(self, images, image_count):
        if not self._active:
            return
        new_imgs = []
        if images:
            for img in images[:IMAGE_STACK['max_display']]:
                if isinstance(img, QImage) and not img.isNull():
                    new_imgs.append(img.copy())
        if not new_imgs:
            return
        self._images.extend(new_imgs)
        self._total_image_count = image_count
        self._has_image = True
        if self._images:
            self._main_image = self._images[0]
        w, h = window_size(self._target_width, self._has_image)
        self.setFixedSize(w, h)
        self._image_scramble_progress = 0.0
        if not self._image_scramble_timer.isActive():
            self._image_scramble_timer.start()
        self.update()

    def stop(self):
        self._active = False
        self._engine.stop()
        self._sm.reset()
        self._scramble_timer.stop()
        self._image_scramble_timer.stop()
        self._stack_anim_timer.stop()
        self._state_timer.stop()
        self._holding_timer.stop()
        self.close()

    # === 状态机动作 ===
    def _execute_action(self, action):
        dispatch = {
            'animate_dot_appear': self._act_dot_appear,
            'animate_box_expand': self._act_box_expand,
            'start_scramble': self._act_start_scramble,
            'enter_image_or_viewing': self._act_enter_image_or_viewing,
            'animate_stack': self._act_stack_appear,
            'start_view_timer': self._act_view_timer,
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
            if self._has_image:
                self._sm.transition('done_has_image')
            elif self._holding_mode:
                self._sm.transition('done_holding_no_image')
            else:
                self._sm.transition('done_normal_no_image')
            return
        self._scramble_start_time = time.time()
        self._display_text = ""  # 初始不显示白色块，等 scramble_tick 逐步显现
        self._scramble_timer.start()

    def _act_enter_image_or_viewing(self):
        if self._has_image or self._awaiting_images:
            if self._image_count >= 2:
                self._sm.transition('done_multi_image')
            elif self._holding_mode:
                self._sm.transition('done_holding_single')
            else:
                self._sm.transition('done_normal_single')
        else:
            # 无图片，直接进入 VIEWING 或 HOLDING
            if self._holding_mode:
                self._sm.transition('done_holding_single')
            else:
                self._sm.transition('done_normal_single')

    def _act_stack_appear(self):
        self._stack_phase = 'appearing'
        self._stack_anim_from = 0.0
        self._stack_anim_to = 1.0
        self._stack_anim_start = time.time()
        self._stack_anim_timer.start()

    def _act_view_timer(self):
        self._state_timer.start(ANIMATION_DURATION.get('view_time', 2800))

    def _act_holding_timer(self):
        self._holding_timer.start(ANIMATION_DURATION.get('holding_max', 30000))

    def _act_stack_retract(self):
        self._stack_phase = 'retracting'
        self._stack_anim_from = self._stack_progress
        self._stack_anim_to = 0.0
        self._stack_anim_start = time.time()
        self._stack_anim_timer.start()

    def _act_image_vanish(self):
        """图片退场收缩动画"""
        if not self._has_image:
            # 无图片，直接跳过
            self._sm.transition('done')
            return
        self._engine.animate('vanish_ratio', 1.0, 0.0,
            ANIMATION_DURATION.get('image_vanish', 200),
            QEasingCurve(QEasingCurve.InQuad))

    def _act_box_shrink(self):
        self._box_opacity = 0.0
        self._engine.animate('box_width', self._box_width, 0.0,
            ANIMATION_DURATION['box_shrink'],
            QEasingCurve(QEasingCurve.InQuad))

    def _act_line_shrink(self):
        self._engine.animate('box_height', self._box_height, 0.0,
            ANIMATION_DURATION['line_shrink'],
            QEasingCurve(QEasingCurve.InQuad))

    def _act_dot_disappear(self):
        self._engine.animate('dot_scale', self._dot_scale, 0.0,
            ANIMATION_DURATION['dot_disappear'],
            QEasingCurve(QEasingCurve.InQuad))

    def _act_complete(self):
        self._active = False
        self.animation_complete.emit()
        self.close()

    def _sync_engine_props(self):
        """从 PropertyEngine 同步属性值到实例变量"""
        if self._engine.has_active('dot_scale'):
            self._dot_scale = self._engine.get_value('dot_scale', self._dot_scale)
        if self._engine.has_active('box_width'):
            self._box_width = self._engine.get_value('box_width', self._box_width)
        if self._engine.has_active('box_height'):
            self._box_height = self._engine.get_value('box_height', self._box_height)
        if self._engine.has_active('vanish_ratio'):
            self._vanish_ratio = self._engine.get_value('vanish_ratio', self._vanish_ratio)
        self.update()

    def _on_prop_finished(self, prop_name):
        state = self._sm.state
        if state == AnimationState.DOT_APPEAR and prop_name == 'dot_scale':
            # 根据反馈类型和内容发送区分上下文的事件
            if self._feedback_type == FeedbackType.ERROR:
                self._sm.transition('done_error_paste')
            elif self._feedback_type == FeedbackType.PASTE:
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
        if self._sm.state == AnimationState.VIEWING:
            if self._image_count >= 2 and self._stack_phase == 'hidden':
                self._sm.transition('timeout_has_stack')
            else:
                self._sm.transition('timeout_no_stack')

    def _on_holding_timeout(self):
        if self._sm.state == AnimationState.HOLDING:
            if self._image_count >= 2 and self._stack_phase == 'visible':
                self._sm.transition('exit_has_stack')
            else:
                self._sm.transition('exit_no_stack')

    def _scramble_tick(self):
        elapsed = time.time() - self._scramble_start_time
        total_dur = ANIMATION_DURATION.get('text_scramble', 1000) / 1000.0
        progress = min(1.0, elapsed / total_dur)
        result = []
        last_char = None  # 跟踪上一个字符，避免连续重复
        for i, ch in enumerate(self._text):
            char_start = (i / max(len(self._text), 1)) * 0.6
            char_prog = min(1.0, max(0.0, (progress - char_start) / 0.4))
            if char_prog >= 1.0:
                result.append(ch)
                last_char = ch
            elif char_prog > 0:
                # 混合使用 BLOCK_CHARS 和 SCRAMBLE_CHARS，避免连续相同
                if random.random() < 0.5:
                    pool = BLOCK_CHARS
                else:
                    pool = SCRAMBLE_CHARS if ch.isalnum() else BLOCK_CHARS
                choices = [c for c in pool if c != last_char]
                chosen = random.choice(choices) if choices else random.choice(pool)
                result.append(chosen)
                last_char = chosen
            else:
                # 未解码区域：不显示白色块，用空格占位
                result.append(' ')
                last_char = None
        self._display_text = ''.join(result)
        self.update()
        if progress >= 1.0:
            self._scramble_timer.stop()
            self._display_text = self._text
            if self._has_image:
                self._sm.transition('done_has_image')
            elif self._holding_mode:
                self._sm.transition('done_holding_no_image')
            else:
                self._sm.transition('done_normal_no_image')

    def _image_scramble_tick(self):
        self._image_scramble_progress += 0.12
        if self._image_scramble_progress >= 1.0:
            self._image_scramble_progress = 1.0
            self._image_scramble_timer.stop()
        self.update()

    def _stack_anim_tick(self):
        elapsed_ms = (time.time() - self._stack_anim_start) * 1000
        t = min(1.0, elapsed_ms / self._stack_anim_duration)
        value = spring_ease(self._stack_anim_from, self._stack_anim_to, t)
        self._stack_progress = value
        self.update()
        if t >= 1.0:
            self._stack_anim_timer.stop()
            self._stack_progress = self._stack_anim_to
            if self._stack_phase == 'appearing':
                self._stack_phase = 'visible'
                if self._holding_mode:
                    self._sm.transition('done_holding')
                else:
                    self._sm.transition('done_normal')
            elif self._stack_phase == 'retracting':
                self._stack_phase = 'hidden'
                self._sm.transition('done')

    def paintEvent(self, event):
        if not self._active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        dot_cx = DOT_CX
        dot_cy = DOT_CY
        if self._dot_scale > 0.01:
            DotRenderer.paint(painter, dot_cx, dot_cy,
                              self._dot_scale, self._dot_color)
        if self._box_width > 1 and self._box_opacity > 0.01:
            ContentBox.paint(painter, dot_cx, dot_cy,
                             self._box_width, self._box_height,
                             self._box_opacity, self._display_text,
                             self._dot_scale)
        if self._has_image:
            img_x, img_y = image_base_pos(dot_cx, dot_cy, self._target_width)
            if self._stack_progress > 0.01 and self._image_count >= 2:
                for i in range(min(self._image_count - 1, 2) - 1, -1, -1):
                    StackLayer.paint(painter, img_x, img_y,
                                     ImageRenderer.IMAGE_BOX_SIZE,
                                     i, self._stack_progress, self._images)
            ImageRenderer.paint(painter, img_x, img_y,
                                self._main_image,
                                self._image_scramble_progress,
                                self._vanish_ratio, dot_cx, dot_cy)
        painter.end()
