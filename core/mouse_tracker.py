"""由 FeedbackWidget 的单一帧时钟驱动的全局鼠标 spring 跟随。"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QCursor

from config import SPRING


class SpringAnimator:
    def __init__(self, stiffness: float = 500, damping: float = 40):
        self.stiffness = stiffness
        self.damping = damping
        self.current_x = self.current_y = 0.0
        self.target_x = self.target_y = 0.0
        self.velocity_x = self.velocity_y = 0.0

    def set_target(self, x: float, y: float):
        self.target_x, self.target_y = x, y

    def step(self, dt: float) -> tuple[float, float]:
        force_x = -self.stiffness * (self.current_x - self.target_x) - self.damping * self.velocity_x
        force_y = -self.stiffness * (self.current_y - self.target_y) - self.damping * self.velocity_y
        self.velocity_x += force_x * dt
        self.velocity_y += force_y * dt
        self.current_x += self.velocity_x * dt
        self.current_y += self.velocity_y * dt
        return self.current_x, self.current_y

    def reset(self, x: float, y: float):
        self.current_x = self.target_x = x
        self.current_y = self.target_y = y
        self.velocity_x = self.velocity_y = 0.0


class MouseTracker(QObject):
    """无内部定时器；仅在反馈窗口激活时由其 ``frame_tick`` 推进。"""

    position_changed = Signal(float, float)
    spring_position_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.spring = SpringAnimator(SPRING['stiffness'], SPRING['damping'])
        pos = QCursor.pos()
        self.spring.reset(pos.x(), pos.y())
        self._is_tracking = False
        self._last_frame_ms = None

    def start_tracking(self):
        pos = QCursor.pos()
        self.spring.reset(pos.x(), pos.y())
        self._last_frame_ms = None
        self._is_tracking = True

    def stop_tracking(self):
        self._is_tracking = False
        self._last_frame_ms = None

    def advance(self, frame_ms: float):
        """由 FeedbackWidget 的 PropertyEngine 每帧调用。"""
        if not self._is_tracking:
            return
        pos = QCursor.pos()
        self.spring.set_target(pos.x(), pos.y())
        self.position_changed.emit(pos.x(), pos.y())
        if self._last_frame_ms is None:
            dt = 1 / 60
        else:
            dt = max(0.001, min((frame_ms - self._last_frame_ms) / 1000.0, 0.05))
        self._last_frame_ms = frame_ms
        x, y = self.spring.step(dt)
        self.spring_position_changed.emit(x, y)

    def get_current_position(self) -> tuple[int, int]:
        pos = QCursor.pos()
        return pos.x(), pos.y()

    def get_spring_position(self) -> tuple[float, float]:
        return self.spring.current_x, self.spring.current_y
