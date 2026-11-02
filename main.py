"""
Does CtrlC Work - 剪贴板复制反馈动画工具
主入口文件 - 系统托盘 + 全局监听 + 动画管理
"""

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import keyboard
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt, QSettings, QObject, Signal, Slot, QStandardPaths, QLockFile, QTimer
from app_version import APP_VERSION

from config import COLORS, SIZES
from core.cursor_metrics import CursorMetrics
from core.mouse_tracker import MouseTracker
from core.clipboard_monitor import ClipboardMonitor
from ui.feedback_widget import FeedbackWidget, FeedbackType
from ui.image_layout import normalize_image_layout
from ui.tray_menu import create_tray_menu
from ui.theme import ThemeController
from ui.text_style import TextStyleResolver


def _configure_logging():
    log_dir = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'dose-ctrlc.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        handlers=[RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024,
                                     backupCount=2, encoding='utf-8'), logging.StreamHandler()],
    )
    logging.getLogger(__name__).info('logging initialized path=%s', log_path)


class _NavigationBridge(QObject):
    """Move keyboard-hook callbacks onto Qt's GUI thread."""

    requested = Signal(str)

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self.requested.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)

    @Slot(str)
    def _dispatch(self, command):
        self._callback(command)


class ClipboardFXApp:
    """剪贴板反馈动画应用"""
    
    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出
        self.app.setApplicationName("Does CtrlC Work")
        self.app.setApplicationDisplayName("Does CtrlC Work")
        self.app.setOrganizationName('DoseCtrlC')
        self.app.setApplicationVersion(APP_VERSION)
        _configure_logging()
        self._instance_lock = QLockFile(os.path.join(
            QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation), 'instance.lock'))
        self._instance_lock.setStaleLockTime(0)
        if not self._instance_lock.tryLock(0):
            raise RuntimeError('Dose CtrlC is already running, or its instance lock is unavailable.')
        self._quitting = False
        self._settings = QSettings('DoseCtrlC', 'DoseCtrlC')
        self._content_font_latin = self._settings.value(
            'content_font_latin', '', type=str)
        self._content_font_cjk = self._settings.value(
            'content_font_cjk', '', type=str)
        TextStyleResolver.set_content_fonts(
            self._content_font_latin, self._content_font_cjk)
        self.theme_controller = ThemeController(self._settings, self.app)
        self.theme_controller.theme_changed.connect(self._on_theme_changed)
        self._set_windows_app_id()
        self.silent_mode = not self._settings.value('feedback_enabled', True, type=bool)
        self._holding_mode = self._settings.value('holding_enabled', False, type=bool)
        self._language = self._settings.value('tray_language', 'zh', type=str)
        self._image_layout_mode = normalize_image_layout(
            self._settings.value('image_layout_mode', 'fan', type=str))
        
        # 创建系统托盘
        self._setup_tray()
        
        # 鼠标追踪器
        self.mouse_tracker = MouseTracker()
        self.mouse_tracker.spring_position_changed.connect(self._on_mouse_move)
        
        # 剪贴板监听器
        self.clipboard_monitor = ClipboardMonitor(remote_previews='--remote-previews' in sys.argv)
        self.clipboard_monitor.copy_session.connect(self._on_copy_session)
        self.clipboard_monitor.copy_failed.connect(self._on_copy_failed)
        self.clipboard_monitor.paste_detected.connect(self._on_paste)
        self.clipboard_monitor.images_for_session.connect(self._on_session_images)

        # 当前活动的反馈窗口
        self._current_widget = None
        self._feedback_session_id = None
        self._navigation_hotkeys = []
        self._navigation_bridge = _NavigationBridge(self._on_text_navigation_requested, self.app)
        self._command_bridge = _NavigationBridge(self._dispatch_command, self.app)
        
        # 当前鼠标位置
        self._mouse_x = 0
        self._mouse_y = 0
        
        # 全局快捷键
        self._command_hotkeys = []
        for shortcut, command in (('ctrl+shift+q', 'quit'),
                                  ('ctrl+shift+m', 'silent'), ('ctrl+shift+h', 'holding')):
            try:
                self._command_hotkeys.append(keyboard.add_hotkey(
                    shortcut, lambda value=command: self._command_bridge.requested.emit(value),
                    suppress=False))
            except Exception:
                logging.getLogger(__name__).warning('Hotkey unavailable: %s', shortcut, exc_info=True)

    def _dispatch_command(self, command):
        if getattr(self, '_quitting', False):
            return
        handler = {'quit': self._quit, 'silent': self._toggle_silent_mode,
                   'holding': self._toggle_holding_mode}.get(command)
        if handler:
            handler()
        
    def _setup_tray(self):
        """设置系统托盘"""
        # 创建托盘图标（简单的圆形图标）
        icon = self._create_tray_icon()
        
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("Does CtrlC Work - 剪贴板反馈")
        
        # Windows uses an owner-drawn HMENU for the real system menu loop;
        # other platforms retain the compact QWidgetAction QMenu.
        self.tray_menu = create_tray_menu(self._language)
        self.tray_menu.feedback_toggled.connect(self._set_feedback_enabled)
        self.tray_menu.holding_toggled.connect(self._set_holding_mode)
        self.tray_menu.language_toggled.connect(self._set_language)
        self.tray_menu.image_layout_changed.connect(self._set_image_layout_mode)
        self.tray_menu.palette_changed.connect(self._set_palette)
        self.tray_menu.color_target_changed.connect(self._set_color_target)
        self.tray_menu.color_overrides_reset.connect(self._reset_color_overrides)
        self.tray_menu.font_target_changed.connect(self._set_content_font)
        self.tray_menu.quit_requested.connect(self._quit)
        if hasattr(self, 'theme_controller'):
            self.tray_menu.set_palette(self.theme_controller.palette,
                                       self.theme_controller.custom_color,
                                       self.theme_controller.color_overrides)
        self.tray_menu.set_content_fonts(
            getattr(self, '_content_font_latin', ''),
            getattr(self, '_content_font_cjk', ''))
        # Do not use QSystemTrayIcon's automatic context-menu path: on Windows
        # it activates the Qt top-level popup and retracts Explorer's hidden-
        # icons flyout immediately. Both mouse entries are handled below.
        self.tray.setContextMenu(None)
        self.tray.activated.connect(self._on_tray_activated)
        self._update_tray_status()
        
    def _create_tray_icon(self) -> QIcon:
        """创建托盘图标"""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制黄色圆点
        painter.setBrush(QColor(COLORS['dot_copy']))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        
        painter.end()
        return QIcon(pixmap)
        
    def _on_tray_activated(self, reason):
        """Show the compact popup for the normal tray interactions."""
        if reason in (QSystemTrayIcon.ActivationReason.Context,
                      QSystemTrayIcon.ActivationReason.Trigger):
            if self.tray_menu.isVisible():
                self.tray_menu.hide()
            else:
                self.tray_menu.show_near_tray(self.tray)
        
    def _on_mouse_move(self, x: float, y: float):
        """鼠标移动回调"""
        self._mouse_x = x
        self._mouse_y = y
        
        # 更新当前反馈窗口位置
        if self._current_widget and self._current_widget._active:
            self._current_widget.move_to_position(x, y)
            
    def _set_palette(self, palette: str, custom_color: str = ''):
        self.theme_controller.set_palette(palette, custom_color or None)
        self.tray_menu.set_palette(self.theme_controller.palette,
                                   self.theme_controller.custom_color,
                                   self.theme_controller.color_overrides)

    def _set_color_target(self, target: str, color: str):
        self.theme_controller.set_color_override(target, color)
        self.tray_menu.set_palette(self.theme_controller.palette,
                                   self.theme_controller.custom_color,
                                   self.theme_controller.color_overrides)

    def _reset_color_overrides(self):
        self.theme_controller.reset_color_overrides()
        self.tray_menu.set_palette(self.theme_controller.palette,
                                   self.theme_controller.custom_color,
                                   self.theme_controller.color_overrides)

    def _set_content_font(self, target: str, family: str):
        if target not in ('latin', 'cjk') or not family:
            return
        if target == 'latin':
            self._content_font_latin = family
            self._settings.setValue('content_font_latin', family)
        else:
            self._content_font_cjk = family
            self._settings.setValue('content_font_cjk', family)
        TextStyleResolver.set_content_fonts(
            self._content_font_latin, self._content_font_cjk)
        self.tray_menu.set_content_fonts(self._content_font_latin,
                                         self._content_font_cjk)

    def _on_theme_changed(self, palette: str):
        """Refresh custom-painted surfaces after an in-app palette change."""
        self.tray_menu.set_theme(palette)
        if self._current_widget:
            self._current_widget.update()

    def _on_copy_success(self, text: str, images=None, image_count: int = 0):
        """复制成功回调"""
        self._show_feedback(FeedbackType.COPY, text, images=images, image_count=image_count)

    def _on_copy_session(self, session_id, text, images, image_count):
        self._on_copy_success(text, images, image_count)
        self._feedback_session_id = session_id if self._current_widget else None

    def _on_session_images(self, session_id, images, image_count):
        if session_id == getattr(self, '_feedback_session_id', None):
            self._on_images_updated(images, image_count)

    def _on_text_navigation_requested(self, direction: str):
        if self._current_widget and self._current_widget._active:
            self._current_widget.navigate_text(direction)

    def _set_text_navigation_enabled(self, enabled: bool):
        if enabled:
            self._register_navigation_hotkeys()
        else:
            self._remove_navigation_hotkeys()

    def _register_navigation_hotkeys(self):
        if self._navigation_hotkeys:
            return
        for direction in ('left', 'right', 'up', 'down'):
            try:
                handle = keyboard.add_hotkey(
                    'ctrl+alt+' + direction,
                    lambda key=direction: self._navigation_bridge.requested.emit(key),
                    suppress=sys.platform.startswith('win'), trigger_on_release=False)
                self._navigation_hotkeys.append(handle)
            except Exception:
                logging.getLogger(__name__).warning('Text navigation hotkey unavailable', exc_info=True)
                self._remove_navigation_hotkeys()
                break

    def _remove_navigation_hotkeys(self):
        for handle in getattr(self, '_navigation_hotkeys', []):
            try:
                keyboard.remove_hotkey(handle)
            except (KeyError, ValueError):
                pass
        self._navigation_hotkeys = []

    def _on_images_updated(self, images, image_count: int):
        """异步图片到达回调（Bug 3: 延迟图片支持）"""
        if (self._current_widget and self._current_widget._active and
                self._current_widget._feedback_type == FeedbackType.COPY):
            self._current_widget.update_images(images, image_count)
        
    def _on_copy_failed(self):
        """复制失败回调"""
        self._show_feedback(FeedbackType.ERROR)
        
    def _on_paste(self):
        """粘贴回调"""
        self._feedback_session_id = None
        # Ctrl+V only dismisses the copy feedback that explicitly opted into
        # holding. Ordinary copy feedback must still be replaced by the green
        # paste confirmation.
        if (self._current_widget and self._current_widget._active and
                self._current_widget.is_holding_copy):
            self._current_widget.start_exit()
            return

        self._show_feedback(FeedbackType.PASTE)
        
    def _show_feedback(self, feedback_type: FeedbackType, text: str = "",
                       images=None, image_count: int = 0):
        """显示反馈动画"""
        if self.silent_mode:
            return

        self._feedback_session_id = None

        # 如果有正在进行的动画，先停止
        if self._current_widget:
            self._remove_navigation_hotkeys()
            self._current_widget.stop()
            self._current_widget.deleteLater()

        # 创建新的反馈窗口（含 holding 模式和多图支持）
        is_holding = self._holding_mode and feedback_type == FeedbackType.COPY
        cursor_metrics = CursorMetrics.detect()
        self._current_widget = FeedbackWidget(
            feedback_type, text,
            images=images,
            image_count=image_count,
            holding_mode=is_holding,
            ui_scale=cursor_metrics.ui_scale,
            cursor_offset=(cursor_metrics.offset_x, cursor_metrics.offset_y),
            image_layout_mode=getattr(self, '_image_layout_mode', 'fan'),
        )
        self._current_widget.animation_complete.connect(self._on_animation_complete)
        self._current_widget.navigation_active_changed.connect(
            self._set_text_navigation_enabled)
        
        # 反馈出现时才开始追踪，空闲期不保留高频计时器。
        self.mouse_tracker.start_tracking()
        self._mouse_x, self._mouse_y = self.mouse_tracker.get_current_position()
        self._current_widget.move_to_position(self._mouse_x, self._mouse_y)
        
        # 开始动画
        self._current_widget.start_animation()
        # The entry state has now emitted its initial inactive signal. Register
        # immediately afterwards so the first copied text does not wait for a
        # later state transition before its arrow-key listener exists.
        self._set_text_navigation_enabled(
            self._current_widget.can_navigate_text)
        
    def _on_animation_complete(self):
        self._feedback_session_id = None
        self._remove_navigation_hotkeys()
        """动画完成回调"""
        if self._current_widget:
            self._current_widget.deleteLater()
            self._current_widget = None
        self.mouse_tracker.stop_tracking()
            
    def _toggle_holding_mode(self):
        self._set_holding_mode(not self._holding_mode)

    def _set_holding_mode(self, enabled: bool):
        """Set the explicit Ctrl+V-dismiss behaviour for future copy feedback."""
        self._holding_mode = bool(enabled)
        self._settings.setValue('holding_enabled', self._holding_mode)
        if (not self._holding_mode and self._current_widget and
                self._current_widget._active and self._current_widget.is_holding_copy):
            self._current_widget.start_exit()
        self._update_tray_status()

    def _toggle_silent_mode(self):
        self._set_feedback_enabled(self.silent_mode)

    def _set_feedback_enabled(self, enabled: bool):
        """Enable or suppress visual feedback while keeping clipboard monitoring alive."""
        self.silent_mode = not bool(enabled)
        if self.silent_mode:
            self._feedback_session_id = None
        self._settings.setValue('feedback_enabled', not self.silent_mode)
        if self.silent_mode and self._current_widget:
            self._remove_navigation_hotkeys()
            self._current_widget.stop()
            self._current_widget.deleteLater()
            self._current_widget = None
            self.mouse_tracker.stop_tracking()
        self._update_tray_status()

    def _update_tray_status(self):
        """更新托盘状态显示"""
        feedback_text = '开' if not self.silent_mode else '关'
        holding_text = '开' if self._holding_mode else '关'
        self.tray.setToolTip(
            f'Does CtrlC Work\n复制反馈：{feedback_text}\n等待 Ctrl+V：{holding_text}')
        self.tray_menu.set_state(
            not self.silent_mode, self._holding_mode,
            getattr(self, '_image_layout_mode', 'fan'))

    def _set_language(self, language: str):
        self._language = language if language in ('zh', 'en') else 'zh'
        self._settings.setValue('tray_language', self._language)
        self.tray_menu.set_language(self._language)

    def _set_image_layout_mode(self, mode: str):
        """Persist the layout used by future copy-feedback instances."""
        self._image_layout_mode = normalize_image_layout(mode)
        self._settings.setValue('image_layout_mode', self._image_layout_mode)
        self._update_tray_status()

    def _set_windows_app_id(self):
        """设置 Windows 任务栏显示标识"""
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DoseCtrlC.App")
        except Exception:
            pass

    def run(self):
        """运行应用"""
        # 显示托盘图标
        self.tray.show()
        
        # 启动剪贴板监听
        self.clipboard_monitor.start_monitoring()
        
        # 运行事件循环
        return self.app.exec()
        
    def _quit(self):
        if getattr(self, '_quitting', False):
            return
        self._quitting = True
        self._feedback_session_id = None
        self._remove_navigation_hotkeys()
        """退出应用"""
        for handle in getattr(self, '_command_hotkeys', []):
            try:
                keyboard.remove_hotkey(handle)
            except (KeyError, ValueError):
                pass
        self._command_hotkeys = []
        self.mouse_tracker.stop_tracking()
        finished = self.clipboard_monitor.stop_monitoring()
        if self._current_widget:
            self._current_widget.stop()
        if finished:
            self.tray.hide()
            self.app.quit()
        else:
            self.tray.setToolTip('Does CtrlC Work — 正在等待预览任务退出')
            QTimer.singleShot(50, self._finish_quit)

    def _finish_quit(self):
        if self.clipboard_monitor.shutdown_preview(wait_ms=0):
            self.tray.hide()
            self.app.quit()
        else:
            QTimer.singleShot(50, self._finish_quit)


def main():
    """主函数"""
    try:
        app = ClipboardFXApp()
    except RuntimeError as error:
        logging.getLogger(__name__).error('%s', error)
        return 1
    sys.exit(app.run())


if __name__ == "__main__":
    sys.exit(main())
