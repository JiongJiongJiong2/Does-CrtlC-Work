"""脚本感知的文本样式、宽度测量与最终布局缓存。"""

from dataclasses import dataclass
from typing import ClassVar, Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetricsF, QStaticText, QTransform

from config import SIZES, TEXT_RENDER


@dataclass
class TextStyle:
    kind: str
    font: QFont
    metrics: QFontMetricsF

    def horizontal_advance(self, text: str) -> float:
        return self.metrics.horizontalAdvance(text)

    def elide(self, text: str) -> str:
        available = int(SIZES['box_max_width'] - SIZES['box_padding'])
        return self.metrics.elidedText(text, Qt.ElideRight, available)

    def static_layout(self, text: str) -> QStaticText:
        layout = QStaticText(text)
        layout.prepare(QTransform(), self.font)
        return layout


class TextStyleResolver:
    """根据文本脚本选择字体，并缓存字体与 metrics。"""

    _cache: ClassVar[Dict[str, TextStyle]] = {}
    _latin_family: ClassVar[str] = ''
    _cjk_family: ClassVar[str] = ''

    @classmethod
    def set_content_fonts(cls, latin_family: str = '', cjk_family: str = '') -> None:
        """Apply user-selected feedback fonts and invalidate cached metrics."""
        latin_family = (latin_family or '').strip()
        cjk_family = (cjk_family or '').strip()
        if (latin_family, cjk_family) == (cls._latin_family, cls._cjk_family):
            return
        cls._latin_family = latin_family
        cls._cjk_family = cjk_family
        cls._cache.clear()

    @staticmethod
    def _has_cjk(text: str) -> bool:
        return any(
            '\u3400' <= char <= '\u4dbf' or
            '\u4e00' <= char <= '\u9fff' or
            '\uf900' <= char <= '\ufaff' or
            '\u3040' <= char <= '\u30ff' or
            '\uac00' <= char <= '\ud7af'
            for char in text
        )

    @staticmethod
    def _has_emoji(text: str) -> bool:
        return any(
            '\U0001f000' <= char <= '\U0001faff' or
            '\u2600' <= char <= '\u27bf'
            for char in text
        )

    @classmethod
    def resolve(cls, text: str) -> TextStyle:
        if cls._has_cjk(text):
            kind = 'ui_cjk'
        elif cls._has_emoji(text):
            kind = 'ui_emoji'
        else:
            kind = 'code_latin'
        if kind not in cls._cache:
            cls._cache[kind] = cls._build(kind)
        return cls._cache[kind]

    @staticmethod
    def _build(kind: str) -> TextStyle:
        font = QFont()
        font.setPointSize(TEXT_RENDER['font_size'])
        if kind == 'code_latin':
            font.setFamilies(([TextStyleResolver._latin_family]
                              if TextStyleResolver._latin_family else []) +
                             ['Cascadia Mono', 'Cascadia Code', 'Consolas'])
            font.setStyleHint(QFont.Monospace)
            font.setLetterSpacing(QFont.AbsoluteSpacing,
                                  TEXT_RENDER['latin_letter_spacing'])
        elif kind == 'ui_emoji':
            font.setFamilies(['Segoe UI Emoji', 'Segoe UI Variable', 'Segoe UI'])
            font.setStyleHint(QFont.SansSerif)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 0)
        else:
            font.setFamilies(([TextStyleResolver._cjk_family]
                              if TextStyleResolver._cjk_family else []) +
                             ['Segoe UI Variable', 'Microsoft YaHei UI',
                              'Microsoft YaHei', 'Segoe UI'])
            font.setStyleHint(QFont.SansSerif)
            font.setLetterSpacing(QFont.AbsoluteSpacing,
                                  TEXT_RENDER['cjk_letter_spacing'])
        return TextStyle(kind, font, QFontMetricsF(font))
