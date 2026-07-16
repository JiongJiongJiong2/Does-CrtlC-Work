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
    """Return the first cascade gap for callers that need a scalar value."""
    return cascade_layer_distance(1, target_width, count)


def cascade_layer_distance(index: int, target_width: float,
                           count: int) -> float:
    """Return a progressively wider, content-box-capped card offset."""
    index = max(0, int(index))
    layers = max(1, int(count) - 1)
    if index <= 0:
        return 0.0
    index = min(index, layers)
    default_step = float(IMAGE_STACK['cascade_offset_x'])
    # Later cards open further than earlier ones: 1.00, 1.18, 1.36 …
    weights = [1.0 + 0.18 * layer for layer in range(layers)]
    desired_span = default_step * sum(weights)
    target_width = float(target_width or 0.0)
    # The front thumbnail is 120 DIP wide. Do not let the cascade tail make
    # the whole image group wider than an existing text content box.
    max_span = (max(0.0, target_width - 120.0)
                if target_width > 0.0 else desired_span)
    span = min(desired_span, max_span)
    return span * sum(weights[:index]) / sum(weights)


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
    step = cascade_layer_distance(index, target_width, count)
    local = cascade_layer_progress(horizontal_progress, index, count)
    expansion_progress = max(0.0, float(expansion_progress))
    return step * (1.0 - 2.0 * local) * expansion_progress
