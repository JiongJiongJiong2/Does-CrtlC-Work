"""
ScrambleText - 赛博朋克 Unicode 块字符解码特效
使用 QTimer 逐帧更新，模拟从左到右的"扫描/解码"揭示效果
"""

import random
import time
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import QWidget

from config import BLOCK_CHARS, SCRAMBLE_CHARS, COLORS, SIZES


class ScrambleText(QWidget):
    """Unicode 块字符解码特效组件"""
    
    def __init__(self, text: str, duration: int = 1000, parent=None):
        super().__init__(parent)
        self._target_text = text
        self._duration = duration  # 毫秒
        self._display_text = ""
        self._start_time = 0.0
        self._is_running = False
        self._is_complete = False
        
        # 设置字体 - 等宽字体
        self._font = QFont("Consolas", 10)
        self._font.setStyleHint(QFont.Monospace)
        self._font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        
        # 计算尺寸
        self._calculate_size()
        
        # 动画定时器
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(16)  # ~60fps
        
    def _calculate_size(self):
        """根据文本计算组件尺寸"""
        fm = QFontMetrics(self._font)
        # 使用目标文本计算最大宽度
        text_width = fm.horizontalAdvance(self._target_text) + 24  # padding
        text_height = fm.height() + 8  # 上下各4px padding
        self.setFixedSize(
            max(int(text_width), SIZES['box_min_width'] - SIZES['box_padding']),
            text_height
        )
        
    def start(self):
        """开始解码动画"""
        self._start_time = time.time() * 1000  # 转为毫秒
        self._is_running = True
        self._is_complete = False
        self._timer.start()
        
    def stop(self):
        """停止动画"""
        self._timer.stop()
        self._is_running = False
        
    def is_complete(self) -> bool:
        """动画是否完成"""
        return self._is_complete
        
    def _tick(self):
        """逐帧更新"""
        now = time.time() * 1000
        elapsed = now - self._start_time
        progress = min(elapsed / self._duration, 1.0)
        
        # 计算已解码的字符数
        text_len = len(self._target_text)
        solved_count = int(progress * text_len)
        
        current = []
        for i in range(text_len):
            if i < solved_count:
                # 已解码区域 - 显示真实字符
                current.append(self._target_text[i])
            elif i < solved_count + 4:
                # 解码前沿 - 密集块字符
                current.append(random.choice(BLOCK_CHARS))
            elif random.random() < 0.6:
                # 动态乱码区域
                current.append(random.choice(SCRAMBLE_CHARS))
            else:
                # 轻像素/点
                current.append(random.choice(BLOCK_CHARS[2:6]))  # 偏向较浅的块
                
        self._display_text = ''.join(current)
        self.update()  # 触发重绘
        
        if progress >= 1.0:
            self._display_text = self._target_text
            self._is_complete = True
            self._is_running = False
            self._timer.stop()
            self.update()
            
    def paintEvent(self, event):
        """绘制文本"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 设置字体
        painter.setFont(self._font)
        
        # 文字颜色
        painter.setPen(QColor(COLORS['text']))
        
        # 绘制文本 - 垂直居中
        fm = QFontMetrics(self._font)
        y = (self.height() + fm.ascent() - fm.descent()) // 2
        painter.drawText(12, y, self._display_text)
        
        painter.end()