"""Compact native-lifecycle tray menu for Dose Ctrl+C."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize, QPoint
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ui.image_layout import (IMAGE_LAYOUT_CASCADE, IMAGE_LAYOUT_FAN,
                             normalize_image_layout)
from ui.theme import tray_colors


class _ActionTextProxy:
    """Expose the pre-submenu label for legacy fallback tests."""

    def __init__(self, action):
        self._action = action

    def text(self):
        return self._action.text().removeprefix('• ')


class ToggleSwitch(QAbstractButton):
    """A compact Apple-like toggle; Qt scales its logical size for Windows DPI."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self):
        return QSize(28, 16)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        colors = tray_colors()
        track = QColor('#facc15') if self.isChecked() else QColor(colors.switch_off)
        if not self.isEnabled():
            track.setAlpha(90)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        thumb_size = rect.height() - 2
        thumb_x = (rect.right() - thumb_size - 1
                   if self.isChecked() else rect.left() + 1)
        painter.setBrush(
            QColor(colors.switch_thumb) if self.isEnabled() else QColor('#b0b0b0'))
        painter.drawEllipse(thumb_x, rect.top() + 1, thumb_size, thumb_size)


class ImageLayoutSelector(QPushButton):
    """One compact layout row with a native-looking hover submenu."""

    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = IMAGE_LAYOUT_FAN
        self._language = 'zh'
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(24)
        self._menu = QMenu(self)
        self._menu.setObjectName('layoutSubmenu')
        self._fan_action = self._menu.addAction('')
        self._cascade_action = self._menu.addAction('')
        # Compatibility aliases for the former two-button fallback API.
        self.btn_fan = _ActionTextProxy(self._fan_action)
        self.btn_cascade = _ActionTextProxy(self._cascade_action)
        self._fan_action.triggered.connect(
            lambda: self._select(IMAGE_LAYOUT_FAN))
        self._cascade_action.triggered.connect(
            lambda: self._select(IMAGE_LAYOUT_CASCADE))
        self.setMenu(self._menu)
        self.setAccessibleName('Image layout')
        self.set_language('zh')
        self.set_mode(IMAGE_LAYOUT_FAN)

    def sizeHint(self):
        return QSize(186, 26)

    @property
    def mode(self):
        return self._mode

    def set_mode(self, mode):
        mode = normalize_image_layout(mode)
        self._mode = mode
        self._refresh_visuals()

    def set_language(self, language):
        self._language = language if language in ('zh', 'en') else 'zh'
        self._fan_action.setText('扇形' if self._language == 'zh' else 'Fan')
        self._cascade_action.setText(
            '层叠' if self._language == 'zh' else 'Cascade')
        self._refresh_visuals()

    def set_theme(self):
        self._refresh_visuals()

    def enterEvent(self, event):
        if not self._menu.isVisible():
            self.showMenu()
        super().enterEvent(event)

    def _refresh_visuals(self):
        colors = tray_colors()
        label = '图片布局' if self._language == 'zh' else 'Image layout'
        value = ('扇形' if self._language == 'zh' else 'Fan')
        icon_name = 'fluent_image_multiple.ico'
        if self._mode == IMAGE_LAYOUT_CASCADE:
            value = '层叠' if self._language == 'zh' else 'Cascade'
            icon_name = 'fluent_slide_multiple.ico'
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
        self.setIcon(QIcon(str(root / 'assets' / 'image_layout' / icon_name)))
        self.setIconSize(QSize(16, 16))
        self.setText(f'{label}                                      {value}')
        self.setStyleSheet(
            f'ImageLayoutSelector {{ color: {colors.text}; background: transparent; '
            f'border: 0; border-radius: 5px; text-align: left; padding: 0 4px; '
            f'font-size: 11px; }} ImageLayoutSelector:hover {{ '
            f'background: {colors.hover}; }} '
            'ImageLayoutSelector::menu-indicator { image: none; width: 0; }')
        self._menu.setStyleSheet(
            f'QMenu#layoutSubmenu {{ background: {colors.surface}; color: {colors.text}; '
            f'border: 0; border-radius: 8px; padding: 3px; }} '
            f'QMenu#layoutSubmenu::item {{ min-width: 88px; min-height: 22px; '
            f'padding: 0 10px; border-radius: 5px; }} '
            f'QMenu#layoutSubmenu::item:selected {{ background: {colors.hover}; }}')
        self._fan_action.setText(
            ('• ' if self._mode == IMAGE_LAYOUT_FAN else '') +
            ('扇形' if self._language == 'zh' else 'Fan'))
        self._cascade_action.setText(
            ('• ' if self._mode == IMAGE_LAYOUT_CASCADE else '') +
            ('层叠' if self._language == 'zh' else 'Cascade'))

    def _select(self, mode):
        if mode == self._mode:
            return
        self.set_mode(mode)
        self.mode_changed.emit(mode)

    def click(self):
        """Compatibility helper for the old single-row selector test path."""
        self._select(IMAGE_LAYOUT_CASCADE
                     if self._mode == IMAGE_LAYOUT_FAN else IMAGE_LAYOUT_FAN)

    def text(self):
        return ''


class TrayMenuPopup(QMenu):
    """A standard QMenu lifecycle containing the existing custom panel.

    QMenu owns outside-click, focus-loss and Escape dismissal. The complete
    visual surface remains a QWidgetAction so the compact rounded layout does
    not change with the platform menu-item style.
    """

    feedback_toggled = Signal(bool)
    holding_toggled = Signal(bool)
    language_toggled = Signal(str)
    image_layout_changed = Signal(str)
    palette_changed = Signal(str, str)
    quit_requested = Signal()

    _TEXT = {
        'zh': {
            'feedback': '显示复制反馈',
            'holding': '等待 Ctrl+V 后收起',
            'quit': '退出',
        },
        'en': {
            'feedback': 'Show copy feedback',
            'holding': 'Dismiss on Ctrl+V',
            'quit': 'Quit',
        },
    }

    def __init__(self, language='zh', parent=None):
        super().__init__(parent)
        self.setObjectName('trayMenu')
        self.setAttribute(Qt.WA_TranslucentBackground)
        if sys.platform.startswith('win'):
            # Keep Explorer's hidden-icons flyout active behind this popup.
            # QMenu still owns its normal popup mouse grab and dismissal.
            self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.NoDropShadowWindowHint, True)
        self.setContentsMargins(0, 0, 0, 0)
        self._language = language if language in self._TEXT else 'zh'
        self._palette_name = 'classic'
        self._custom_color = '#52677f'
        self._build_ui()
        self.set_language(self._language)

    def _build_ui(self):
        self.panel = QFrame()
        self.panel.setObjectName('trayPanel')
        self.panel.setFixedWidth(210)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(10, 4, 10, 6)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 2, 0)
        title = QLabel('Does Ctrl+C Work', self.panel)
        title.setObjectName('trayTitle')
        header.addWidget(title)
        header.addStretch(1)

        self.lang_container = QWidget(self.panel)
        lang_layout = QHBoxLayout(self.lang_container)
        lang_layout.setContentsMargins(0, 0, 0, 0)
        lang_layout.setSpacing(3)

        self.btn_en = QPushButton('EN', self.panel)
        self.btn_en.setCursor(Qt.PointingHandCursor)
        self.btn_en.clicked.connect(lambda: self._set_lang_and_emit('en'))

        slash = QLabel('/', self.panel)
        slash.setStyleSheet(
            'color: rgba(142, 142, 142, 0.3); font-size: 8.5px; '
            'font-family: monospace;')

        self.btn_zh = QPushButton('中', self.panel)
        self.btn_zh.setCursor(Qt.PointingHandCursor)
        self.btn_zh.clicked.connect(lambda: self._set_lang_and_emit('zh'))

        lang_layout.addWidget(self.btn_en)
        lang_layout.addWidget(slash)
        lang_layout.addWidget(self.btn_zh)
        header.addWidget(self.lang_container)
        layout.addLayout(header)

        (self.feedback_label, self.feedback_switch,
         self.feedback_shortcut) = self._add_switch_row(layout)
        (self.holding_label, self.holding_switch,
         self.holding_shortcut) = self._add_switch_row(layout)
        self.feedback_switch.toggled.connect(self.feedback_toggled)
        self.holding_switch.toggled.connect(self.holding_toggled)

        self.image_layout_selector = ImageLayoutSelector(self.panel)
        self.image_layout_selector.mode_changed.connect(
            self.image_layout_changed)
        selector_row = QHBoxLayout()
        selector_row.setContentsMargins(4, 0, 2, 0)
        selector_row.addWidget(self.image_layout_selector)
        layout.addLayout(selector_row)

        self.palette_button = QPushButton(self.panel)
        self.palette_button.setObjectName('paletteButton')
        self.palette_button.setCursor(Qt.PointingHandCursor)
        self._palette_menu = QMenu(self.palette_button)
        self._palette_actions = {
            'classic': self._palette_menu.addAction(''),
            'light': self._palette_menu.addAction(''),
            'custom': self._palette_menu.addAction(''),
        }
        for name, action in self._palette_actions.items():
            action.triggered.connect(lambda checked=False, value=name:
                                     self._choose_palette(value))
        self.palette_button.setMenu(self._palette_menu)
        layout.addWidget(self.palette_button)

        self.quit_button = QPushButton(self.panel)
        self.quit_button.setObjectName('quitButton')
        self.quit_button.setCursor(Qt.PointingHandCursor)
        self.quit_button.clicked.connect(self._request_quit)
        layout.addWidget(self.quit_button)

        # One widget action preserves the previous panel pixel-for-pixel while
        # the surrounding QMenu supplies the platform popup lifecycle.
        self._panel_action = QWidgetAction(self)
        self._panel_action.setDefaultWidget(self.panel)
        self.addAction(self._panel_action)

        self._apply_theme()

    def set_theme(self, light):
        self._apply_theme()
        self.set_language(self._language)
        self.image_layout_selector.set_theme()
        self.feedback_switch.update()
        self.holding_switch.update()

    def set_palette(self, palette, custom_color='#52677f'):
        self._palette_name = (palette if palette in ('classic', 'light', 'custom')
                              else 'classic')
        self._custom_color = custom_color or '#52677f'
        self._refresh_palette_button()

    def _apply_theme(self):
        colors = tray_colors()
        self.setStyleSheet(f'''
            QMenu#trayMenu {{ background: transparent; border: 0; padding: 0; }}
            #trayPanel {{ background: {colors.surface}; border: 0;
                         border-radius: 10px; }}
            #trayTitle {{ color: {colors.title}; font-size: 11px; font-weight: 600; }}
            #trayLabel {{ color: {colors.text}; font-size: 11px; }}
            #trayShortcut {{ color: {colors.muted}; font-size: 8px; }}
            #quitButton {{ color: {colors.text}; background: transparent; border: 0;
                          border-radius: 5px; min-height: 22px; font-size: 11px;
                          text-align: left; padding-left: 4px; }}
            #quitButton:hover {{ background: {colors.hover}; }}
            #paletteButton {{ color: {colors.text}; background: transparent; border: 0;
                             border-radius: 5px; min-height: 24px; font-size: 11px;
                             text-align: left; padding-left: 4px; }}
            #paletteButton:hover {{ background: {colors.hover}; }}
        ''')

    def _add_switch_row(self, layout):
        row = QWidget(self.panel)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 1, 2, 1)
        row_layout.setSpacing(6)
        label = QLabel(row)
        label.setObjectName('trayLabel')
        shortcut = QLabel(row)
        shortcut.setObjectName('trayShortcut')
        switch = ToggleSwitch(row)
        row_layout.addWidget(label)
        row_layout.addStretch(1)
        row_layout.addWidget(shortcut)
        row_layout.addWidget(switch)
        layout.addWidget(row)
        return label, switch, shortcut

    def _request_quit(self):
        self.close()
        self.quit_requested.emit()

    def _set_lang_and_emit(self, lang):
        if self._language != lang:
            self.set_language(lang)
            self.language_toggled.emit(lang)

    def set_language(self, language):
        self._language = language if language in self._TEXT else 'zh'
        text = self._TEXT[self._language]
        self.feedback_label.setText(text['feedback'])
        self.holding_label.setText(text['holding'])
        self.feedback_label.setToolTip('Ctrl+Shift+M')
        self.holding_label.setToolTip('Ctrl+Shift+H')
        self.feedback_shortcut.clear()
        self.holding_shortcut.clear()
        self.quit_button.setText(text['quit'])
        colors = tray_colors()

        if self._language == 'en':
            self.btn_en.setStyleSheet(
                f'color: {colors.title}; font-size: 10px; font-weight: bold; '
                'background: transparent; border: 0; padding: 0;')
            self.btn_zh.setStyleSheet(
                f'color: {colors.muted}; font-size: 8.5px; font-weight: normal; '
                'background: transparent; border: 0; padding: 0;')
        else:
            self.btn_en.setStyleSheet(
                f'color: {colors.muted}; font-size: 8.5px; font-weight: normal; '
                'background: transparent; border: 0; padding: 0;')
            self.btn_zh.setStyleSheet(
                f'color: {colors.title}; font-size: 10px; font-weight: bold; '
                'background: transparent; border: 0; padding: 0;')

        self.setToolTip('English' if self._language == 'zh' else '中文')
        self.image_layout_selector.set_language(self._language)
        self.image_layout_selector.setToolTip(
            '图片展示方式' if self._language == 'zh' else 'Image layout')
        self._refresh_palette_button()
        self.adjustSize()

    def _refresh_palette_button(self):
        if not hasattr(self, 'palette_button'):
            return
        label = 'Colour' if self._language == 'en' else '配色'
        values = {
            'classic': 'Classic' if self._language == 'en' else '经典',
            'light': 'Light' if self._language == 'en' else '浅色',
            'custom': 'Custom' if self._language == 'en' else '自定义',
        }
        self.palette_button.setText(
            f'{label}                                      {values[self._palette_name]}')
        entries = {
            'classic': 'Classic' if self._language == 'en' else '经典深色',
            'light': 'Light glass' if self._language == 'en' else '浅色玻璃',
            'custom': 'Custom...' if self._language == 'en' else '自定义...',
        }
        for name, action in self._palette_actions.items():
            action.setText(('• ' if name == self._palette_name else '') + entries[name])
        colors = tray_colors()
        self._palette_menu.setStyleSheet(
            f'QMenu {{ background: {colors.surface}; color: {colors.text}; border: 0; '
            f'border-radius: 8px; padding: 3px; }} QMenu::item {{ min-width: 104px; '
            f'min-height: 22px; padding: 0 10px; border-radius: 5px; }} '
            f'QMenu::item:selected {{ background: {colors.hover}; }}')

    def _choose_palette(self, palette):
        if palette == 'custom':
            from PySide6.QtWidgets import QColorDialog
            color = QColorDialog.getColor(QColor(self._custom_color), self,
                                          'Choose Dose Ctrl+C colour')
            if not color.isValid():
                return
            self._custom_color = color.name()
        self._palette_name = palette
        self._refresh_palette_button()
        self.palette_changed.emit(
            palette, self._custom_color if palette == 'custom' else '')

    def set_state(self, feedback_enabled, holding_enabled,
                  image_layout_mode='fan'):
        for switch, checked in ((self.feedback_switch, feedback_enabled),
                                (self.holding_switch, holding_enabled)):
            switch.blockSignals(True)
            switch.setChecked(checked)
            switch.blockSignals(False)
        self.image_layout_selector.set_mode(image_layout_mode)

    def show_near_tray(self, tray_icon):
        """Show left-click menu at the same tray-relative anchor as before."""
        self.ensurePolished()
        menu_size = self.sizeHint()
        screen = (QApplication.screenAt(QCursor.pos()) or
                  QApplication.primaryScreen())
        available = screen.availableGeometry()
        icon_geo = tray_icon.geometry()
        if icon_geo.isValid() and icon_geo.width() > 0:
            anchor_x = icon_geo.right() + 1
            anchor_y = icon_geo.top() - 1
        else:
            cursor = QCursor.pos()
            anchor_x = cursor.x()
            anchor_y = cursor.y()

        x = anchor_x - menu_size.width()
        y = anchor_y - menu_size.height()
        x = max(available.left() + 6,
                min(x, available.right() - menu_size.width() - 6))
        y = max(available.top() + 6,
                min(y, available.bottom() - menu_size.height() - 6))
        self.popup(QPoint(x, y))


def create_tray_menu(language='zh', parent=None):
    """Use a real HMENU loop on Windows; retain the Qt menu elsewhere."""
    if sys.platform.startswith('win'):
        try:
            from ui.windows_tray_menu import WindowsNativeTrayMenu
            return WindowsNativeTrayMenu(language, parent)
        except (AttributeError, OSError, TypeError):
            pass
    return TrayMenuPopup(language, parent)
