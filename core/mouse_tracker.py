"""Active-only high-rate global cursor spring tracking."""

from PySide6.QtCore import QElapsedTimer, QObject, QTimer, Qt, Signal
from PySide6.QtGui import QCursor

from config import SPRING


class SpringAnimator:
    def __init__(self, stiffness: float = 500, damping: float = 40):
        self.stiffness = stiffness
        self.damping = damping
        self.current_x = self.current_y = 0.0
        self.target_x = self.target_y = 0.0
        self.velocity_x = self.velocity_y = 0.0
        self._target_moved_right = False

    def set_target(self, x: float, y: float):
        self._target_moved_right = x > self.target_x
        self.target_x, self.target_y = x, y

    def step(self, dt: float) -> tuple[float, float]:
        # Moving left keeps the spring lag (the content feels dragged behind).
        # Moving right is a direct push: the anchor keeps its fixed cursor
        # offset from the first rightward pixel instead of trailing behind.
        if self._target_moved_right:
            self.current_x = self.target_x
            self.velocity_x = 0.0
        else:
            force_x = (-self.stiffness * (self.current_x - self.target_x) -
                       self.damping * self.velocity_x)
            self.velocity_x += force_x * dt
            self.current_x += self.velocity_x * dt
        force_y = -self.stiffness * (self.current_y - self.target_y) - self.damping * self.velocity_y
        self.velocity_y += force_y * dt
        self.current_y += self.velocity_y * dt
        return self.current_x, self.current_y

    def reset(self, x: float, y: float):
        self.current_x = self.target_x = x
        self.current_y = self.target_y = y
        self.velocity_x = self.velocity_y = 0.0
        self._target_moved_right = False


class MouseTracker(QObject):
    """Track at 8ms while feedback is visible and stay idle otherwise."""

    position_changed = Signal(float, float)
    spring_position_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.spring = SpringAnimator(SPRING['stiffness'], SPRING['damping'])
        pos = QCursor.pos()
        self.spring.reset(pos.x(), pos.y())
        self._is_tracking = False
        self._clock = QElapsedTimer()
        self._last_tick_ns = None
        self._motion_timer = QTimer(self)
        self._motion_timer.setTimerType(Qt.PreciseTimer)
        self._motion_timer.setInterval(4)
        self._motion_timer.timeout.connect(self.advance)

    def start_tracking(self):
        pos = QCursor.pos()
        self.spring.reset(pos.x(), pos.y())
        self._clock.start()
        self._last_tick_ns = 0
        self._is_tracking = True
        self._motion_timer.start()

    def stop_tracking(self):
        self._is_tracking = False
        self._last_tick_ns = None
        self._motion_timer.stop()

    def advance(self):
        """Sample the cursor and integrate the spring using actual elapsed time."""
        if not self._is_tracking:
            return
        pos = QCursor.pos()
        self.spring.set_target(pos.x(), pos.y())
        self.position_changed.emit(pos.x(), pos.y())
        now_ns = self._clock.nsecsElapsed()
        if self._last_tick_ns is None:
            dt = 1 / 120
        else:
            dt = max(0.001, min((now_ns - self._last_tick_ns) / 1_000_000_000, 0.05))
        self._last_tick_ns = now_ns
        x, y = self.spring.step(dt)
        self.spring_position_changed.emit(x, y)

    def get_current_position(self) -> tuple[int, int]:
        pos = QCursor.pos()
        return pos.x(), pos.y()

    def get_spring_position(self) -> tuple[float, float]:
        return self.spring.current_x, self.spring.current_y
