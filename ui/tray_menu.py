"""Small, DPI-aware custom tray popup for Dose Ctrl+C."""

from PySide6.QtCore import Qt, Signal, QSize
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
        return QSize(38, 22)

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

        thumb_size = rect.height() - 4
        thumb_x = rect.right() - thumb_size - 2 if self.isChecked() else rect.left() + 2
        painter.setBrush(QColor('#f7f7f7') if self.isEnabled() else QColor('#b0b0b0'))
        painter.drawEllipse(thumb_x, rect.top() + 2, thumb_size, thumb_size)


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
            'quit': '退出 Dose Ctrl+C',
        },
        'en': {
            'feedback': 'Show copy feedback',
            'holding': 'Dismiss on Ctrl+V',
            'quit': 'Quit Dose Ctrl+C',
        },
    }

    def __init__(self, language='zh', parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName('trayPopup')
        self._language = language if language in self._TEXT else 'zh'
        self._build_ui()
        self.set_language(self._language)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.panel = QFrame(self)
        self.panel.setObjectName('trayPanel')
        root.addWidget(self.panel)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        header = QHBoxLayout()
        title = QLabel('Dose Ctrl+C', self.panel)
        title.setObjectName('trayTitle')
        header.addWidget(title)
        header.addStretch(1)
        self.language_button = QPushButton(self.panel)
        self.language_button.setObjectName('languageButton')
        self.language_button.setFixedSize(32, 22)
        self.language_button.clicked.connect(self._toggle_language)
        header.addWidget(self.language_button)
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
            #trayPanel { background: #252525; border: 1px solid #414141; border-radius: 12px; }
            #trayTitle { color: #f2f2f2; font-weight: 600; }
            #languageButton { color: #facc15; background: #333333; border: 1px solid #4a4a4a;
                              border-radius: 8px; font-weight: 700; padding: 0; }
            #languageButton:hover { background: #3d3d3d; }
            #trayLabel { color: #ececec; }
            #trayShortcut { color: #929292; font-size: 9px; }
            #trayDivider { color: #414141; margin: 4px 0; }
            #quitButton { color: #ececec; background: transparent; border: 0; border-radius: 7px;
                          min-height: 28px; text-align: left; padding-left: 8px; }
            #quitButton:hover { background: #3a3a3a; }
        ''')

    def _add_switch_row(self, layout):
        row = QWidget(self.panel)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 2, 2, 2)
        row_layout.setSpacing(8)
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

    def _toggle_language(self):
        self.set_language('en' if self._language == 'zh' else 'zh')
        self.language_toggled.emit(self._language)

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
        self.language_button.setText('EN' if self._language == 'zh' else '中')
        self.setToolTip('English' if self._language == 'zh' else '中文')

    def set_state(self, feedback_enabled, holding_enabled):
        for switch, checked in ((self.feedback_switch, feedback_enabled),
                                (self.holding_switch, holding_enabled)):
            switch.blockSignals(True)
            switch.setChecked(checked)
            switch.blockSignals(False)

    def show_near_cursor(self):
        self.adjustSize()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        available = screen.availableGeometry()
        cursor = QCursor.pos()
        x = max(available.left() + 6, min(cursor.x() - self.width() + 12,
                                          available.right() - self.width() - 6))
        y = cursor.y() - self.height() - 10
        if y < available.top() + 6:
            y = min(cursor.y() + 10, available.bottom() - self.height() - 6)
        self.move(x, y)
        self.show()
        self.raise_()
