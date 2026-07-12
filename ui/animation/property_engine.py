"""单调时钟驱动的属性动画与逐帧效果引擎。"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Set

from PySide6.QtCore import QElapsedTimer, QObject, QEasingCurve, QTimer, Qt, Signal


@dataclass
class AnimDescriptor:
    """单个属性动画的描述符。"""

    start: float
    end: float
    duration: int
    easing: QEasingCurve
    start_time: float
    current: float
    on_finished: Optional[Callable] = field(default=None, repr=False)


class PropertyEngine(QObject):
    """FeedbackWidget 唯一的活动期帧时钟。

    属性插值、文字解码、图片 reveal、堆叠动画和鼠标追踪都由同一
    ``tick`` 信号驱动。``set_frame_active`` 用于保持展示期的时钟运行，
    即使此时没有正在插值的属性。
    """

    tick = Signal()
    finished = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._on_tick)
        self._clock = QElapsedTimer()
        self._clock.start()
        self._active_anims: Dict[str, AnimDescriptor] = {}
        self._frame_clients: Set[str] = set()
        self._now_ms = 0.0

    @property
    def now_ms(self) -> float:
        """本帧的单调时间戳（毫秒）。"""
        return self._now_ms

    def set_frame_active(self, client: str, active: bool) -> None:
        """声明一个需要逐帧更新的生命周期客户端。"""
        if active:
            self._frame_clients.add(client)
            self._ensure_running()
        else:
            self._frame_clients.discard(client)
            self._stop_if_idle()

    def animate(self, prop: str, start: float, end: float,
                duration: int, easing: QEasingCurve = None,
                on_finished: Callable = None) -> None:
        """启动或替换一个属性动画。"""
        self._now_ms = float(self._clock.elapsed())
        self._active_anims[prop] = AnimDescriptor(
            start=start,
            end=end,
            duration=duration,
            easing=easing or QEasingCurve(QEasingCurve.Linear),
            start_time=self._now_ms,
            current=start,
            on_finished=on_finished,
        )
        self._ensure_running()

    def cancel(self, prop: str) -> None:
        self._active_anims.pop(prop, None)
        self._stop_if_idle()

    def cancel_all(self) -> None:
        self._active_anims.clear()
        self._stop_if_idle()

    def get_value(self, prop: str, default: float = 0.0) -> float:
        desc = self._active_anims.get(prop)
        return desc.current if desc else default

    def has_active(self, prop: str) -> bool:
        return prop in self._active_anims

    def has_any_active(self) -> bool:
        return bool(self._active_anims)

    def _ensure_running(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def _stop_if_idle(self) -> None:
        if not self._active_anims and not self._frame_clients and self._timer.isActive():
            self._timer.stop()

    def _on_tick(self) -> None:
        self._now_ms = float(self._clock.elapsed())
        finished_props = []
        for prop, desc in list(self._active_anims.items()):
            elapsed = self._now_ms - desc.start_time
            raw = min(elapsed / desc.duration, 1.0) if desc.duration > 0 else 1.0
            desc.current = desc.start + (desc.end - desc.start) * desc.easing.valueForProgress(raw)
            if raw >= 1.0:
                desc.current = desc.end
                finished_props.append(prop)

        self.tick.emit()

        for prop in finished_props:
            desc = self._active_anims.pop(prop, None)
            if desc is None:
                continue
            self.finished.emit(prop)
            if desc.on_finished:
                desc.on_finished()

        self._stop_if_idle()

    def stop(self) -> None:
        self._active_anims.clear()
        self._frame_clients.clear()
        if self._timer.isActive():
            self._timer.stop()
