"""Low-allocation navigation state for a copied-text preview."""

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple


@dataclass
class TextViewport:
    """Keep one text snapshot and address lines by offsets, not copied lines."""

    text: str
    visible_chars: int
    line_index: int = 0
    column: int = 0
    _line_ranges: List[Tuple[int, int]] = field(default_factory=list,
                                                  init=False,
                                                  repr=False)
    _max_column_override: Optional[int] = field(default=None, init=False,
                                                 repr=False)

    def __post_init__(self) -> None:
        self.visible_chars = max(1, int(self.visible_chars))
        start = 0
        for index, char in enumerate(self.text):
            if char == '\n':
                self._line_ranges.append((start, index))
                start = index + 1
        self._line_ranges.append((start, len(self.text)))

    @property
    def line_count(self) -> int:
        return len(self._line_ranges)

    @property
    def current_range(self) -> Tuple[int, int]:
        return self._line_ranges[self.line_index]

    @property
    def current_line_length(self) -> int:
        start, end = self.current_range
        return end - start

    @property
    def visible_text(self) -> str:
        return self.text_slice(self.column, self.visible_chars)

    @property
    def max_column(self) -> int:
        if self._max_column_override is not None:
            return self._max_column_override
        return max(0, self.current_line_length - self.visible_chars)

    def text_slice(self, column: int, length: int) -> str:
        start, end = self.current_range
        column = max(0, min(int(column), self.max_column))
        start += column
        return self.text[start:min(end, start + max(1, int(length)))]

    def text_between(self, start_column: int, end_column: int) -> str:
        start, end = self.current_range
        left = max(0, min(int(start_column), self.current_line_length))
        right = max(left, min(int(end_column), self.current_line_length))
        return self.text[start + left:start + right]

    def line_slice(self, line_index: int, length: int, column: int = 0) -> str:
        """Return a bounded slice of any line at a shared viewport column."""
        line_index = max(0, min(int(line_index), self.line_count - 1))
        start, end = self._line_ranges[line_index]
        column = max(0, min(int(column), end - start))
        start += column
        return self.text[start:min(end, start + max(1, int(length)))]

    def set_column(self, column: int) -> None:
        self.column = max(0, min(int(column), self.max_column))

    def set_max_column(self, column: Optional[int]) -> None:
        """Set an optional pixel-layout-derived terminal character column."""
        if column is None:
            self._max_column_override = None
        else:
            self._max_column_override = max(
                0, min(int(column), self.current_line_length))
        self.set_column(self.column)

    def suffix_start_for_width(self, measure: Callable[[str], float],
                               max_width: float) -> int:
        """Return the first column of the longest end suffix fitting ``max_width``.

        Only the short visible suffix is measured. This avoids laying out a
        copied line that may contain tens of thousands of characters.
        """
        start, end = self.current_range
        column = end - start
        limit = max(1.0, float(max_width))
        while column > 0:
            candidate = column - 1
            if measure(self.text[start + candidate:end]) > limit:
                break
            column = candidate
        return column

    @property
    def can_navigate(self) -> bool:
        return self.line_count > 1 or any(
            end - start > self.visible_chars
            for start, end in self._line_ranges
        )

    def move_line(self, delta: int) -> bool:
        next_line = max(0, min(self.line_index + int(delta),
                               self.line_count - 1))
        if next_line == self.line_index:
            return False
        self.line_index = next_line
        self.column = 0
        return True

    def width_probe(self, max_chars: int):
        """Yield small per-line samples; never duplicate a full long line."""
        count = max(1, int(max_chars))
        for start, end in self._line_ranges:
            yield self.text[start:min(end, start + count)], end - start > count
