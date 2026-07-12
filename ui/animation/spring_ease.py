"""
spring_ease - 弹簧缓动函数
从 FeedbackWidget._spring_ease 抽取的纯函数，无 Qt 依赖
"""

import math


def spring_ease(t: float, stiffness: float = 180, damping: float = 14) -> float:
    """弹簧缓动函数

    Args:
        t: 归一化时间 [0, 1]
        stiffness: 弹簧刚度（越大回弹越快）
        damping: 阻尼系数（越大振荡越少）

    Returns:
        缓动值，通常在 0~1 之间（欠阻尼时可能超过 1）
    """
    omega = math.sqrt(stiffness)
    zeta = damping / (2 * omega)

    if zeta < 1.0:
        # 欠阻尼：有振荡
        omega_d = omega * math.sqrt(1.0 - zeta * zeta)
        return 1.0 - math.exp(-zeta * omega * t) * (
            math.cos(omega_d * t) +
            (zeta * omega / omega_d) * math.sin(omega_d * t)
        )
    else:
        # 临界阻尼 / 过阻尼：无振荡
        return 1.0 - (1.0 + omega * t) * math.exp(-omega * t)