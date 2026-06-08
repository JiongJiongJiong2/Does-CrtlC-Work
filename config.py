"""
配置参数 - 动画时长、颜色、尺寸等
"""

# 动画时长配置 (毫秒)
ANIMATION_DURATION = {
    'dot_appear': 200,        # 圆点出现
    'box_expand': 250,        # 框展开
    'text_scramble': 1000,    # 文字解码
    'view_time': 2800,        # 展示时间
    'box_shrink': 350,        # 框收缩成线
    'line_shrink': 250,       # 线收缩回圆点
    'dot_disappear': 200,     # 圆点消失
    'error_display': 700,     # 错误/粘贴显示时间
}

# 颜色配置
COLORS = {
    'dot_copy': '#facc15',     # 黄色 - 复制成功
    'dot_paste': '#22c55e',    # 绿色 - 粘贴成功
    'dot_error': '#ef4444',    # 红色 - 复制失败
    'box_bg': (0, 0, 0, 217),  # 黑色透明 85% (0-255 RGBA)
    'text': '#f5f5f5',         # 文字颜色
    'border': '#facc15',       # 左边界颜色
}

# 尺寸配置
SIZES = {
    'dot_radius': 5,           # 圆点半径
    'box_height': 28,          # 框高度
    'box_min_width': 80,       # 框最小宽度
    'box_max_width': 450,      # 框最大宽度
    'char_width': 9.5,         # 每字符宽度
    'box_padding': 24,         # 框内边距
    'mouse_offset_x': 16,      # 鼠标 X 偏移
    'mouse_offset_y': 16,      # 鼠标 Y 偏移
}

# Spring 物理参数 (用于鼠标跟随缓动)
SPRING = {
    'stiffness': 500,
    'damping': 40,
}

# 文本截断长度
MAX_TEXT_LENGTH = 45

# Unicode 块字符池
BLOCK_CHARS = ['█', '▓', '▒', '░', '▖', '▗', '▘', '▙', '▚', '▛', '▜', '▝', '▞', '▟']
SCRAMBLE_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+-=[]{}|;:,./<>?'