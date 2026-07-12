"""
FeedbackLayout - 布局计算器
从 FeedbackWidget 中抽取的坐标计算逻辑，纯函数无 Qt 依赖
"""

from config import SIZES
from ui.components.image_renderer import ImageRenderer


# 圆点在窗口内的固定坐标
DOT_CX = 5
DOT_CY = 5


def window_size(target_width: float, has_image: bool) -> tuple:
    """计算窗口尺寸

    Returns:
        (width, height) 元组
    """
    content_w = int(target_width + 40) if target_width else 100
    image_w = ImageRenderer.IMAGE_BOX_SIZE + 60 if has_image else 0
    max_w = max(content_w, image_w, 220)

    max_h = int(SIZES['box_height'] + SIZES['dot_radius'] * 2 + 30)
    if has_image:
        max_h += ImageRenderer.IMAGE_BOX_SIZE + 20

    return (max(max_w, 500), max(max_h, 180))


def image_base_pos(dot_cx: float, dot_cy: float, target_width: float) -> tuple:
    """计算图片区域基准位置

    Returns:
        (base_x, base_y) 元组
    """
    base_x = dot_cx
    base_y = dot_cy + SIZES['box_height'] + 8
    if target_width <= 0:
        base_y = dot_cy + 8
    return (base_x, base_y)


def mouse_to_window(x: float, y: float) -> tuple:
    """将鼠标坐标转换为窗口位置

    Returns:
        (win_x, win_y) 窗口左上角坐标
    """
    dot_x = x + SIZES['mouse_offset_x']
    dot_y = y + SIZES['mouse_offset_y']
    return (int(dot_x - DOT_CX), int(dot_y - DOT_CY))