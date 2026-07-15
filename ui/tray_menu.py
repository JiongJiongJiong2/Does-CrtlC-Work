"""Compact native-lifecycle tray menu for Dose Ctrl+C."""

import sys

from PySide6.QtCore import Qt, Signal, QSize, QPoint
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPen
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
from ui.resource_path import resource_path


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
        track = QColor('#facc15') if self.isChecked() else QColor('#4b4b4b')
        if not self.isEnabled():
            track.setAlpha(90)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        thumb_size = rect.height() - 2
        thumb_x = (rect.right() - thumb_size - 1
                   if self.isChecked() else rect.left() + 1)
        painter.setBrush(
            QColor('#f7f7f7') if self.isEnabled() else QColor('#b0b0b0'))
        painter.drawEllipse(thumb_x, rect.top() + 1, thumb_size, thumb_size)


class ImageLayoutSelector(QAbstractButton):
    """Two official Fluent thumbnails in one compact, icon-only control."""

    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = IMAGE_LAYOUT_FAN
        self._icons = (
            QIcon(resource_path('assets', 'image_layout',
                                'fluent_image_multiple.ico')),
            QIcon(resource_path('assets', 'image_layout',
                                'fluent_slide_multiple.ico')),
        )
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.sizeHint())
        self.setAccessibleName('Image layout')
        self.clicked.connect(self.toggle_mode)

    def sizeHint(self):
        return QSize(64, 24)

    @property
    def mode(self):
        return self._mode

    def set_mode(self, mode):
        mode = normalize_image_layout(mode)
        if mode != self._mode:
            self._mode = mode
            self.update()

    def toggle_mode(self):
        mode = (IMAGE_LAYOUT_CASCADE
                if self._mode == IMAGE_LAYOUT_FAN else IMAGE_LAYOUT_FAN)
        self.set_mode(mode)
        self.mode_changed.emit(mode)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        selected = 0 if self._mode == IMAGE_LAYOUT_FAN else 1
        for index, icon in enumerate(self._icons):
            left = index * 32
            cell = self.rect().adjusted(left + 1, 1,
                                        -(self.width() - left - 31), -1)
            if index == selected:
                painter.setBrush(QColor(250, 204, 21, 22))
                painter.setPen(QPen(QColor('#facc15'), 1))
                painter.drawRoundedRect(cell, 5, 5)
            else:
                painter.setPen(Qt.NoPen)
            painter.setOpacity(1.0 if index == selected else 0.52)
            icon.paint(painter, cell.adjusted(6, 3, -6, -3))
        painter.end()


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
        self._build_ui()
        self.set_language(self._language)

    def _build_ui(self):
        self.panel = QFrame()
        self.panel.setObjectName('trayPanel')
        self.panel.setFixedWidth(210)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(1)

        header = QHBoxLayout()
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
        selector_row.setContentsMargins(0, 0, 0, 0)
        selector_row.addStretch(1)
        selector_row.addWidget(self.image_layout_selector)
        selector_row.addStretch(1)
        layout.addLayout(selector_row)

        divider = QFrame(self.panel)
        divider.setObjectName('trayDivider')
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

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

        self.setStyleSheet('''
            QMenu#trayMenu { background: transparent; border: 0; padding: 0; }
            #trayPanel { background: #252525; border: 1px solid #414141;
                         border-radius: 10px; }
            #trayTitle { color: #f2f2f2; font-size: 11px; font-weight: 600; }
            #trayLabel { color: #ececec; font-size: 11px; }
            #trayShortcut { color: #929292; font-size: 8px; }
            #trayDivider { color: #414141; margin: 1px 0; }
            #quitButton { color: #ececec; background: transparent; border: 0;
                          border-radius: 5px; min-height: 22px; font-size: 11px;
                          text-align: left; padding-left: 6px; }
            #quitButton:hover { background: #3a3a3a; }
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

        if self._language == 'en':
            self.btn_en.setStyleSheet(
                'color: #ffffff; font-size: 10px; font-weight: bold; '
                'background: transparent; border: 0; padding: 0;')
            self.btn_zh.setStyleSheet(
                'color: #8e8e8e; font-size: 8.5px; font-weight: normal; '
                'background: transparent; border: 0; padding: 0;')
        else:
            self.btn_en.setStyleSheet(
                'color: #8e8e8e; font-size: 8.5px; font-weight: normal; '
                'background: transparent; border: 0; padding: 0;')
            self.btn_zh.setStyleSheet(
                'color: #ffffff; font-size: 10px; font-weight: bold; '
                'background: transparent; border: 0; padding: 0;')

        self.setToolTip('English' if self._language == 'zh' else '中文')
        self.image_layout_selector.setToolTip(
            '图片展示方式' if self._language == 'zh' else 'Image layout')
        self.adjustSize()

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
