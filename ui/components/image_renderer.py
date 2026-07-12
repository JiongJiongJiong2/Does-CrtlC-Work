"""主图渲染器：预先缓存缩放和像素化帧，绘制阶段不再重复转换。"""

from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QColor, QPainterPath, QPen, QPixmap

from config import IMAGE_STACK


@dataclass
class ImageRenderCache:
    source: QImage
    final_pixmap: QPixmap
    reveal_frames: List[QPixmap]

    def pixmap_for_progress(self, progress: float) -> QPixmap:
        index = min(len(self.reveal_frames) - 1,
                    max(0, int(progress * (len(self.reveal_frames) - 1))))
        return self.reveal_frames[index]


class ImageRenderer:
    IMAGE_BOX_SIZE = 120
    CORNER_RADIUS = 16
    REVEAL_FRAME_COUNT = 25

    @classmethod
    def build_cache(cls, image: Optional[QImage]) -> Optional[ImageRenderCache]:
        if image is None or image.isNull():
            return None

        size = cls.IMAGE_BOX_SIZE
        final_image = image.scaled(size, size, Qt.KeepAspectRatioByExpanding,
                                   Qt.FastTransformation)
        final_pixmap = QPixmap.fromImage(final_image)
        reveal_frames = []
        for index in range(cls.REVEAL_FRAME_COUNT):
            progress = index / (cls.REVEAL_FRAME_COUNT - 1)
            if progress >= 1.0:
                reveal_frames.append(final_pixmap)
                continue
            block = max(5, int(40 * ((1.0 - progress) ** 2)))
            small_size = max(1, size // block)
            pixelated = image.scaled(small_size, small_size,
                                     Qt.KeepAspectRatioByExpanding,
                                     Qt.FastTransformation).scaled(
                                         size, size,
                                         Qt.KeepAspectRatioByExpanding,
                                         Qt.FastTransformation)
            reveal_frames.append(QPixmap.fromImage(pixelated))
        return ImageRenderCache(image, final_pixmap, reveal_frames)

    @classmethod
    def paint(cls, painter: QPainter, base_x: float, base_y: float,
              main_image: Optional[QImage], scramble_progress: float,
              vanish_ratio: float, dot_cx: float, dot_cy: float,
              cache: Optional[ImageRenderCache] = None) -> None:
        base_size = cls.IMAGE_BOX_SIZE
        if main_image is None or main_image.isNull():
            painter.save()
            painter.setOpacity(IMAGE_STACK.get('placeholder_opacity', 0.5))
            painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
            painter.setBrush(QColor(30, 30, 35, 200))
            painter.drawRoundedRect(int(base_x), int(base_y), base_size, base_size,
                                    cls.CORNER_RADIUS, cls.CORNER_RADIUS)
            painter.restore()
            return

        if cache is None or cache.source is not main_image:
            cache = cls.build_cache(main_image)
        pixmap = cache.pixmap_for_progress(scramble_progress)
        draw_size = max(2, int(base_size * vanish_ratio))
        draw_x = int(base_x + (dot_cx - base_x) * (1.0 - vanish_ratio))
        draw_y = int(base_y + (dot_cy - base_y) * (1.0 - vanish_ratio))
        draw_radius = max(2.0, cls.CORNER_RADIUS * vanish_ratio)

        painter.save()
        painter.setOpacity(vanish_ratio)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.setBrush(QColor(17, 17, 17, 220))
        painter.drawRoundedRect(draw_x, draw_y, draw_size, draw_size,
                                draw_radius, draw_radius)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(float(draw_x), float(draw_y), float(draw_size),
                                 float(draw_size), float(draw_radius),
                                 float(draw_radius))
        painter.setClipPath(clip_path)
        painter.drawPixmap(draw_x, draw_y, draw_size, draw_size, pixmap)
        painter.restore()
