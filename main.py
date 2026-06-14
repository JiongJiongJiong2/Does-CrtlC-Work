"""
Dose Ctrl+C - 剪贴板复制反馈动画工具
主入口文件 - 系统托盘 + 全局监听 + 动画管理
"""

import sys
import keyboard
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor
from PySide6.QtCore import QTimer, Qt

from config import COLORS, SIZES
from core.mouse_tracker import MouseTracker
from core.clipboard_monitor import ClipboardMonitor
from ui.feedback_widget import FeedbackWidget, FeedbackType


class ClipboardFXApp:
    """剪贴板反馈动画应用"""
    
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出
        self.app.setApplicationName("Dose Ctrl+C")
        self.app.setApplicationDisplayName("Dose Ctrl+C")
        self._set_windows_app_id()

        self.silent_mode = False
        
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

        # 是否启用 holding 模式（复制后持留到粘贴才退场）
        self._holding_mode = True
        
        # 当前活动的反馈窗口
        self._current_widget = None
        
        # 当前鼠标位置
        self._mouse_x = 0
        self._mouse_y = 0
        
        # 全局快捷键
        keyboard.add_hotkey('ctrl+shift+q', self._quit, suppress=False)
        keyboard.add_hotkey('ctrl+shift+m', self._toggle_silent_mode, suppress=False)
        
    def _setup_tray(self):
        """设置系统托盘"""
        # 创建托盘图标（简单的圆形图标）
        icon = self._create_tray_icon()
        
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("Dose Ctrl+C - 剪贴板反馈")
        
        # 托盘菜单
        menu = QMenu()
        
        # 显示状态
        self.status_action = QAction("状态: 运行中（提示开启）", menu)
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)

        # 切换静默模式
        self.toggle_silent_action = QAction("切换静默模式 (Ctrl+Shift+M)", menu)
        self.toggle_silent_action.triggered.connect(self._toggle_silent_mode)
        menu.addAction(self.toggle_silent_action)

        menu.addSeparator()

        # 退出
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        
        self.tray.setContextMenu(menu)
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
        """托盘图标被点击"""
        pass  # 可以添加双击显示设置等功能
        
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
        
    def _on_copy_failed(self):
        """复制失败回调"""
        self._show_feedback(FeedbackType.ERROR)
        
    def _on_paste(self):
        """粘贴回调"""
        # 如果当前有 holding 状态的复制动画，触发退场
        if self._current_widget and self._current_widget._active:
            if hasattr(self._current_widget, 'start_exit'):
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
        
        # 设置初始位置
        self._current_widget.move_to_position(self._mouse_x, self._mouse_y)
        
        # 开始动画
        self._current_widget.start_animation()
        
    def _on_animation_complete(self):
        """动画完成回调"""
        if self._current_widget:
            self._current_widget.deleteLater()
            self._current_widget = None
            
    def _toggle_silent_mode(self):
        """切换静默模式"""
        self.silent_mode = not self.silent_mode
        if self.silent_mode and self._current_widget:
            self._current_widget.stop()
            self._current_widget.deleteLater()
            self._current_widget = None
        self._update_tray_status()

    def _update_tray_status(self):
        """更新托盘状态显示"""
        if self.silent_mode:
            self.status_action.setText("状态: 运行中（静默）")
            self.tray.setToolTip("Dose Ctrl+C - 静默运行中")
        else:
            self.status_action.setText("状态: 运行中（提示开启）")
            self.tray.setToolTip("Dose Ctrl+C - 剪贴板反馈")

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
        
        # 启动鼠标追踪
        self.mouse_tracker.start_tracking()
        
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