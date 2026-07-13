"""
Dose Ctrl+C - 剪贴板复制反馈动画工具
主入口文件 - 系统托盘 + 全局监听 + 动画管理
"""

import sys
import keyboard
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt, QSettings

from config import COLORS, SIZES
from core.mouse_tracker import MouseTracker
from core.clipboard_monitor import ClipboardMonitor
from ui.feedback_widget import FeedbackWidget, FeedbackType
from ui.tray_menu import TrayMenuPopup


class ClipboardFXApp:
    """剪贴板反馈动画应用"""
    
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出
        self.app.setApplicationName("Dose Ctrl+C")
        self.app.setApplicationDisplayName("Dose Ctrl+C")
        self._set_windows_app_id()

        self._settings = QSettings('DoseCtrlC', 'DoseCtrlC')
        self.silent_mode = not self._settings.value('feedback_enabled', True, type=bool)
        self._holding_mode = self._settings.value('holding_enabled', False, type=bool)
        self._language = self._settings.value('tray_language', 'zh', type=str)
        
        # 创建系统托盘
        self._setup_tray()
        
        # 鼠标追踪器
        self.mouse_tracker = MouseTracker()
        self.mouse_tracker.spring_position_changed.connect(self._on_mouse_move)
        
        # 剪贴板监听器
        self.clipboard_monitor = ClipboardMonitor()
        self.clipboard_monitor.copy_rich.connect(self._on_copy_success)
        self.clipboard_monitor.copy_failed.connect(self._on_copy_failed)
        self.clipboard_monitor.paste_detected.connect(self._on_paste)
        self.clipboard_monitor.images_updated.connect(self._on_images_updated)

        # 当前活动的反馈窗口
        self._current_widget = None
        
        # 当前鼠标位置
        self._mouse_x = 0
        self._mouse_y = 0
        
        # 全局快捷键
        keyboard.add_hotkey('ctrl+shift+q', self._quit, suppress=False)
        keyboard.add_hotkey('ctrl+shift+m', self._toggle_silent_mode, suppress=False)
        keyboard.add_hotkey('ctrl+shift+h', self._toggle_holding_mode, suppress=False)
        
    def _setup_tray(self):
        """设置系统托盘"""
        # 创建托盘图标（简单的圆形图标）
        icon = self._create_tray_icon()
        
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("Dose Ctrl+C - 剪贴板反馈")
        
        # Native tray QMenu cannot reliably provide the requested rounded,
        # dark control surface, so use a small DPI-aware Qt.Popup instead.
        self.tray_menu = TrayMenuPopup(self._language)
        self.tray_menu.feedback_toggled.connect(self._set_feedback_enabled)
        self.tray_menu.holding_toggled.connect(self._set_holding_mode)
        self.tray_menu.language_toggled.connect(self._set_language)
        self.tray_menu.quit_requested.connect(self._quit)
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
                self.tray_menu.show_near_cursor()
        
    def _on_mouse_move(self, x: float, y: float):
        """鼠标移动回调"""
        self._mouse_x = x
        self._mouse_y = y
        
        # 更新当前反馈窗口位置
        if self._current_widget and self._current_widget._active:
            self._current_widget.move_to_position(x, y)
            
    def _on_copy_success(self, text: str, images=None, image_count: int = 0):
        """复制成功回调"""
        self._show_feedback(FeedbackType.COPY, text, images=images, image_count=image_count)

    def _on_images_updated(self, images, image_count: int):
        """异步图片到达回调（Bug 3: 延迟图片支持）"""
        if self._current_widget and self._current_widget._active:
            self._current_widget.update_images(images, image_count)
        
    def _on_copy_failed(self):
        """复制失败回调"""
        self._show_feedback(FeedbackType.ERROR)
        
    def _on_paste(self):
        """粘贴回调"""
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

        # 如果有正在进行的动画，先停止
        if self._current_widget:
            self._current_widget.stop()
            self._current_widget.deleteLater()

        # 创建新的反馈窗口（含 holding 模式和多图支持）
        is_holding = self._holding_mode and feedback_type == FeedbackType.COPY
        self._current_widget = FeedbackWidget(
            feedback_type, text,
            images=images,
            image_count=image_count,
            holding_mode=is_holding
        )
        self._current_widget.animation_complete.connect(self._on_animation_complete)
        self._current_widget.frame_tick.connect(self.mouse_tracker.advance)
        
        # 反馈出现时才开始追踪，空闲期不保留高频计时器。
        self.mouse_tracker.start_tracking()
        self._mouse_x, self._mouse_y = self.mouse_tracker.get_current_position()
        self._current_widget.move_to_position(self._mouse_x, self._mouse_y)
        
        # 开始动画
        self._current_widget.start_animation()
        
    def _on_animation_complete(self):
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
        self._settings.setValue('feedback_enabled', not self.silent_mode)
        if self.silent_mode and self._current_widget:
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
            f'Dose Ctrl+C\n复制反馈：{feedback_text}\n等待 Ctrl+V：{holding_text}')
        self.tray_menu.set_state(not self.silent_mode, self._holding_mode)

    def _set_language(self, language: str):
        self._language = language if language in ('zh', 'en') else 'zh'
        self._settings.setValue('tray_language', self._language)
        self.tray_menu.set_language(self._language)

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
        """退出应用"""
        keyboard.unhook_all_hotkeys()  # 先移除所有热键，避免重复触发
        self.mouse_tracker.stop_tracking()
        self.clipboard_monitor.stop_monitoring()
        self.tray.hide()
        self.app.quit()


def main():
    """主函数"""
    app = ClipboardFXApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
