"""
鼠标追踪器 - 获取全局鼠标位置并提供 Spring 物理缓动
"""

from PySide6.QtCore import QObject, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QCursor
import math

from config import SPRING


class SpringAnimator:
    """Spring 物理缓动动画器 - 模拟 Framer Motion 的 spring 效果"""
    
    def __init__(self, stiffness: float = 500, damping: float = 40):
        self.stiffness = stiffness
        self.damping = damping
        self.current_x = 0.0
        self.current_y = 0.0
        self.target_x = 0.0
        self.target_y = 0.0
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        
    def set_target(self, x: float, y: float):
        """设置目标位置"""
        self.target_x = x
        self.target_y = y
        
    def step(self, dt: float) -> tuple[float, float]:
        """执行一步动画，返回当前位置"""
        # Spring physics: F = -k * (x - target) - c * v
        # k = stiffness, c = damping
        
        # X 方向
        force_x = -self.stiffness * (self.current_x - self.target_x) - self.damping * self.velocity_x
        self.velocity_x += force_x * dt
        self.current_x += self.velocity_x * dt
        
        # Y 方向
        force_y = -self.stiffness * (self.current_y - self.target_y) - self.damping * self.velocity_y
        self.velocity_y += force_y * dt
        self.current_y += self.velocity_y * dt
        
        return self.current_x, self.current_y
    
    def is_settled(self, threshold: float = 0.5) -> bool:
        """检查是否已稳定"""
        dx = abs(self.current_x - self.target_x)
        dy = abs(self.current_y - self.target_y)
        v = abs(self.velocity_x) + abs(self.velocity_y)
        return dx < threshold and dy < threshold and v < threshold
    
    def reset(self, x: float, y: float):
        """重置到指定位置"""
        self.current_x = x
        self.current_y = y
        self.target_x = x
        self.target_y = y
        self.velocity_x = 0.0
        self.velocity_y = 0.0


class MouseTracker(QObject):
    """鼠标追踪器 - 跟踪全局鼠标位置并提供 Spring 缓动"""
    
    position_changed = Signal(float, float)  # 实际鼠标位置
    spring_position_changed = Signal(float, float)  # Spring 缓动后的位置
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.spring = SpringAnimator(
            stiffness=SPRING['stiffness'],
            damping=SPRING['damping']
        )
        
        # 初始化鼠标位置
        pos = QCursor.pos()
        self.spring.reset(pos.x(), pos.y())
        
        # 更新定时器 (60fps)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_spring)
        self.update_timer.setInterval(16)  # ~60fps
        
        # 鼠标轮询定时器
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_mouse_position)
        self.poll_timer.setInterval(8)  # ~120fps 轮询鼠标位置
        
        self._is_tracking = False
        
    def start_tracking(self):
        """开始追踪鼠标"""
        if not self._is_tracking:
            self._is_tracking = True
            # 初始化位置
            pos = QCursor.pos()
            self.spring.reset(pos.x(), pos.y())
            self.poll_timer.start()
            self.update_timer.start()
            
    def stop_tracking(self):
        """停止追踪鼠标"""
        self._is_tracking = False
        self.poll_timer.stop()
        self.update_timer.stop()
        
    def _poll_mouse_position(self):
        """轮询鼠标位置"""
        pos = QCursor.pos()
        self.spring.set_target(pos.x(), pos.y())
        self.position_changed.emit(pos.x(), pos.y())
        
    def _update_spring(self):
        """更新 Spring 动画"""
        # dt = 16ms = 0.016s，但为了更平滑，使用实际时间间隔
        dt = 0.016
        x, y = self.spring.step(dt)
        self.spring_position_changed.emit(x, y)
        
    def get_current_position(self) -> tuple[int, int]:
        """获取当前鼠标位置"""
        pos = QCursor.pos()
        return pos.x(), pos.y()
    
    def get_spring_position(self) -> tuple[float, float]:
        """获取 Spring 缓动后的位置"""
        return self.spring.current_x, self.spring.current_y