"""
StackLayer - 堆叠层渲染器
从 FeedbackWidget._draw_stack_layer 抽取的堆叠层绘制逻辑
"""

from PySide6.QtGui import QPainter, QColor, QPen, QPixmap, QPainterPath, QTransform
from PySide6.QtCore import Qt
from config import IMAGE_STACK


class StackLayer:
    """堆叠层渲染器 - 纯绘制逻辑，无状态"""

    CORNER_RADIUS = 16

    @staticmethod
    def paint(painter: QPainter, base_x: float, base_y: float,
              base_size: int, layer_idx: int, progress: float,
              images: list, thumbnail: QPixmap = None, direction: int = 1,
              vertical_direction: int = 1) -> None:
        """绘制一个堆叠背景层

        Args:
            painter: QPainter 实例
            base_x: 基准 X
            base_y: 基准 Y
            base_size: 图片框尺寸
            layer_idx: 层索引（0=第一层，1=第二层）
            progress: 展开进度 0~1
            images: 图片列表（用于真实缩略图）
        """
        if progress < 0.01:
            return

        cfg = IMAGE_STACK
        offset_x = cfg['offset_x'] * direction * (layer_idx + 1) * progress
        offset_y = (cfg['offset_y'] * vertical_direction *
                    (layer_idx + 1) * progress)
        rotate = cfg['rotate_per_layer'] * direction * (layer_idx + 1) * progress

        if layer_idx == 0:
            opacity = cfg['opacity_layer1'] * progress
        else:
            opacity = cfg['opacity_layer2'] * progress

        sx = base_x + offset_x
        sy = base_y + offset_y
        corner_radius = StackLayer.CORNER_RADIUS

        painter.save()
        painter.setOpacity(opacity)

        # Mirror the stack direction and rotate around its outer lower corner.
        transform = QTransform()
        pivot_x = base_x + (base_size if direction >= 0 else 0)
        pivot_y = base_y if vertical_direction < 0 else base_y + base_size
        transform.translate(pivot_x, pivot_y)
        transform.rotate(rotate)
        transform.translate(-pivot_x, -pivot_y)
        # Preserve FeedbackWidget's outer cursor-size scale. Replacing the
        # transform here would leave stack layers at 1x while every other
        # component is enlarged.
        painter.setTransform(transform, combine=True)

        # 背景
        bg = cfg['bg_color']
        border = cfg['border_color']
        painter.setPen(QPen(QColor(*border), 1))
        painter.setBrush(QColor(bg[0], bg[1], bg[2], bg[3]))
        painter.drawRoundedRect(int(sx), int(sy), base_size, base_size,
                               corner_radius, corner_radius)

        # 真实缩略图（可选）
        show_real = cfg.get('show_real_thumbnails', False)
        img_idx = layer_idx + 1
        if show_real and img_idx < len(images):
            pixmap = thumbnail
            if pixmap is None:
                img = images[img_idx]
                scaled = img.scaled(base_size, base_size,
                                   Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)
                pixmap = QPixmap.fromImage(scaled)

            clip = QPainterPath()
            clip.addRoundedRect(float(sx), float(sy), float(base_size), float(base_size),
                               float(corner_radius), float(corner_radius))
            painter.setClipPath(clip)
            painter.setOpacity(opacity * 0.5)
            painter.drawPixmap(int(sx), int(sy), pixmap)

        painter.restore()
