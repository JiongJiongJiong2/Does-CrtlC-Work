"""内容框绘制器；文本样式和最终布局由 FeedbackWidget 预先缓存。"""

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QStaticText

from config import COLORS, SIZES
from ui.text_style import TextStyle


class ContentBox:
    @staticmethod
    def paint(painter: QPainter, dot_cx: float, dot_cy: float,
              box_width: float, box_height: float, box_opacity: float,
              display_text: str, dot_scale: float, text_style: TextStyle,
              final_layout: QStaticText = None) -> None:
        if box_width <= 0:
            return
        box_x, box_y = dot_cx, dot_cy
        dot_radius = SIZES['dot_radius']
        if box_opacity > 0:
            line_top = dot_cy + (dot_radius * dot_scale) if dot_scale > 0 else dot_cy + dot_radius
            painter.setPen(QPen(QColor(COLORS['border']), 2))
            painter.drawLine(int(dot_cx), int(line_top), int(dot_cx), int(box_y))

        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode_DestinationOver)
        gradient = QLinearGradient(box_x, box_y, box_x + box_width, box_y)
        gradient.setColorAt(0, QColor(0, 0, 0, int(217 * box_opacity)))
        gradient.setColorAt(0.8, QColor(0, 0, 0, int(217 * box_opacity)))
        gradient.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRect(int(box_x), int(box_y), int(box_width), int(box_height))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        if box_opacity > 0:
            painter.setPen(QPen(QColor(COLORS['border']), 2))
            painter.drawLine(int(box_x), int(box_y), int(box_x), int(box_y + box_height))
        painter.restore()

        if display_text and box_width > 20:
            painter.setPen(QColor(COLORS['text']))
            painter.setFont(text_style.font)
            text_x = box_x + 10
            text_top = box_y + (box_height - text_style.metrics.height()) / 2
            painter.save()
            painter.setClipRect(int(box_x + 8), int(box_y),
                                max(0, int(box_width - 12)), int(box_height))
            if final_layout is not None:
                painter.drawStaticText(QPointF(text_x, text_top), final_layout)
            else:
                baseline = text_top + text_style.metrics.ascent()
                painter.drawText(QPointF(text_x, baseline), display_text)
            painter.restore()
