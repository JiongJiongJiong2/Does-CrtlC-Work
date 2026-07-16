"""
FeedbackLayout - 布局计算器
从 FeedbackWidget 中抽取的坐标计算逻辑，纯函数无 Qt 依赖
"""

import math

from config import DOCK_TRANSITION, IMAGE_STACK, SIZES
from ui.components.image_renderer import ImageRenderer
from ui.image_layout import (IMAGE_LAYOUT_CASCADE, cascade_layer_distance,
                             normalize_image_layout)


# 圆点在窗口内的固定坐标
DOT_CX = 5
DOT_CY = 5
EDGE_DOCK_MARGIN = DOCK_TRANSITION['enter_margin']


def edge_dock_required(visible_edge: float, boundary: float,
                       currently_docked: bool,
                       ui_scale: float = 1.0) -> bool:
    """Return a stable dock target with an enter/exit hysteresis band."""
    margin_key = 'exit_margin' if currently_docked else 'enter_margin'
    margin = DOCK_TRANSITION[margin_key] * ui_scale
    return visible_edge > boundary - margin


def window_size(target_width: float, has_image: bool, ui_scale: float = 1.0) -> tuple:
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

    base_width = max(max_w, 500)
    base_height = max(max_h, 180)
    return (math.ceil(base_width * ui_scale), math.ceil(base_height * ui_scale))


def image_base_pos(dot_cx: float, dot_cy: float, target_width: float,
                   direction: int = 1, image_above: bool = False,
                   horizontal_progress: float = None,
                   vertical_progress: float = None) -> tuple:
    """计算图片区域基准位置

    Returns:
        (base_x, base_y) 元组
    """
    if horizontal_progress is None:
        horizontal_progress = 1.0 if direction < 0 else 0.0
    if vertical_progress is None:
        vertical_progress = 1.0 if image_above else 0.0
    horizontal_progress = max(0.0, min(float(horizontal_progress), 1.0))
    vertical_progress = max(0.0, min(float(vertical_progress), 1.0))

    base_x = dot_cx - ImageRenderer.IMAGE_BOX_SIZE * horizontal_progress
    below_offset = SIZES['box_height'] + 8 if target_width > 0 else 8
    above_offset = -ImageRenderer.IMAGE_BOX_SIZE - 8
    base_y = dot_cy + below_offset + (
        above_offset - below_offset) * vertical_progress
    return (base_x, base_y)


def bottom_dock_dot_y(image_count: int = 0,
                      image_layout_mode: str = 'fan') -> float:
    """Keep an upward-opening image stack inside the feedback canvas."""
    mode = normalize_image_layout(image_layout_mode)
    stack_layers = min(max(image_count - 1, 0), 2)
    stack_height = (0 if mode == IMAGE_LAYOUT_CASCADE else
                    abs(IMAGE_STACK['offset_y']) * stack_layers)
    return DOT_CY + ImageRenderer.IMAGE_BOX_SIZE + stack_height + 8


def mouse_to_window(x: float, y: float, ui_scale: float = 1.0,
                    offset_x: float = None, offset_y: float = None,
                    dot_cy: float = DOT_CY) -> tuple:
    """将鼠标坐标转换为窗口位置

    Returns:
        (win_x, win_y) 窗口左上角坐标
    """
    dot_x = x + (SIZES['mouse_offset_x'] if offset_x is None else offset_x)
    dot_y = y + (SIZES['mouse_offset_y'] if offset_y is None else offset_y)
    return (int(dot_x - DOT_CX * ui_scale),
            int(dot_y - dot_cy * ui_scale))


def clamp_window_position(x: int, y: int, width: int, height: int,
                          available: tuple) -> tuple:
    """Keep the whole transparent feedback canvas inside one screen."""
    left, top, available_width, available_height = available
    max_x = left + max(0, available_width - width)
    max_y = top + max(0, available_height - height)
    return (max(left, min(x, max_x)), max(top, min(y, max_y)))


def visible_content_bounds(target_width: float, has_image: bool,
                           image_count: int = 0, dot_cy: float = DOT_CY,
                           image_above: bool = False,
                           image_layout_mode: str = 'fan') -> tuple[float, float]:
    """Return the normal-direction visible right/bottom edges in logical px.

    The QWidget canvas deliberately has generous transparent space for
    animation. Screen-edge docking must use these visible bounds instead of
    the full canvas, otherwise a short text box stops 100+ px too early.
    """
    dot_extent = SIZES['dot_radius'] * 2
    right = DOT_CX + dot_extent
    bottom = dot_cy + dot_extent
    if target_width > 0:
        right = max(right, DOT_CX + target_width)
        bottom = max(bottom, dot_cy + SIZES['box_height'])
    if has_image:
        mode = normalize_image_layout(image_layout_mode)
        image_x, image_y = image_base_pos(
            DOT_CX, dot_cy, target_width, image_above=image_above)
        if mode == IMAGE_LAYOUT_CASCADE:
            stack_layers = min(max(image_count - 1, 0), 3)
            stack_x = cascade_layer_distance(
                stack_layers, target_width, image_count)
            stack_y = 0
        else:
            stack_layers = min(max(image_count - 1, 0), 2)
            stack_x = abs(IMAGE_STACK['offset_x']) * stack_layers
            stack_y = abs(IMAGE_STACK['offset_y']) * stack_layers
        # A small allowance covers the rotated stack corners.
        right = max(right, image_x + ImageRenderer.IMAGE_BOX_SIZE + stack_x + 12)
        image_bottom = image_y + ImageRenderer.IMAGE_BOX_SIZE
        if not image_above:
            image_bottom += stack_y + 12
        bottom = max(bottom, image_bottom)
    return right, bottom


def dock_feedback_position(mouse_x: float, mouse_y: float, canvas_width: int,
                           ui_scale: float, offset_x: float, offset_y: float,
                           visible_right: float, visible_bottom: float,
                           available: tuple, dot_cy: float = DOT_CY) -> tuple[int, int, bool]:
    """Position feedback by its visible content and select right-edge mirror.

    The returned window may extend below the available geometry; only its
    transparent tail does so. The painted content remains safely visible and
    continues to follow the mouse horizontally along the bottom edge.
    """
    left, top, available_width, available_height = available
    right_edge = left + available_width
    bottom_edge = top + available_height
    margin = EDGE_DOCK_MARGIN * ui_scale
    normal_x, normal_y = mouse_to_window(
        mouse_x, mouse_y, ui_scale, offset_x, offset_y, dot_cy)

    should_mirror_right = normal_x + visible_right * ui_scale > right_edge - margin
    if should_mirror_right:
        window_x = int(right_edge - margin - canvas_width)
    else:
        window_x = normal_x

    if normal_y + visible_bottom * ui_scale > bottom_edge - margin:
        window_y = int(bottom_edge - margin - visible_bottom * ui_scale)
    else:
        window_y = normal_y

    # The cursor cannot normally travel outside the virtual desktop, but keep
    # the visible feedback usable at a top/left edge or on a small monitor.
    window_x = max(int(left - DOT_CX * ui_scale), window_x)
    window_y = max(int(top - DOT_CY * ui_scale), window_y)
    return window_x, window_y, should_mirror_right
