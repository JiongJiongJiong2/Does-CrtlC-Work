"""
PropertyEngine - 统一属性动画引擎
替代 FeedbackWidget 中 6 个手写 QTimer + _start_property_animation / _animation_tick
使用单一定时器驱动所有活跃属性的插值
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict
from PySide6.QtCore import QObject, QTimer, Signal, QEasingCurve


@dataclass
class AnimDescriptor:
    """单个属性动画的描述符"""
    start: float
    end: float
    duration: int  # 毫秒
    easing: QEasingCurve
    start_time: float  # 毫秒时间戳
    current: float
    on_finished: Optional[Callable] = field(default=None, repr=False)


class PropertyEngine(QObject):
    """统一属性动画引擎

    单定时器驱动所有活跃动画的插值，替代多个独立 QTimer。

    Signals:
        tick(): 每帧触发，通知所有组件 repaint
        finished(str): 单个属性动画完成时发射，携带属性名
    """

    tick = Signal()
    finished = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60fps
        self._timer.timeout.connect(self._on_tick)
        self._active_anims: Dict[str, AnimDescriptor] = {}

    def animate(self, prop: str, start: float, end: float,
                duration: int, easing: QEasingCurve = None,
                on_finished: Callable = None) -> None:
        """启动一个属性动画

        如果同名属性已有活跃动画，先取消旧的再启动新的。

        Args:
            prop: 属性名（如 'dot_scale', 'box_width'）
            start: 起始值
            end: 目标值
            duration: 持续时间（毫秒）
            easing: 缓动曲线，默认 Linear
            on_finished: 动画完成回调（可选）
        """
        if prop in self._active_anims:
            del self._active_anims[prop]

        desc = AnimDescriptor(
            start=start,
            end=end,
            duration=duration,
            easing=easing or QEasingCurve(QEasingCurve.Linear),
            start_time=time.time() * 1000,
            current=start,
            on_finished=on_finished,
        )
        self._active_anims[prop] = desc

        if not self._timer.isActive():
            self._timer.start()

    def cancel(self, prop: str) -> None:
        """取消指定属性的动画"""
        if prop in self._active_anims:
            del self._active_anims[prop]
            if not self._active_anims and self._timer.isActive():
                self._timer.stop()

    def cancel_all(self) -> None:
        """取消所有活跃动画"""
        self._active_anims.clear()
        if self._timer.isActive():
            self._timer.stop()

    def get_value(self, prop: str, default: float = 0.0) -> float:
        """获取属性当前插值"""
        desc = self._active_anims.get(prop)
        if desc:
            return desc.current
        return default

    def has_active(self, prop: str) -> bool:
        """指定属性是否有活跃动画"""
        return prop in self._active_anims

    def has_any_active(self) -> bool:
        """是否有任何活跃动画"""
        return len(self._active_anims) > 0

    def _on_tick(self):
        """单定时器驱动所有活跃动画的插值"""
        now = time.time() * 1000
        finished_props = []

        for prop, desc in self._active_anims.items():
            elapsed = now - desc.start_time
            raw = min(elapsed / desc.duration, 1.0) if desc.duration > 0 else 1.0
            eased = desc.easing.valueForProgress(raw)
            desc.current = desc.start + (desc.end - desc.start) * eased

            if raw >= 1.0:
                desc.current = desc.end
                finished_props.append(prop)

        # 发射 tick 通知所有组件重绘
        self.tick.emit()

        # 处理已完成的动画（在 tick 之后，避免迭代中修改字典）
        for prop in finished_props:
            desc = self._active_anims.pop(prop)
            self.finished.emit(prop)
            if desc.on_finished:
                desc.on_finished()

        # 无活跃动画时停止定时器
        if not self._active_anims and self._timer.isActive():
            self._timer.stop()

    def stop(self):
        """停止引擎（清理所有动画和定时器）"""
        self._active_anims.clear()
        if self._timer.isActive():
            self._timer.stop()