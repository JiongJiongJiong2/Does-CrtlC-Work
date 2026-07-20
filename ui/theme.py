"""Small, persisted colour palettes shared by feedback and tray surfaces."""

import json
from dataclasses import dataclass, replace

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

from config import COLORS, IMAGE_STACK


PALETTE_CLASSIC = 'classic'
PALETTE_LIGHT = 'light'
PALETTE_CUSTOM = 'custom'
PALETTES = (PALETTE_CLASSIC, PALETTE_LIGHT, PALETTE_CUSTOM)
COLOR_TARGETS = ('menu', 'menu_text', 'content', 'content_text', 'image')


@dataclass(frozen=True)
class TrayColors:
    surface: str
    hover: str
    title: str
    text: str
    muted: str
    separator: str
    switch_off: str
    switch_thumb: str
    icon: str


_DARK_TRAY = TrayColors(
    surface='#252525', hover='#3a3a3a', title='#f2f2f2', text='#ececec',
    muted='#8e8e8e', separator='#555555', switch_off='#4b4b4b',
    switch_thumb='#f7f7f7', icon='#212121')
_LIGHT_TRAY = TrayColors(
    surface='#f6f6f6', hover='#e7e7e7', title='#1f1f1f', text='#2c2c2c',
    muted='#666666', separator='#b7b7b7', switch_off='#b7b7b7',
    switch_thumb='#ffffff', icon='#212121')

_tray_colors = _DARK_TRAY
_is_light = False
_color_overrides = {}


def tray_colors() -> TrayColors:
    return _tray_colors


def is_light_theme() -> bool:
    return _is_light


def _blend(source: QColor, target: QColor, amount: float) -> QColor:
    return QColor(
        round(source.red() + (target.red() - source.red()) * amount),
        round(source.green() + (target.green() - source.green()) * amount),
        round(source.blue() + (target.blue() - source.blue()) * amount))


def _is_light_color(color: QColor) -> bool:
    return color.lightnessF() >= 0.62


def _apply_surface(surface: QColor, light: bool) -> None:
    """Derive readable feedback and tray tokens from one chosen surface."""
    global _tray_colors, _is_light
    _is_light = light
    foreground = QColor('#202020' if light else '#f5f5f5')
    muted = QColor('#626262' if light else '#9b9b9b')
    hover = _blend(surface, QColor('#202020' if light else '#ffffff'), 0.09)
    border = QColor('#242424' if light else '#ffffff')
    border_alpha = 26 if light else 25
    image_alpha = 220 if light else 232
    placeholder_alpha = 212 if light else 205

    _tray_colors = TrayColors(
        surface=surface.name(), hover=hover.name(), title=foreground.name(),
        text=foreground.name(), muted=muted.name(),
        separator=_blend(surface, foreground, 0.28).name(),
        switch_off=_blend(surface, foreground, 0.35).name(),
        switch_thumb='#ffffff' if light else '#f7f7f7', icon='#212121')
    COLORS.update({
        'box_bg': (surface.red(), surface.green(), surface.blue(), 220 if light else 217),
        'text': foreground.name(),
    })
    IMAGE_STACK.update({
        'border_color': (border.red(), border.green(), border.blue(), border_alpha),
        'bg_color': (surface.red(), surface.green(), surface.blue(), image_alpha),
        'placeholder_border_color': (border.red(), border.green(), border.blue(), border_alpha + 3),
        'placeholder_bg_color': (surface.red(), surface.green(), surface.blue(), placeholder_alpha),
        'image_border_color': (border.red(), border.green(), border.blue(), border_alpha + 5),
        'image_surface_color': (surface.red(), surface.green(), surface.blue(), image_alpha),
    })


def _apply_palette(name: str, custom_color: str) -> None:
    if name == PALETTE_CLASSIC:
        _apply_surface(QColor('#000000'), False)
    elif name == PALETTE_LIGHT:
        _apply_surface(QColor('#fafafa'), True)
    else:
        color = QColor(custom_color)
        _apply_surface(color if color.isValid() else QColor('#52677f'),
                       _is_light_color(color))


def _valid_overrides(value) -> dict:
    if not isinstance(value, dict):
        return {}
    result = {}
    for target, color in value.items():
        if target in COLOR_TARGETS and isinstance(color, str):
            parsed = QColor(color)
            if parsed.isValid():
                result[target] = parsed.name()
    # Compatibility: versions before the split stored one `text` color.
    # Preserve its visual intent for both surfaces when users upgrade.
    legacy_text = value.get('text') if isinstance(value, dict) else None
    if legacy_text and 'menu_text' not in result and 'content_text' not in result:
        color = QColor(legacy_text)
        if color.isValid():
            result['menu_text'] = color.name()
            result['content_text'] = color.name()
    return result


def _apply_color_overrides(overrides: dict) -> None:
    """Apply independently selected surfaces after the base palette."""
    global _tray_colors
    overrides = _valid_overrides(overrides)

    if 'menu' in overrides:
        surface = QColor(overrides['menu'])
        light = _is_light_color(surface)
        foreground = QColor('#202020' if light else '#f5f5f5')
        _tray_colors = replace(
            _tray_colors, surface=surface.name(),
            hover=_blend(surface, foreground, 0.09).name(),
            title=foreground.name(), text=foreground.name(),
            muted=QColor('#626262' if light else '#9b9b9b').name(),
            separator=_blend(surface, foreground, 0.28).name(),
            switch_off=_blend(surface, foreground, 0.35).name(),
            switch_thumb='#ffffff' if light else '#f7f7f7')

    if 'content' in overrides:
        color = QColor(overrides['content'])
        COLORS['box_bg'] = (color.red(), color.green(), color.blue(),
                            220 if _is_light_color(color) else 217)

    if 'menu_text' in overrides:
        color = QColor(overrides['menu_text'])
        _tray_colors = replace(
            _tray_colors, title=color.name(), text=color.name(),
            muted=_blend(color, QColor(_tray_colors.surface), 0.42).name())

    if 'content_text' in overrides:
        color = QColor(overrides['content_text'])
        COLORS['text'] = color.name()

    if 'image' in overrides:
        color = QColor(overrides['image'])
        light = _is_light_color(color)
        border = QColor('#242424' if light else '#ffffff')
        border_alpha = 26 if light else 25
        image_alpha = 220 if light else 232
        placeholder_alpha = 212 if light else 205
        IMAGE_STACK.update({
            'border_color': (border.red(), border.green(), border.blue(), border_alpha),
            'bg_color': (color.red(), color.green(), color.blue(), image_alpha),
            'placeholder_border_color': (border.red(), border.green(), border.blue(), border_alpha + 3),
            'placeholder_bg_color': (color.red(), color.green(), color.blue(), placeholder_alpha),
            'image_border_color': (border.red(), border.green(), border.blue(), border_alpha + 5),
            'image_surface_color': (color.red(), color.green(), color.blue(), image_alpha),
        })


class ThemeController(QObject):
    """Persist and apply an app-owned palette; never follows system mode."""

    theme_changed = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._palette = settings.value('color_palette', PALETTE_CLASSIC, type=str)
        if self._palette not in PALETTES:
            self._palette = PALETTE_CLASSIC
        self._custom_color = settings.value(
            'custom_palette_color', '#52677f', type=str)
        self._color_overrides = self._load_color_overrides()
        _apply_palette(self._palette, self._custom_color)
        _apply_color_overrides(self._color_overrides)

    @property
    def palette(self) -> str:
        return self._palette

    @property
    def custom_color(self) -> str:
        return self._custom_color

    @property
    def color_overrides(self) -> dict:
        return dict(self._color_overrides)

    def _load_color_overrides(self) -> dict:
        raw = self._settings.value('color_overrides', '{}', type=str)
        if isinstance(raw, dict):
            return _valid_overrides(raw)
        try:
            return _valid_overrides(json.loads(raw or '{}'))
        except (TypeError, json.JSONDecodeError):
            return {}

    def _save_color_overrides(self) -> None:
        self._settings.setValue(
            'color_overrides', json.dumps(self._color_overrides, sort_keys=True))

    def _apply_current_theme(self) -> None:
        _apply_palette(self._palette, self._custom_color)
        _apply_color_overrides(self._color_overrides)

    def set_palette(self, palette: str, custom_color: str | None = None) -> None:
        palette = palette if palette in PALETTES else PALETTE_CLASSIC
        if custom_color:
            color = QColor(custom_color)
            if color.isValid():
                self._custom_color = color.name()
        changed = palette != self._palette or palette == PALETTE_CUSTOM
        self._palette = palette
        self._settings.setValue('color_palette', self._palette)
        self._settings.setValue('custom_palette_color', self._custom_color)
        self._apply_current_theme()
        if changed:
            self.theme_changed.emit(self._palette)

    def set_color_override(self, target: str, color: str | None) -> None:
        if target not in COLOR_TARGETS:
            return
        parsed = QColor(color) if color else QColor()
        if color and not parsed.isValid():
            return
        value = parsed.name() if color else None
        if value == self._color_overrides.get(target):
            return
        if value:
            self._color_overrides[target] = value
        else:
            self._color_overrides.pop(target, None)
        self._save_color_overrides()
        self._apply_current_theme()
        self.theme_changed.emit(self._palette)

    def reset_color_overrides(self) -> None:
        if not self._color_overrides:
            return
        self._color_overrides = {}
        self._save_color_overrides()
        self._apply_current_theme()
        self.theme_changed.emit(self._palette)
