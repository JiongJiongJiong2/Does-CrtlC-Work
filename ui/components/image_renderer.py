"""
ImageRenderer - 主图渲染器
从 FeedbackWidget._draw_main_image 抽取的图片绘制逻辑
包含：像素化渐显、收缩动画、占位框
"""

from PySide6.QtGui import QPainter, QColor, QPen, QPixmap, QPainterPath
from PySide6.QtCore import Qt
from config import IMAGE_STACK


class ImageRenderer:
    """主图渲染器 - 纯绘制逻辑，无状态"""

    IMAGE_BOX_SIZE = 120
    CORNER_RADIUS = 16

    @classmethod
    def paint(cls, painter: QPainter, base_x: float, base_y: float,
              main_image, scramble_progress: float, vanish_ratio: float,
              dot_cx: float, dot_cy: float) -> None:
        """绘制主图（含像素化/收缩动画）

        Args:
            painter: QPainter 实例
            base_x: 基准 X
            base_y: 基准 Y
            main_image: QImage 主图（可能为 None）
            scramble_progress: 像素化进度 0~1
            vanish_ratio: 收缩比例 0~1
            dot_cx: 圆点中心 X（收缩目标）
            dot_cy: 圆点中心 Y（收缩目标）
        """
        base_size = cls.IMAGE_BOX_SIZE

        if main_image is None:
            # 占位框
            painter.save()
            painter.setOpacity(IMAGE_STACK.get('placeholder_opacity', 0.5))
            painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
            painter.setBrush(QColor(30, 30, 35, 200))
            painter.drawRoundedRect(int(base_x), int(base_y), base_size, base_size,
                                   cls.CORNER_RADIUS, cls.CORNER_RADIUS)
            painter.restore()
            return

        # 像素化处理
        if scramble_progress < 1.0:
            block = max(5, int(40 * ((1.0 - scramble_progress) ** 2)))
            small_w = max(1, base_size // block)
            small_h = max(1, base_size // block)
            pixelated = main_image.scaled(small_w, small_h,
                                         Qt.KeepAspectRatioByExpanding, Qt.FastTransformation
                                         ).scaled(base_size, base_size,
                                                 Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)
            pixmap = QPixmap.fromImage(pixelated)
        else:
            final_img = main_image.scaled(base_size, base_size,
                                         Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)
            pixmap = QPixmap.fromImage(final_img)

        # 收缩动画参数
        draw_size = max(2, int(base_size * vanish_ratio))
        draw_x = int(base_x + (dot_cx - base_x) * (1.0 - vanish_ratio))
        draw_y = int(base_y + (dot_cy - base_y) * (1.0 - vanish_ratio))
        draw_radius = max(2.0, cls.CORNER_RADIUS * vanish_ratio)

        painter.save()
        painter.setOpacity(vanish_ratio)

        # 背景框
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.setBrush(QColor(17, 17, 17, 220))
        painter.drawRoundedRect(int(draw_x), int(draw_y), draw_size, draw_size,
                               draw_radius, draw_radius)

        # 裁剪并绘制图片
        clip_path = QPainterPath()
        clip_path.addRoundedRect(float(draw_x), float(draw_y),
                                float(draw_size), float(draw_size),
                                float(draw_radius), float(draw_radius))
        painter.setClipPath(clip_path)
        painter.drawPixmap(int(draw_x), int(draw_y), draw_size, draw_size, pixmap)
        painter.restore()