"""
ContentBox - 文字内容框渲染器
从 FeedbackWidget.paintEvent 中抽取的内容框绘制逻辑
包含：黑底渐变框、左侧边框线、文字绘制
"""

from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QFont
from PySide6.QtCore import Qt
from config import COLORS, SIZES


class ContentBox:
    """内容框渲染器 - 纯绘制逻辑，无状态"""

    @staticmethod
    def paint(painter: QPainter, dot_cx: float, dot_cy: float,
              box_width: float, box_height: float, box_opacity: float,
              display_text: str, dot_scale: float) -> None:
        """绘制内容框

        Args:
            painter: QPainter 实例
            dot_cx: 圆点中心 X
            dot_cy: 圆点中心 Y
            box_width: 框宽度
            box_height: 框高度
            box_opacity: 框透明度
            display_text: 显示文字（可能含 scramble 字符）
            dot_scale: 圆点缩放（用于计算边线起始位置）
        """
        if box_width <= 0:
            return

        box_x = dot_cx
        box_y = dot_cy
        box_w = box_width
        box_h = box_height
        dot_radius = SIZES['dot_radius']

        # 左侧边线（圆点到框）
        if box_opacity > 0:
            line_top = dot_cy + (dot_radius * dot_scale) if dot_scale > 0 else dot_cy + dot_radius
            painter.setPen(QPen(QColor(COLORS['border']), 2))
            painter.drawLine(int(dot_cx), int(line_top), int(dot_cx), int(box_y))

        # 黑底渐变框
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode_DestinationOver)
        gradient = QLinearGradient(box_x, box_y, box_x + box_w, box_y)
        gradient.setColorAt(0, QColor(0, 0, 0, int(217 * box_opacity)))
        gradient.setColorAt(0.8, QColor(0, 0, 0, int(217 * box_opacity)))
        gradient.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRect(int(box_x), int(box_y), int(box_w), int(box_h))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # 左侧边框线
        if box_opacity > 0:
            painter.setPen(QPen(QColor(COLORS['border']), 2))
            painter.drawLine(int(box_x), int(box_y), int(box_x), int(box_y + box_h))
        painter.restore()

        # 文字
        if display_text and box_width > 20:
            painter.setPen(QColor(COLORS['text']))
            font = QFont("Cascadia Code", 10)
            font.setStyleHint(QFont.Monospace)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
            painter.setFont(font)
            text_y = box_y + box_h / 2 + 4
            painter.drawText(int(box_x + 10), int(text_y), display_text)