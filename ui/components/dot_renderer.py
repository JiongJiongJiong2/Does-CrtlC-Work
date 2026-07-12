"""
DotRenderer - 圆点渲染器
从 FeedbackWidget.paintEvent 中抽取的圆点绘制逻辑
"""

from PySide6.QtGui import QPainter, QColor, QRadialGradient
from PySide6.QtCore import Qt
from config import SIZES


class DotRenderer:
    """圆点渲染器 - 纯绘制逻辑，无状态"""

    @staticmethod
    def paint(painter: QPainter, cx: float, cy: float,
              scale: float, color: QColor) -> None:
        """绘制带光晕的圆点

        Args:
            painter: QPainter 实例
            cx: 圆心 X
            cy: 圆心 Y
            scale: 缩放比例 (0~1+)
            color: 圆点颜色
        """
        if scale <= 0:
            return

        radius = SIZES['dot_radius'] * scale

        # 光晕
        glow = QRadialGradient(cx, cy, radius * 2)
        glow.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 150))
        glow.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(cx - radius * 2, cy - radius * 2,
                           radius * 4, radius * 4)

        # 实心圆点
        painter.setBrush(color)
        painter.drawEllipse(cx - radius, cy - radius,
                           radius * 2, radius * 2)