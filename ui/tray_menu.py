"""Small, DPI-aware custom tray popup for Dose Ctrl+C."""

import ctypes
import sys

from PySide6.QtCore import Qt, Signal, QSize, QEvent, QPoint, QTimer
from PySide6.QtGui import QColor, QCursor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
        thumb_x = rect.right() - thumb_size - 1 if self.isChecked() else rect.left() + 1
        painter.setBrush(QColor('#f7f7f7') if self.isEnabled() else QColor('#b0b0b0'))
        painter.drawEllipse(thumb_x, rect.top() + 1, thumb_size, thumb_size)

class TrayMenuPopup(QWidget):
    """Frameless popup used instead of the unstyleable native tray QMenu."""

    feedback_toggled = Signal(bool)
    holding_toggled = Signal(bool)
    language_toggled = Signal(str)
    quit_requested = Signal()

    _TEXT = {
        'zh': {
            'feedback': '显示复制反馈',
            'holding': '等待 Ctrl+V 后收起',
            'quit': '退出 Does Ctrl+C Work',
        },
        'en': {
            'feedback': 'Show copy feedback',
            'holding': 'Dismiss on Ctrl+V',
            'quit': 'Quit',
        },
    }

    def __init__(self, language='zh', parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName('trayPopup')
        self._language = language if language in self._TEXT else 'zh'
        self._build_ui()
        self.set_language(self._language)
        self.installEventFilter(self)
        self._application = QApplication.instance()
        self._application.installEventFilter(self)
        self._pointer_button_down = False
        self._outside_click_timer = QTimer(self)
        self._outside_click_timer.setInterval(40)
        self._outside_click_timer.timeout.connect(self._dismiss_after_external_click)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.panel = QFrame(self)
        self.panel.setObjectName('trayPanel')
        self.panel.setFixedWidth(210)
        root.addWidget(self.panel)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

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
        slash.setStyleSheet('color: rgba(142, 142, 142, 0.3); font-size: 8.5px; font-family: monospace;')

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

        divider = QFrame(self.panel)
        divider.setObjectName('trayDivider')
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        self.quit_button = QPushButton(self.panel)
        self.quit_button.setObjectName('quitButton')
        self.quit_button.setCursor(Qt.PointingHandCursor)
        self.quit_button.clicked.connect(self.quit_requested)
        layout.addWidget(self.quit_button)

        self.setStyleSheet('''
            #trayPanel { background: #252525; border: 1px solid #414141; border-radius: 8px; }
            #trayTitle { color: #f2f2f2; font-size: 11px; font-weight: 600; }
            #trayLabel { color: #ececec; font-size: 11px; }
            #trayShortcut { color: #929292; font-size: 8px; }
            #trayDivider { color: #414141; margin: 2px 0; }
            #quitButton { color: #ececec; background: transparent; border: 0; border-radius: 5px;
                          min-height: 24px; font-size: 11px; text-align: left; padding-left: 6px; }
            #quitButton:hover { background: #3a3a3a; }
        ''')

    def _add_switch_row(self, layout):
        row = QWidget(self.panel)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 2, 2, 2)
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
        # Full shortcut strings make this intentionally compact popup much
        # wider on Windows. They remain documented in README and tooltips.
        self.feedback_shortcut.clear()
        self.holding_shortcut.clear()
        self.quit_button.setText(text['quit'])

        # Style language buttons based on selection
        if self._language == 'en':
            self.btn_en.setStyleSheet('color: #ffffff; font-size: 10px; font-weight: bold; background: transparent; border: 0; padding: 0;')
            self.btn_zh.setStyleSheet('color: #8e8e8e; font-size: 8.5px; font-weight: normal; background: transparent; border: 0; padding: 0;')
        else:
            self.btn_en.setStyleSheet('color: #8e8e8e; font-size: 8.5px; font-weight: normal; background: transparent; border: 0; padding: 0;')
            self.btn_zh.setStyleSheet('color: #ffffff; font-size: 10px; font-weight: bold; background: transparent; border: 0; padding: 0;')

        self.setToolTip('English' if self._language == 'zh' else '中文')

    def set_state(self, feedback_enabled, holding_enabled):
        for switch, checked in ((self.feedback_switch, feedback_enabled),
                                (self.holding_switch, holding_enabled)):
            switch.blockSignals(True)
            switch.setChecked(checked)
            switch.blockSignals(False)

    def eventFilter(self, obj, event):
        """Close when either Qt or the whole application loses activation."""
        if (obj is self and event.type() == QEvent.Type.WindowDeactivate) or (
                obj is self._application and event.type() == QEvent.Type.ApplicationDeactivate):
            self.hide()
        return super().eventFilter(obj, event)

    @staticmethod
    def _is_windows_pointer_button_down() -> bool:
        """Read mouse buttons only while this popup is visible on Windows."""
        if not sys.platform.startswith('win'):
            return False
        try:
            user32 = ctypes.windll.user32
            return any(user32.GetAsyncKeyState(button) & 0x8000
                       for button in (0x01, 0x02, 0x04))
        except (AttributeError, OSError):
            return False

    def _should_dismiss_for_pointer(self, pointer_down: bool, global_pos: QPoint) -> bool:
        """Dismiss only on the new outside click, never merely on pointer movement."""
        return (pointer_down and not self._pointer_button_down and
                not self.rect().contains(self.mapFromGlobal(global_pos)))

    def _dismiss_after_external_click(self):
        pointer_down = self._is_windows_pointer_button_down()
        if self._should_dismiss_for_pointer(pointer_down, QCursor.pos()):
            self.hide()
        self._pointer_button_down = pointer_down

    def hideEvent(self, event):
        self._outside_click_timer.stop()
        self._pointer_button_down = False
        super().hideEvent(event)

    def show_near_tray(self, tray_icon):
        self.adjustSize()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        available = screen.availableGeometry()

        # Prefer the tray icon's screen position over cursor
        icon_geo = tray_icon.geometry()
        if icon_geo.isValid() and icon_geo.width() > 0:
            anchor_x = icon_geo.right() + 1
            anchor_y = icon_geo.top() - 1
        else:
            anchor_x = QCursor.pos().x()
            anchor_y = QCursor.pos().y()

        x = anchor_x - self.width()
        y = anchor_y - self.height()

        # Keep inside available screen area
        x = max(available.left() + 6, min(x, available.right() - self.width() - 6))
        y = max(available.top() + 6, min(y, available.bottom() - self.height() - 6))

        self.move(x, y)
        self.show()
        self.raise_()
        self._pointer_button_down = self._is_windows_pointer_button_down()
        self._outside_click_timer.start()
