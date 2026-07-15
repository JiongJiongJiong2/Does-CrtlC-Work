"""Image-layout mode normalization and small pure layout helpers."""

from config import IMAGE_STACK


IMAGE_LAYOUT_FAN = 'fan'
IMAGE_LAYOUT_CASCADE = 'cascade'
IMAGE_LAYOUT_MODES = (IMAGE_LAYOUT_FAN, IMAGE_LAYOUT_CASCADE)


def normalize_image_layout(value) -> str:
    """Return a supported persisted image-layout value."""
    return value if value in IMAGE_LAYOUT_MODES else IMAGE_LAYOUT_FAN


def image_display_limit(mode: str) -> int:
    mode = normalize_image_layout(mode)
    key = 'cascade_max_display' if mode == IMAGE_LAYOUT_CASCADE else 'fan_max_display'
    return int(IMAGE_STACK[key])


def cascade_layer_progress(progress: float, index: int, count: int) -> float:
    """Stagger mirrored positions while preserving exact reversible endpoints."""
    progress = max(0.0, min(float(progress), 1.0))
    count = max(1, int(count))
    delay = float(IMAGE_STACK['cascade_stagger'])
    total_delay = delay * max(0, count - 1)
    travel = max(0.01, 1.0 - total_delay)
    local = max(0.0, min((progress - index * delay) / travel, 1.0))
    # Smoothstep keeps individual cards from snapping at their phase endpoints.
    return local * local * (3.0 - 2.0 * local)


def cascade_layer_offset(index: int, count: int,
                         horizontal_progress: float) -> float:
    """Move later cards from right of the front card to its left at right dock."""
    step = float(IMAGE_STACK['cascade_offset_x']) * max(0, int(index))
    local = cascade_layer_progress(horizontal_progress, index, count)
    return step * (1.0 - 2.0 * local)
