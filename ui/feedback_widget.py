"""
FeedbackWidget - 自恢复多态动画窗口容器
驱动"亮灯-舒展-文字揭现-横向坍塌-指回亮点"全生命周期动画

动画序列 (copy 成功):
1. 圆点出现 (Spring 弹出)
2. 黑色透明框从左向右展开
3. ScrambleText 文字解码揭示
4. 等待展示时间
5. 框从右向左收缩成细线
6. 细线向上收缩回圆点
7. 圆点消失

动画序列 (error/paste):
1. 圆点出现
2. 等待短暂时间
3. 圆点消失
"""

import random
import time
from enum import Enum, auto
from PySide6.QtCore import QTimer, Qt, QEasingCurve, Signal
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QRadialGradient, QPen, QFont, QFontMetrics
from PySide6.QtWidgets import QWidget

from config import COLORS, SIZES, ANIMATION_DURATION, BLOCK_CHARS, SCRAMBLE_CHARS


class FeedbackType(Enum):
    COPY = auto()
    PASTE = auto()
    ERROR = auto()


class AnimationState(Enum):
    IDLE = auto()
    DOT_APPEAR = auto()
    BOX_EXPAND = auto()
    TEXT_REVEAL = auto()
    VIEWING = auto()
    BOX_SHRINK = auto()
    LINE_SHRINK = auto()
    DOT_DISAPPEAR = auto()
    COMPLETE = auto()


class FeedbackWidget(QWidget):
    """反馈动画窗口 - 跟随鼠标的动画提示"""
    
    animation_complete = Signal()
    
    def __init__(self, feedback_type: FeedbackType, text: str = "", parent=None):
        super().__init__(parent)
        
        self._feedback_type = feedback_type
        self._text = text
        self._state = AnimationState.IDLE
        self._active = True
        
        # 动画参数
        self._dot_scale = 0.0
        self._box_width = 0.0
        self._box_height = SIZES['box_height']
        self._box_opacity = 0.0
        
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
        
        # 设置窗口属性
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        # 计算窗口尺寸 - 圆点在上，黑框在下
        max_w = int(self._target_width + 40) if self._target_width else 100
        max_h = int(SIZES['box_height'] + SIZES['dot_radius'] * 2 + 30)  # 圆点高度 + 框高度 + 间距
        self.setFixedSize(max(max_w, 500), max(max_h, 100))
        
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
        self.show()
        
    def _start_property_animation(self, prop: str, start: float, end: float,
                                   duration: int, easing: QEasingCurve = None):
        """启动属性动画"""
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
        """动画帧更新"""
        now = time.time() * 1000
        elapsed = now - self._anim_start_time
        raw_progress = min(elapsed / self._anim_duration, 1.0) if self._anim_duration > 0 else 1.0
        eased_progress = self._anim_easing.valueForProgress(raw_progress)
        current_value = self._anim_start_value + (self._anim_end_value - self._anim_start_value) * eased_progress
        setattr(self, f'_{self._anim_property}', current_value)
        
        # 确保 box_height 在收缩时实时更新
        if self._anim_property == 'box_height':
            self._box_height = current_value
            # LINE_SHRINK 阶段同步衰减透明度
            if self._state == AnimationState.LINE_SHRINK:
                height_ratio = current_value / SIZES['box_height'] if SIZES['box_height'] > 0 else 0
                self._box_opacity = height_ratio
            
        self.update()
        
        if raw_progress >= 1.0:
            setattr(self, f'_{self._anim_property}', self._anim_end_value)
            self._anim_timer.stop()
            self._on_animation_finished()
            
    def _on_animation_finished(self):
        """当前属性动画完成"""
        if not self._active:
            return
            
        if self._state == AnimationState.DOT_APPEAR:
            if self._feedback_type == FeedbackType.COPY:
                self._state = AnimationState.BOX_EXPAND
                self._box_opacity = 1.0
                self._start_property_animation('box_width', 0.0, self._target_width,
                                                ANIMATION_DURATION['box_expand'],
                                                QEasingCurve(QEasingCurve.OutQuad))
            else:
                self._state = AnimationState.VIEWING
                self._state_timer.start(ANIMATION_DURATION['error_display'])
                
        elif self._state == AnimationState.BOX_EXPAND:
            # 框展开完成，开始文字揭示
            self._start_scramble_text()
            
        elif self._state == AnimationState.BOX_SHRINK:
            self._state = AnimationState.LINE_SHRINK
            # 同时动画高度和透明度
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
            
    def _advance_state(self):
        """推进动画状态"""
        if not self._active:
            return
            
        if self._state == AnimationState.TEXT_REVEAL:
            # 文字揭示完成，进入收缩阶段
            self._scramble_timer.stop()
            self._display_text = self._text
            self._state = AnimationState.BOX_SHRINK
            self._start_property_animation('box_width', self._target_width, 2.0,
                                            ANIMATION_DURATION['box_shrink'],
                                            QEasingCurve(QEasingCurve.InQuad))
            
        elif self._state == AnimationState.VIEWING:
            # error/paste 展示完成
            self._state = AnimationState.DOT_DISAPPEAR
            self._start_property_animation('dot_scale', 1.0, 0.0,
                                            ANIMATION_DURATION['dot_disappear'],
                                            QEasingCurve(QEasingCurve.InBack))
            
    def _start_scramble_text(self):
        """开始文字解码动画"""
        self._state = AnimationState.TEXT_REVEAL
        self._scramble_start_time = time.time() * 1000
        self._scramble_timer.start()
        # 设置揭示完成后的定时器
        self._state_timer.start(ANIMATION_DURATION['text_scramble'] + ANIMATION_DURATION['view_time'])
        
    def _scramble_tick(self):
        """文字解码帧更新"""
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
            
        self.update()
        
    def move_to_position(self, x: float, y: float):
        """移动窗口到指定位置（相对于鼠标）"""
        # 圆点在鼠标位置偏移处
        dot_x = x + SIZES['mouse_offset_x']
        dot_y = y + SIZES['mouse_offset_y']
        # 窗口位置（圆点在窗口左上角偏移处）
        self.move(int(dot_x - 5), int(dot_y - 5))
        
    def paintEvent(self, event):
        """绘制动画"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 基准位置（圆点中心）
        dot_cx = 5
        dot_cy = 5
        dot_radius = SIZES['dot_radius']
        
        # 绘制圆点（带缩放）
        if self._dot_scale > 0:
            scaled_radius = dot_radius * self._dot_scale
            # 发光效果
            glow = QRadialGradient(dot_cx, dot_cy, scaled_radius * 2)
            glow.setColorAt(0, QColor(self._dot_color.red(), self._dot_color.green(), 
                                       self._dot_color.blue(), 150))
            glow.setColorAt(1, QColor(self._dot_color.red(), self._dot_color.green(),
                                       self._dot_color.blue(), 0))
            painter.setBrush(glow)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(dot_cx - scaled_radius * 2, dot_cy - scaled_radius * 2,
                               scaled_radius * 4, scaled_radius * 4)
            
            # 实心圆点
            painter.setBrush(self._dot_color)
            painter.drawEllipse(dot_cx - scaled_radius, dot_cy - scaled_radius,
                               scaled_radius * 2, scaled_radius * 2)
        
        # 绘制内容框（仅 COPY 类型）
        if self._feedback_type == FeedbackType.COPY and self._box_width > 0:
            # 黑框左边界对齐圆点中心（从圆点正下方开始）
            box_x = dot_cx  # 左边界对齐圆点中心
            # 框顶部在圆点底部下方留2px间距
            gap = 0

            #box_y = dot_cy + dot_radius * self._dot_scale + gap
            box_y = dot_cy

            box_w = self._box_width
            box_h = self._box_height
            
            # 绘制圆点到黑框的连接竖线（黄色）
            if self._box_opacity > 0:
                line_top = dot_cy + scaled_radius if self._dot_scale > 0 else dot_cy + dot_radius
                line_bottom = box_y
                
                #line_top = dot_cy
                #line_bottom = box_y + box_h
                
                painter.setPen(QPen(QColor(COLORS['border']), 2))
                painter.drawLine(int(dot_cx), int(line_top), int(dot_cx), int(line_bottom))
            
            # 背景（带右边界渐变消失效果）
            painter.save()

            #
            painter.setCompositionMode(QPainter.CompositionMode_DestinationOver)
            
            # 创建渐变遮罩
            gradient = QLinearGradient(box_x, box_y, box_x + box_w, box_y)
            gradient.setColorAt(0, QColor(0, 0, 0, int(217 * self._box_opacity)))
            gradient.setColorAt(0.8, QColor(0, 0, 0, int(217 * self._box_opacity)))
            gradient.setColorAt(1, QColor(0, 0, 0, 0))
            
            painter.setBrush(gradient)
            painter.setPen(Qt.NoPen)
            painter.drawRect(int(box_x), int(box_y), int(box_w), int(box_h))
            
            #
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # 左边界黄色线条
            if self._box_opacity > 0:
                painter.setPen(QPen(QColor(COLORS['border']), 2))
                painter.drawLine(int(box_x), int(box_y), int(box_x), int(box_y + box_h))
            
            painter.restore()
            
            # 绘制文字
            if self._display_text and self._box_width > 20:
                painter.setPen(QColor(COLORS['text']))
                font = QFont("Cascadia Code", 10)
                font.setStyleHint(QFont.Monospace)
                font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
                painter.setFont(font)
                
                text_y = box_y + box_h / 2 + 4  # 垂直居中偏移
                painter.drawText(int(box_x + 10), int(text_y), self._display_text)
        
        painter.end()
        
    def stop(self):
        """停止所有动画"""
        self._active = False
        self._anim_timer.stop()
        self._scramble_timer.stop()
        self._state_timer.stop()
        self.close()