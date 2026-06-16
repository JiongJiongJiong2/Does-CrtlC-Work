"""
FeedbackWidget - 自恢复多态动画窗口容器
驱动"亮灯-舒展-文字揭现-多图堆叠-持留-退场"全生命周期动画

动画序列 (copy 成功):
1. 圆点出现 (Spring 弹出)
2. 黑色透明框从左向右展开
3. ScrambleText 文字解码揭示
4. 图片像素化渐显 + 堆叠层弹出（多图时）
5. 持留等待（holding 模式：直到粘贴；普通模式：定时）
6. 堆叠层回收（多图时）
7. 框+图片向圆点收缩
8. 圆点消失

动画序列 (error/paste):
1. 圆点出现
2. 等待短暂时间
3. 圆点消失
"""

import math
import random
import time
from enum import Enum, auto
from PySide6.QtCore import QTimer, Qt, QEasingCurve, Signal
from PySide6.QtGui import (QPainter, QColor, QLinearGradient, QRadialGradient,
                            QPen, QFont, QImage, QPixmap, QPainterPath, QTransform)
from PySide6.QtWidgets import QWidget

from config import COLORS, SIZES, ANIMATION_DURATION, BLOCK_CHARS, SCRAMBLE_CHARS, IMAGE_STACK


class FeedbackType(Enum):
    COPY = auto()
    PASTE = auto()
    ERROR = auto()


class AnimationState(Enum):
    IDLE = auto()
    DOT_APPEAR = auto()
    BOX_EXPAND = auto()
    TEXT_REVEAL = auto()
    IMAGE_APPEAR = auto()
    STACK_APPEAR = auto()
    VIEWING = auto()
    HOLDING = auto()           # 持留：等待粘贴或超时
    STACK_RETRACT = auto()
    BOX_SHRINK = auto()
    LINE_SHRINK = auto()
    DOT_DISAPPEAR = auto()
    COMPLETE = auto()


class FeedbackWidget(QWidget):
    """反馈动画窗口 - 跟随鼠标的动画提示"""

    animation_complete = Signal()

    def __init__(self, feedback_type: FeedbackType, text: str = "",
                 images=None, image_count: int = 0,
                 holding_mode: bool = False, parent=None):
        super().__init__(parent)

        self._feedback_type = feedback_type
        self._text = text
        self._image_count = min(image_count, IMAGE_STACK['max_display'])
        self._total_image_count = image_count  # 实际总数（可能 > max_display）
        self._holding_mode = holding_mode
        self._state = AnimationState.IDLE
        self._active = True

        # 图片数据：主图 + 堆叠层
        self._images = []
        if images:
            for img in images[:IMAGE_STACK['max_display']]:
                if isinstance(img, QImage) and not img.isNull():
                    self._images.append(img.copy())
        # Bug 2 修复：即使 images 为空但 image_count > 0，也标记为有图片（预留区域）
        self._has_image = len(self._images) > 0 or image_count > 0
        self._main_image = self._images[0] if self._images else None
        self._awaiting_images = image_count > 0 and len(self._images) == 0  # 等待异步图片

        # 动画参数
        self._dot_scale = 0.0
        self._box_width = 0.0
        self._box_height = SIZES['box_height']
        self._box_opacity = 0.0

        # 堆叠层动画参数
        self._stack_progress = 0.0    # 0=隐藏, 1=完全展开
        self._stack_phase = 'hidden'  # hidden / appearing / visible / retracting

        # 计算目标框宽度
        if feedback_type == FeedbackType.COPY and text:
            self._target_width = min(
                SIZES['box_max_width'],
                max(SIZES['box_min_width'], len(text) * SIZES['char_width'] + SIZES['box_padding'])
            )
        else:
            self._target_width = 0

        # 圆点颜色
        if feedback_type == FeedbackType.ERROR:
            self._dot_color = QColor(COLORS['dot_error'])
        elif feedback_type == FeedbackType.PASTE:
            self._dot_color = QColor(COLORS['dot_paste'])
        else:
            self._dot_color = QColor(COLORS['dot_copy'])

        # Scramble 文字参数
        self._display_text = ""
        self._scramble_start_time = 0
        self._scramble_timer = QTimer(self)
        self._scramble_timer.timeout.connect(self._scramble_tick)
        self._scramble_timer.setInterval(16)

        # 图片像素扰动参数
        self._image_box_size = 120
        self._image_corner_radius = 16
        self._image_scramble_progress = 0.0
        self._image_scramble_timer = QTimer(self)
        self._image_scramble_timer.timeout.connect(self._image_scramble_tick)
        self._image_scramble_timer.setInterval(40)

        # 堆叠层动画定时器
        self._stack_anim_timer = QTimer(self)
        self._stack_anim_timer.timeout.connect(self._stack_anim_tick)
        self._stack_anim_timer.setInterval(16)

        # holding 超时定时器
        self._holding_timer = QTimer(self)
        self._holding_timer.setSingleShot(True)
        self._holding_timer.timeout.connect(self._on_holding_timeout)

        # 设置窗口属性
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # 计算窗口尺寸
        content_w = int(self._target_width + 40) if self._target_width else 100
        image_w = self._image_box_size + 60 if self._has_image else 0
        max_w = max(content_w, image_w, 220)

        max_h = int(SIZES['box_height'] + SIZES['dot_radius'] * 2 + 30)
        if self._has_image:
            max_h += self._image_box_size + 20

        self.setFixedSize(max(max_w, 500), max(max_h, 180))

        # 动画定时器
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._animation_tick)
        self._anim_timer.setInterval(16)

        # 状态定时器
        self._state_timer = QTimer(self)
        self._state_timer.setSingleShot(True)
        self._state_timer.timeout.connect(self._advance_state)

        # 当前动画参数
        self._anim_property = ""
        self._anim_start_value = 0.0
        self._anim_end_value = 0.0
        self._anim_duration = 0
        self._anim_start_time = 0.0
        self._anim_easing = QEasingCurve(QEasingCurve.OutQuad)

    def start_animation(self):
        """开始动画序列"""
        self._state = AnimationState.DOT_APPEAR
        self._start_property_animation('dot_scale', 0.0, 1.0,
                                       ANIMATION_DURATION['dot_appear'],
                                       QEasingCurve(QEasingCurve.OutBack))
        if self._has_image:
            self._image_scramble_progress = 0.0
            self._image_scramble_timer.start()
        self.show()

    def start_exit(self):
        """外部触发退场（如检测到粘贴）"""
        if self._state in (AnimationState.VIEWING, AnimationState.HOLDING,
                           AnimationState.STACK_APPEAR, AnimationState.IMAGE_APPEAR):
            # 先回收堆叠层
            if self._image_count >= 2 and self._stack_phase == 'visible':
                self._state = AnimationState.STACK_RETRACT
                self._stack_phase = 'retracting'
                self._stack_anim_start = time.time() * 1000
                self._stack_anim_duration = ANIMATION_DURATION.get('stack_retract', 220)
                self._stack_anim_from = self._stack_progress
                self._stack_anim_to = 0.0
                if not self._stack_anim_timer.isActive():
                    self._stack_anim_timer.start()
            else:
                self._begin_box_shrink()

    def _begin_box_shrink(self):
        """开始框收缩退场"""
        self._state = AnimationState.BOX_SHRINK
        self._start_property_animation('box_width', self._target_width, 2.0,
                                       ANIMATION_DURATION['box_shrink'],
                                       QEasingCurve(QEasingCurve.InQuad))

    def _start_property_animation(self, prop: str, start: float, end: float,
                                   duration: int, easing: QEasingCurve = None):
        self._anim_property = prop
        self._anim_start_value = start
        self._anim_end_value = end
        self._anim_duration = duration
        self._anim_start_time = time.time() * 1000
        self._anim_easing = easing
        setattr(self, f'_{prop}', start)
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def _animation_tick(self):
        now = time.time() * 1000
        elapsed = now - self._anim_start_time
        raw_progress = min(elapsed / self._anim_duration, 1.0) if self._anim_duration > 0 else 1.0
        eased_progress = self._anim_easing.valueForProgress(raw_progress)
        current_value = self._anim_start_value + (self._anim_end_value - self._anim_start_value) * eased_progress
        setattr(self, f'_{self._anim_property}', current_value)

        if self._anim_property == 'box_height':
            self._box_height = current_value
            if self._state == AnimationState.LINE_SHRINK:
                height_ratio = current_value / SIZES['box_height'] if SIZES['box_height'] > 0 else 0
                self._box_opacity = height_ratio

        self.update()

        if raw_progress >= 1.0:
            setattr(self, f'_{self._anim_property}', self._anim_end_value)
            self._anim_timer.stop()
            self._on_animation_finished()

    def _on_animation_finished(self):
        if not self._active:
            return

        if self._state == AnimationState.DOT_APPEAR:
            if self._feedback_type == FeedbackType.COPY:
                if self._target_width > 0:
                    self._state = AnimationState.BOX_EXPAND
                    self._box_opacity = 1.0
                    self._start_property_animation('box_width', 0.0, self._target_width,
                                                   ANIMATION_DURATION['box_expand'],
                                                   QEasingCurve(QEasingCurve.OutQuad))
                else:
                    self._enter_image_or_viewing()
            else:
                self._state = AnimationState.VIEWING
                self._state_timer.start(ANIMATION_DURATION['error_display'])

        elif self._state == AnimationState.BOX_EXPAND:
            self._start_scramble_text()

        elif self._state == AnimationState.BOX_SHRINK:
            self._state = AnimationState.LINE_SHRINK
            self._start_property_animation('box_height', SIZES['box_height'], 0.0,
                                           ANIMATION_DURATION['line_shrink'],
                                           QEasingCurve(QEasingCurve.Linear))

        elif self._state == AnimationState.LINE_SHRINK:
            self._state = AnimationState.DOT_DISAPPEAR
            self._start_property_animation('dot_scale', 1.0, 0.0,
                                           ANIMATION_DURATION['dot_disappear'],
                                           QEasingCurve(QEasingCurve.InBack))

        elif self._state == AnimationState.DOT_DISAPPEAR:
            self._state = AnimationState.COMPLETE
            self._active = False
            self.animation_complete.emit()
            self.close()

    def _enter_image_or_viewing(self):
        """进入图片显示或直接 viewing"""
        if self._has_image:
            self._state = AnimationState.IMAGE_APPEAR
            # 图片已在 scramble，等一小段时间后弹堆叠
            self._state_timer.start(300)
        else:
            self._enter_holding_or_viewing()

    def _enter_holding_or_viewing(self):
        """进入持留或普通 viewing"""
        if self._holding_mode:
            self._state = AnimationState.HOLDING
            self._holding_timer.start(ANIMATION_DURATION.get('holding_max', 30000))
        else:
            self._state = AnimationState.VIEWING
            self._state_timer.start(ANIMATION_DURATION['view_time'])

    def _advance_state(self):
        if not self._active:
            return

        if self._state == AnimationState.TEXT_REVEAL:
            self._scramble_timer.stop()
            self._display_text = self._text
            self._enter_image_or_viewing()

        elif self._state == AnimationState.IMAGE_APPEAR:
            # 图片已显示，弹堆叠层
            if self._image_count >= 2:
                self._state = AnimationState.STACK_APPEAR
                self._stack_phase = 'appearing'
                self._stack_anim_start = time.time() * 1000
                self._stack_anim_duration = ANIMATION_DURATION.get('stack_appear', 220)
                self._stack_anim_from = 0.0
                self._stack_anim_to = 1.0
                self._stack_anim_timer.start()
            else:
                self._enter_holding_or_viewing()

        elif self._state == AnimationState.VIEWING:
            # 退场：先回收堆叠层（如有），再框收缩
            if self._image_count >= 2 and self._stack_phase == 'visible':
                self._state = AnimationState.STACK_RETRACT
                self._stack_phase = 'retracting'
                self._stack_anim_start = time.time() * 1000
                self._stack_anim_duration = ANIMATION_DURATION.get('stack_retract', 220)
                self._stack_anim_from = self._stack_progress
                self._stack_anim_to = 0.0
                if not self._stack_anim_timer.isActive():
                    self._stack_anim_timer.start()
            else:
                self._begin_box_shrink()

    def _on_holding_timeout(self):
        """holding 超时，开始退场"""
        if self._state == AnimationState.HOLDING:
            self.start_exit()

    def _stack_anim_tick(self):
        """堆叠层动画帧"""
        now = time.time() * 1000
        elapsed = now - self._stack_anim_start
        raw = min(elapsed / self._stack_anim_duration, 1.0) if self._stack_anim_duration > 0 else 1.0

        if self._stack_phase == 'appearing':
            # 弹簧效果
            eased = self._spring_ease(raw, stiffness=180, damping=14)
            self._stack_progress = self._stack_anim_from + (self._stack_anim_to - self._stack_anim_from) * eased
        elif self._stack_phase == 'retracting':
            eased = raw * raw  # easeIn
            self._stack_progress = self._stack_anim_from + (self._stack_anim_to - self._stack_anim_from) * eased

        self.update()

        if raw >= 1.0:
            self._stack_progress = self._stack_anim_to
            self._stack_anim_timer.stop()

            if self._stack_phase == 'appearing':
                self._stack_phase = 'visible'
                self._enter_holding_or_viewing()
            elif self._stack_phase == 'retracting':
                self._stack_phase = 'hidden'
                self._begin_box_shrink()

    @staticmethod
    def _spring_ease(t: float, stiffness: float = 180, damping: float = 14) -> float:
        """简易弹簧缓动"""
        import math as _m
        omega = _m.sqrt(stiffness)
        zeta = damping / (2 * omega)
        if zeta < 1.0:
            omega_d = omega * _m.sqrt(1.0 - zeta * zeta)
            return 1.0 - _m.exp(-zeta * omega * t) * (_m.cos(omega_d * t) +
                   (zeta * omega / omega_d) * _m.sin(omega_d * t))
        else:
            return 1.0 - (1.0 + omega * t) * _m.exp(-omega * t)

    def _start_scramble_text(self):
        if not self._text:
            self._enter_image_or_viewing()
            return
        self._state = AnimationState.TEXT_REVEAL
        self._scramble_start_time = time.time() * 1000
        self._scramble_timer.start()
        # 不在此设置 _state_timer — scramble 完成后由 _scramble_tick 触发状态转换

    def _scramble_tick(self):
        now = time.time() * 1000
        elapsed = now - self._scramble_start_time
        duration = ANIMATION_DURATION['text_scramble']
        progress = min(elapsed / duration, 1.0)

        text_len = len(self._text)
        solved_count = int(progress * text_len)

        current = []
        for i in range(text_len):
            if i < solved_count:
                current.append(self._text[i])
            elif i < solved_count + 4:
                current.append(random.choice(BLOCK_CHARS))
            elif random.random() < 0.6:
                current.append(random.choice(SCRAMBLE_CHARS))
            else:
                current.append(random.choice(BLOCK_CHARS[2:6]))

        self._display_text = ''.join(current)

        if progress >= 1.0:
            self._display_text = self._text
            self._scramble_timer.stop()
            # scramble 完成，触发状态转换
            if self._state == AnimationState.TEXT_REVEAL:
                self._advance_state()
        self.update()

    def _image_scramble_tick(self):
        if not self._active:
            self._image_scramble_timer.stop()
            return
        self._image_scramble_progress = min(1.0, self._image_scramble_progress + 0.04)
        if self._image_scramble_progress >= 1.0:
            self._image_scramble_timer.stop()
        self.update()

    def _get_image_vanish_ratio(self) -> float:
        if not self._has_image:
            return 0.0
        if self._state == AnimationState.BOX_SHRINK:
            base = max(float(self._target_width), 1.0)
            return max(0.0, min(1.0, float(self._box_width) / base))
        if self._state == AnimationState.LINE_SHRINK:
            return 0.06
        if self._state == AnimationState.DOT_DISAPPEAR:
            return max(0.0, min(1.0, float(self._dot_scale))) * 0.06
        return 1.0

    def move_to_position(self, x: float, y: float):
        dot_x = x + SIZES['mouse_offset_x']
        dot_y = y + SIZES['mouse_offset_y']
        self.move(int(dot_x - 5), int(dot_y - 5))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        dot_cx = 5
        dot_cy = 5
        dot_radius = SIZES['dot_radius']

        # 绘制圆点
        if self._dot_scale > 0:
            scaled_radius = dot_radius * self._dot_scale
            glow = QRadialGradient(dot_cx, dot_cy, scaled_radius * 2)
            glow.setColorAt(0, QColor(self._dot_color.red(), self._dot_color.green(),
                                       self._dot_color.blue(), 150))
            glow.setColorAt(1, QColor(self._dot_color.red(), self._dot_color.green(),
                                       self._dot_color.blue(), 0))
            painter.setBrush(glow)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(dot_cx - scaled_radius * 2, dot_cy - scaled_radius * 2,
                               scaled_radius * 4, scaled_radius * 4)
            painter.setBrush(self._dot_color)
            painter.drawEllipse(dot_cx - scaled_radius, dot_cy - scaled_radius,
                               scaled_radius * 2, scaled_radius * 2)

        # 绘制内容框
        if self._feedback_type == FeedbackType.COPY and self._box_width > 0:
            box_x = dot_cx
            box_y = dot_cy
            box_w = self._box_width
            box_h = self._box_height

            if self._box_opacity > 0:
                line_top = dot_cy + scaled_radius if self._dot_scale > 0 else dot_cy + dot_radius
                painter.setPen(QPen(QColor(COLORS['border']), 2))
                painter.drawLine(int(dot_cx), int(line_top), int(dot_cx), int(box_y))

            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode_DestinationOver)
            gradient = QLinearGradient(box_x, box_y, box_x + box_w, box_y)
            gradient.setColorAt(0, QColor(0, 0, 0, int(217 * self._box_opacity)))
            gradient.setColorAt(0.8, QColor(0, 0, 0, int(217 * self._box_opacity)))
            gradient.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(gradient)
            painter.setPen(Qt.NoPen)
            painter.drawRect(int(box_x), int(box_y), int(box_w), int(box_h))
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            if self._box_opacity > 0:
                painter.setPen(QPen(QColor(COLORS['border']), 2))
                painter.drawLine(int(box_x), int(box_y), int(box_x), int(box_y + box_h))
            painter.restore()

            if self._display_text and self._box_width > 20:
                painter.setPen(QColor(COLORS['text']))
                font = QFont("Cascadia Code", 10)
                font.setStyleHint(QFont.Monospace)
                font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
                painter.setFont(font)
                text_y = box_y + box_h / 2 + 4
                painter.drawText(int(box_x + 10), int(text_y), self._display_text)

        # 绘制图片区域（含堆叠层）
        if self._feedback_type == FeedbackType.COPY and self._has_image:
            base_x = dot_cx
            base_y = dot_cy + SIZES['box_height'] + 8
            if self._target_width <= 0:
                base_y = dot_cy + 8

            base_size = self._image_box_size
            vanish_ratio = self._get_image_vanish_ratio()

            if vanish_ratio > 0.002:
                # 先绘制堆叠层（底层，从后往前：layer2 -> layer1）
                stack_layers = self._image_count - 1  # 主图不算
                for layer_idx in range(min(stack_layers, 2) - 1, -1, -1):
                    self._draw_stack_layer(painter, base_x, base_y, base_size, layer_idx)

                # 再绘制主图（最上层，覆盖堆叠层的大部分，只露出右下角边缘）
                self._draw_main_image(painter, base_x, base_y, base_size, vanish_ratio)

        painter.end()

    def _draw_stack_layer(self, painter, base_x, base_y, base_size, layer_idx):
        """绘制一个堆叠背景层"""
        progress = self._stack_progress
        if progress < 0.01:
            return

        cfg = IMAGE_STACK
        offset_x = cfg['offset_x'] * (layer_idx + 1) * progress
        offset_y = cfg['offset_y'] * (layer_idx + 1) * progress
        rotate = cfg['rotate_per_layer'] * (layer_idx + 1) * progress

        if layer_idx == 0:
            opacity = cfg['opacity_layer1'] * progress
        else:
            opacity = cfg['opacity_layer2'] * progress

        sx = base_x + offset_x
        sy = base_y + offset_y

        painter.save()
        painter.setOpacity(opacity)

        # 旋转圆心：主图右下角（让堆叠层从右下角微露出来）
        transform = QTransform()
        pivot_x = base_x + base_size  # 主图右下角 X
        pivot_y = base_y + base_size  # 主图右下角 Y
        transform.translate(pivot_x, pivot_y)
        transform.rotate(rotate)
        transform.translate(-pivot_x, -pivot_y)
        painter.setTransform(transform)

        # 背景
        bg = cfg['bg_color']
        border = cfg['border_color']
        painter.setPen(QPen(QColor(*border), 1))
        painter.setBrush(QColor(bg[0], bg[1], bg[2], bg[3]))
        painter.drawRoundedRect(int(sx), int(sy), base_size, base_size,
                               self._image_corner_radius, self._image_corner_radius)

        # 根据 show_real_thumbnails 开关决定是否渲染真实缩略图
        show_real = cfg.get('show_real_thumbnails', False)
        img_idx = layer_idx + 1  # 0=主图, 1=第一层, 2=第二层
        if show_real and img_idx < len(self._images):
            img = self._images[img_idx]
            scaled = img.scaled(base_size, base_size,
                               Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)
            pixmap = QPixmap.fromImage(scaled)

            clip = QPainterPath()
            clip.addRoundedRect(float(sx), float(sy), float(base_size), float(base_size),
                               float(self._image_corner_radius), float(self._image_corner_radius))
            painter.setClipPath(clip)
            painter.setOpacity(opacity * 0.5)  # 堆叠层图片半透明
            painter.drawPixmap(int(sx), int(sy), pixmap)
        # else: 仅显示半透明圆角方块背景（已绘制）

        painter.restore()

    def _draw_main_image(self, painter, base_x, base_y, base_size, vanish_ratio):
        """绘制主图（含像素化/收缩动画）"""
        src_img = self._main_image
        if src_img is None:
            # 主图未加载时绘制占位框（简洁半透明圆角方块）
            painter.save()
            painter.setOpacity(IMAGE_STACK.get('placeholder_opacity', 0.5))
            painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
            painter.setBrush(QColor(30, 30, 35, 200))
            painter.drawRoundedRect(int(base_x), int(base_y), base_size, base_size,
                                   self._image_corner_radius, self._image_corner_radius)
            painter.restore()
            return

        if self._image_scramble_progress < 1.0:
            block = max(5, int(40 * ((1.0 - self._image_scramble_progress) ** 2)))
            small_w = max(1, base_size // block)
            small_h = max(1, base_size // block)
            pixelated = src_img.scaled(small_w, small_h,
                                       Qt.KeepAspectRatioByExpanding, Qt.FastTransformation
                                       ).scaled(base_size, base_size,
                                               Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)
            pixmap = QPixmap.fromImage(pixelated)
        else:
            final_img = src_img.scaled(base_size, base_size,
                                       Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)
            pixmap = QPixmap.fromImage(final_img)

        dot_cx = 5
        dot_cy = 5
        draw_size = max(2, int(base_size * vanish_ratio))
        draw_x = int(base_x + (dot_cx - base_x) * (1.0 - vanish_ratio))
        draw_y = int(base_y + (dot_cy - base_y) * (1.0 - vanish_ratio))
        draw_radius = max(2.0, self._image_corner_radius * vanish_ratio)

        painter.save()
        painter.setOpacity(vanish_ratio)

        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.setBrush(QColor(17, 17, 17, 220))
        painter.drawRoundedRect(int(draw_x), int(draw_y), draw_size, draw_size,
                               draw_radius, draw_radius)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(float(draw_x), float(draw_y),
                                float(draw_size), float(draw_size),
                                float(draw_radius), float(draw_radius))
        painter.setClipPath(clip_path)
        painter.drawPixmap(int(draw_x), int(draw_y), draw_size, draw_size, pixmap)
        painter.restore()

    def update_images(self, images, image_count: int):
        """异步图片到达后更新图片数据（追加模式）"""
        if not self._active:
            return

        new_images = []
        if images:
            for img in images[:IMAGE_STACK['max_display']]:
                if isinstance(img, QImage) and not img.isNull():
                    new_images.append(img.copy())

        if not new_images:
            return

        # 追加模式：保留已有图片，添加新图片
        for img in new_images:
            self._images.append(img)

        # 注意：不修改 _image_count — 它代表复制时的预估图片总数，用于决定堆叠层数量
        # 即使 Worker 只下载了部分图片，堆叠层仍应保持
        self._total_image_count = image_count
        self._has_image = True
        if self._images:
            self._main_image = self._images[0]

        # 不在此触发 STACK_APPEAR — 由 _advance_state 的 IMAGE_APPEAR 分支在正确时机触发
        # update_images 只更新图片数据，让状态机在动画序列走到 IMAGE_APPEAR 时再启动堆叠

        # 重新计算窗口尺寸
        content_w = int(self._target_width + 40) if self._target_width else 100
        image_w = self._image_box_size + 60
        max_w = max(content_w, image_w, 220)
        max_h = int(SIZES['box_height'] + SIZES['dot_radius'] * 2 + 30)
        max_h += self._image_box_size + 20
        self.setFixedSize(max(max_w, 500), max(max_h, 180))

        # 启动图片像素化动画
        self._image_scramble_progress = 0.0
        if not self._image_scramble_timer.isActive():
            self._image_scramble_timer.start()

        self.update()

    def stop(self):
        """停止所有动画"""
        self._active = False
        self._anim_timer.stop()
        self._scramble_timer.stop()
        self._image_scramble_timer.stop()
        self._stack_anim_timer.stop()
        self._state_timer.stop()
        self._holding_timer.stop()
        self.close()
