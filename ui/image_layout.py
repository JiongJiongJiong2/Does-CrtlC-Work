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


def cascade_step(target_width: float, count: int) -> float:
    """Return a slightly open card step without outrunning a wide text box."""
    layers = max(1, int(count) - 1)
    default_step = float(IMAGE_STACK['cascade_offset_x'])
    target_width = float(target_width or 0.0)
    if target_width <= 0.0:
        return default_step
    available_step = (target_width - 120.0) / layers
    # A text box shorter than one image cannot be a useful hard cap. Preserve
    # a visible minimum overlap instead of shrinking the image itself.
    if available_step < 20.0:
        return 20.0
    return min(default_step, available_step)


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
                         horizontal_progress: float,
                         target_width: float = 0.0,
                         expansion_progress: float = 1.0) -> float:
    """Move later cards from right of the front card to its left at right dock."""
    step = cascade_step(target_width, count) * max(0, int(index))
    local = cascade_layer_progress(horizontal_progress, index, count)
    expansion_progress = max(0.0, float(expansion_progress))
    return step * (1.0 - 2.0 * local) * expansion_progress
