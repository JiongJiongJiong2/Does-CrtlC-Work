"""
剪贴板监听器 - 监听 Ctrl+C 复制操作并获取复制的文本
修复：keyboard 库在后台线程回调，需通过 Qt Signal 桥接到主线程
"""

from PySide6.QtCore import QObject, Signal, QTimer
import keyboard
import pyperclip

from config import MAX_TEXT_LENGTH


class ClipboardMonitor(QObject):
    """剪贴板监听器 - 监听全局 Ctrl+C 操作"""
    
    # 公开信号
    copy_success = Signal(str)      # 复制成功，携带文本
    copy_failed = Signal()          # 复制失败（无选中内容）
    paste_detected = Signal()       # 检测到粘贴
    
    # 内部信号 - 用于从 keyboard 后台线程安全地通知 Qt 主线程
    _ctrl_c_triggered = Signal()
    _ctrl_v_triggered = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_clipboard_text = ""
        self._is_monitoring = False
        
        # 延迟检查定时器（在主线程中创建和使用）
        self._check_timer = QTimer(self)
        self._check_timer.setSingleShot(True)
        self._check_timer.timeout.connect(self._check_copy_result)
        
        # 连接内部信号到主线程处理槽
        self._ctrl_c_triggered.connect(self._handle_ctrl_c_on_main_thread)
        self._ctrl_v_triggered.connect(self._handle_ctrl_v_on_main_thread)
        
    def start_monitoring(self):
        """开始监听剪贴板"""
        if not self._is_monitoring:
            self._is_monitoring = True
            
            # 保存当前剪贴板内容
            try:
                self._last_clipboard_text = pyperclip.paste() or ""
            except Exception:
                self._last_clipboard_text = ""
            
            # 使用 add_hotkey 注册快捷键
            # 回调会在 keyboard 的后台线程中执行，只发 Signal 不操作 QTimer
            keyboard.add_hotkey('ctrl+c', self._on_ctrl_c_detected, suppress=False)
            keyboard.add_hotkey('ctrl+v', self._on_ctrl_v_detected, suppress=False)
            
    def stop_monitoring(self):
        """停止监听"""
        if self._is_monitoring:
            self._is_monitoring = False
            keyboard.unhook_all_hotkeys()
            
    # ---- keyboard 后台线程回调（仅发 Signal，不操作任何 QTimer/QObject）----
    
    def _on_ctrl_c_detected(self):
        """Ctrl+C 被按下 - 在 keyboard 后台线程中调用"""
        # 仅通过 Signal 通知主线程，Signal.emit() 是线程安全的
        self._ctrl_c_triggered.emit()
        
    def _on_ctrl_v_detected(self):
        """Ctrl+V 被按下 - 在 keyboard 后台线程中调用"""
        self._ctrl_v_triggered.emit()
        
    # ---- Qt 主线程处理（安全操作 QTimer 和其他 QObject）----
    
    def _handle_ctrl_c_on_main_thread(self):
        """在 Qt 主线程中处理 Ctrl+C"""
        # 延迟检查复制结果（等待系统完成复制操作）
        self._check_timer.start(50)
        
    def _handle_ctrl_v_on_main_thread(self):
        """在 Qt 主线程中处理 Ctrl+V"""
        self.paste_detected.emit()
        
    def _check_copy_result(self):
        """检查复制结果"""
        try:
            current_text = pyperclip.paste()
            
            if current_text and current_text != self._last_clipboard_text:
                # 复制成功，有新内容
                self._last_clipboard_text = current_text
                # 截断文本
                display_text = self._truncate_text(current_text)
                self.copy_success.emit(display_text)
            else:
                # 复制失败，剪贴板内容未变化
                self.copy_failed.emit()
                
        except Exception:
            # 发生错误，视为复制失败
            self.copy_failed.emit()
            
    def _truncate_text(self, text: str) -> str:
        """截断文本用于显示"""
        # 替换换行符为空格
        clean_text = text.replace('\n', ' ').replace('\r', ' ')
        # 截断
        if len(clean_text) > MAX_TEXT_LENGTH:
            return clean_text[:MAX_TEXT_LENGTH] + '...'
        return clean_text
    
    def get_clipboard_text(self) -> str:
        """获取当前剪贴板文本"""
        try:
            return pyperclip.paste() or ""
        except Exception:
            return ""