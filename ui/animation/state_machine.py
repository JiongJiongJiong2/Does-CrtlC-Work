"""
AnimationStateMachine - 集中式动画状态机
将分散在 FeedbackWidget 多处方法中的状态转换逻辑集中到转换表中
"""

from enum import Enum, auto
from PySide6.QtCore import QObject, Signal


class AnimationState(Enum):
    """动画状态枚举"""
    IDLE = auto()
    DOT_APPEAR = auto()
    BOX_EXPAND = auto()
    TEXT_REVEAL = auto()
    IMAGE_APPEAR = auto()
    STACK_APPEAR = auto()
    PULSE = auto()
    VIEWING = auto()
    HOLDING = auto()
    STACK_RETRACT = auto()
    IMAGE_VANISH = auto()
    BOX_SHRINK = auto()
    LINE_SHRINK = auto()
    DOT_DISAPPEAR = auto()
    COMPLETE = auto()


class AnimationStateMachine(QObject):
    """集中式动画状态机

    使用转换表定义所有状态转换规则，替代分散在多处方法中的 if/elif 逻辑。

    Signals:
        state_changed(AnimationState): 状态变更时发射，携带新状态
        action_requested(str): 状态转换时请求执行的动作名称
    """

    state_changed = Signal(AnimationState)
    action_requested = Signal(str)

    # 转换表：{(当前状态, 触发事件) → (下一状态, 动作名称)}
    TRANSITIONS = {
        # === 入场序列 ===
        (AnimationState.IDLE, 'start'):
            (AnimationState.DOT_APPEAR, 'animate_dot_appear'),

        (AnimationState.DOT_APPEAR, 'done_copy_with_text'):
            (AnimationState.BOX_EXPAND, 'animate_box_expand'),
        (AnimationState.DOT_APPEAR, 'done_copy_no_text'):
            (AnimationState.IMAGE_APPEAR, 'enter_image_or_viewing'),
        (AnimationState.DOT_APPEAR, 'done_error_paste'):
            (AnimationState.PULSE, 'start_pulse_timer'),
        (AnimationState.DOT_APPEAR, 'exit'):
            (AnimationState.DOT_DISAPPEAR, 'animate_dot_disappear'),

        (AnimationState.BOX_EXPAND, 'done'):
            (AnimationState.TEXT_REVEAL, 'start_scramble'),

        (AnimationState.TEXT_REVEAL, 'done_has_image'):
            (AnimationState.IMAGE_APPEAR, 'enter_image_or_viewing'),
        (AnimationState.TEXT_REVEAL, 'done_holding_no_image'):
            (AnimationState.HOLDING, 'start_holding_timer'),
        (AnimationState.TEXT_REVEAL, 'done_normal_no_image'):
            (AnimationState.VIEWING, 'start_view_timer'),

        (AnimationState.IMAGE_APPEAR, 'done_multi_image'):
            (AnimationState.STACK_APPEAR, 'animate_stack'),
        (AnimationState.IMAGE_APPEAR, 'done_holding_single'):
            (AnimationState.HOLDING, 'start_holding_timer'),
        (AnimationState.IMAGE_APPEAR, 'done_normal_single'):
            (AnimationState.VIEWING, 'start_view_timer'),
        (AnimationState.IMAGE_APPEAR, 'exit_no_stack'):
            (AnimationState.IMAGE_VANISH, 'animate_image_vanish'),

        (AnimationState.STACK_APPEAR, 'done_holding'):
            (AnimationState.HOLDING, 'start_holding_timer'),
        (AnimationState.STACK_APPEAR, 'done_normal'):
            (AnimationState.VIEWING, 'start_view_timer'),
        (AnimationState.STACK_APPEAR, 'exit_has_stack'):
            (AnimationState.STACK_RETRACT, 'retract_stack'),
        (AnimationState.STACK_APPEAR, 'exit_no_stack'):
            (AnimationState.IMAGE_VANISH, 'animate_image_vanish'),

        (AnimationState.PULSE, 'timeout'):
            (AnimationState.DOT_DISAPPEAR, 'animate_dot_disappear'),
        (AnimationState.PULSE, 'exit'):
            (AnimationState.DOT_DISAPPEAR, 'animate_dot_disappear'),

        # === 退场序列 ===
        (AnimationState.VIEWING, 'timeout_has_stack'):
            (AnimationState.STACK_RETRACT, 'retract_stack'),
        (AnimationState.VIEWING, 'timeout_no_stack'):
            (AnimationState.IMAGE_VANISH, 'animate_image_vanish'),
        (AnimationState.VIEWING, 'exit_has_stack'):
            (AnimationState.STACK_RETRACT, 'retract_stack'),
        (AnimationState.VIEWING, 'exit_no_stack'):
            (AnimationState.IMAGE_VANISH, 'animate_image_vanish'),

        (AnimationState.HOLDING, 'exit_has_stack'):
            (AnimationState.STACK_RETRACT, 'retract_stack'),
        (AnimationState.HOLDING, 'exit_no_stack'):
            (AnimationState.IMAGE_VANISH, 'animate_image_vanish'),

        (AnimationState.TEXT_REVEAL, 'exit_no_stack'):
            (AnimationState.IMAGE_VANISH, 'animate_image_vanish'),

        (AnimationState.STACK_RETRACT, 'done'):
            (AnimationState.IMAGE_VANISH, 'animate_image_vanish'),

        (AnimationState.IMAGE_VANISH, 'done'):
            (AnimationState.BOX_SHRINK, 'animate_box_shrink'),

        (AnimationState.BOX_SHRINK, 'done'):
            (AnimationState.LINE_SHRINK, 'animate_line_shrink'),

        (AnimationState.LINE_SHRINK, 'done'):
            (AnimationState.DOT_DISAPPEAR, 'animate_dot_disappear'),

        (AnimationState.DOT_DISAPPEAR, 'done'):
            (AnimationState.COMPLETE, 'emit_complete'),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = AnimationState.IDLE

    @property
    def state(self) -> AnimationState:
        return self._state

    def transition(self, event: str) -> bool:
        """尝试状态转换

        Args:
            event: 触发事件名称

        Returns:
            True 如果转换成功，False 如果无匹配转换
        """
        key = (self._state, event)
        if key not in self.TRANSITIONS:
            return False

        new_state, action = self.TRANSITIONS[key]
        self._state = new_state
        self.state_changed.emit(new_state)
        if action:
            self.action_requested.emit(action)
        return True

    def reset(self):
        """重置到初始状态"""
        self._state = AnimationState.IDLE

    def is_active(self) -> bool:
        """状态机是否处于活跃状态"""
        return self._state not in (AnimationState.IDLE, AnimationState.COMPLETE)
