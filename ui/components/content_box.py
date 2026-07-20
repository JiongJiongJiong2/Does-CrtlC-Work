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
              final_layout: QStaticText = None, direction: int = 1,
              mirror_progress: float = None,
              viewport_text: bool = False,
              text_translation_x: float = 0.0,
              display_lines=None, line_layouts=None,
              expanded_line_step: float = None) -> None:
        if box_width <= 0:
            return
        if mirror_progress is None:
            mirror_progress = 1.0 if direction < 0 else 0.0
        mirror_progress = max(0.0, min(float(mirror_progress), 1.0))
        box_x = dot_cx - box_width * mirror_progress
        box_y = dot_cy
        dot_radius = SIZES['dot_radius']
        if box_opacity > 0:
            line_top = dot_cy + (dot_radius * dot_scale) if dot_scale > 0 else dot_cy + dot_radius
            painter.setPen(QPen(QColor(COLORS['border']), 2))
            painter.drawLine(int(dot_cx), int(line_top), int(dot_cx), int(box_y))

        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode_DestinationOver)
        # Keep a stable left-to-right gradient vector. Reversing its endpoints
        # continuously would collapse it to zero length at 50%, causing a
        # visible flash. Instead, interpolate only the two fading edge alphas.
        gradient = QLinearGradient(box_x, box_y, box_x + box_width, box_y)
        red, green, blue, alpha = COLORS['box_bg']
        edge_alpha = int(alpha * box_opacity)
        gradient.setColorAt(
            0, QColor(red, green, blue,
                      int(edge_alpha * (1.0 - mirror_progress))))
        gradient.setColorAt(0.2, QColor(red, green, blue, edge_alpha))
        gradient.setColorAt(0.8, QColor(red, green, blue,
                                        int(alpha * box_opacity)))
        gradient.setColorAt(
            1, QColor(red, green, blue,
                      int(edge_alpha * mirror_progress)))
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRect(int(box_x), int(box_y), int(box_width), int(box_height))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        if box_opacity > 0:
            painter.setPen(QPen(QColor(COLORS['border']), 2))
            # In mirrored mode the box grows left, but the vertical yellow
            # anchor must stay under the dot on the right.
            painter.drawLine(int(dot_cx), int(box_y),
                             int(dot_cx), int(box_y + box_height))
        painter.restore()

        lines = display_lines if display_lines is not None else [display_text]
        if any(lines) and box_width > 20:
            painter.setPen(QColor(COLORS['text']))
            painter.setFont(text_style.font)
            normal_text_x = box_x + 10
            if viewport_text or mirror_progress <= 0.0:
                text_x = normal_text_x
            else:
                text_width = (final_layout.size().width()
                              if final_layout is not None else
                              text_style.metrics.horizontalAdvance(display_text))
                mirrored_text_x = max(
                    box_x + 8, box_x + box_width - 10 - text_width)
                text_x = normal_text_x + (
                    mirrored_text_x - normal_text_x) * mirror_progress
            painter.save()
            painter.setClipRect(int(box_x + 8), int(box_y),
                                max(0, int(box_width - 12)), int(box_height))
            line_step = (SIZES['box_height'] if expanded_line_step is None
                         else max(float(expanded_line_step),
                                  float(text_style.metrics.height())))
            first_line_top = box_y + (
                SIZES['box_height'] - text_style.metrics.height()) / 2
            for index, line in enumerate(lines):
                if not line:
                    continue
                text_top = first_line_top + index * line_step
                layout = (line_layouts[index] if line_layouts and
                          index < len(line_layouts) else
                          (final_layout if index == 0 else None))
                # Expanded text is one viewport: horizontal navigation must
                # translate every visible row together, not just the first.
                row_x = text_x + text_translation_x
                if layout is not None:
                    painter.drawStaticText(QPointF(row_x, text_top), layout)
                else:
                    baseline = text_top + text_style.metrics.ascent()
                    painter.drawText(QPointF(row_x, baseline), line)
            painter.restore()
