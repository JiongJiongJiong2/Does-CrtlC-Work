"""
配置参数 - 动画时长、颜色、尺寸等
"""

# 动画时长配置 (毫秒)
ANIMATION_DURATION = {
    'dot_appear': 200,        # 圆点出现
    'box_expand': 250,        # 框展开
    'text_scramble': 1000,    # 文字解码
    'image_reveal': 1000,     # 图片像素化揭现
    'view_time': 2800,        # 展示时间（非 holding 模式）
    'box_shrink': 350,        # 框收缩成线
    'line_shrink': 250,       # 线收缩回圆点
    'dot_disappear': 200,     # 圆点消失
    'error_display': 700,     # 错误/粘贴显示时间
    'stack_appear': 220,      # 堆叠层弹出
    'stack_retract': 220,     # 堆叠层回收
    'holding_max': 30000,     # holding 模式最大持有时长
}

# 剪贴板检测参数
CLIPBOARD_CHECK = {
    'confirmation_timeout': 700,       # Ctrl+C 等待系统剪贴板事件的最长时间(ms)
    'event_retry_delays': [40, 120],   # 事件已到达但 MIME 暂不可读时的有限重试(ms)
}

# All preview inputs share these limits. Network preview is explicitly opt-in.
PREVIEW_LIMITS = {
    'max_concurrent': 3,
    'max_images': 4,
    'max_image_bytes': 16 * 1024 * 1024,  # encoded bytes (raw MIME/file/data/HTTP)
    'max_total_bytes': 32 * 1024 * 1024,  # encoded bytes per copy session
    'max_image_pixels': 16 * 1024 * 1024,
    'max_total_pixels': 32 * 1024 * 1024,
    'thumbnail_edge': 256,
    'decoder_allocation_mb': 64,
    'remote_deadline_ms': 5000,
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
    'box_text_min_width': 0,   # 短文本按实际内容宽度收紧
    'box_height': 28,          # 框高度
    'box_min_width': 80,       # 框最小宽度
    'box_max_width': 450,      # 框最大宽度
    'box_padding': 24,         # 框内边距
    'mouse_offset_x': 16,      # 鼠标 X 偏移
    'mouse_offset_y': 16,      # 鼠标 Y 偏移
}

# 文本渲染：scramble 与窗口帧时钟同频；每帧只变更少量噪声字符。
TEXT_RENDER = {
    'font_size': 10,
    'latin_letter_spacing': 0.5,
    'cjk_letter_spacing': 0.0,
    'scramble_refresh_ms': 16,
    'scramble_mutations_per_frame': 4,
}

# Spring 物理参数 (用于鼠标跟随缓动)
SPRING = {
    'stiffness': 1500,
    'damping': 70,
}

# 屏幕边缘停靠过渡。进入/退出使用不同阈值，避免光标贴着边缘时
# 右侧镜像或图片上下布局在相邻帧反复切换。
DOCK_TRANSITION = {
    'right_duration': 210,
    'bottom_duration': 190,
    'enter_margin': 12,
    'exit_margin': 26,
}

# 多图堆叠参数
IMAGE_STACK = {
    'max_preload': 4,           # 剪贴板最多预取图片数（由具体布局决定展示 3 或 4 张）
    'fan_max_display': 3,       # 原扇形堆叠保持最多 3 张
    'cascade_max_display': 4,   # 横向层叠最多 4 张
    'show_real_thumbnails': True,  # 堆叠层是否显示真实缩略图（False=仅半透明圆角方块）
    'offset_x': 14,             # 每层 X 偏移（向右，需足够大以露出边缘）
    'offset_y': 14,             # 每层 Y 偏移（向下，需足够大以露出边缘）
    'rotate_per_layer': 3.0,    # 每层旋转角度（以右下角为圆心，微旋转）
    'opacity_layer1': 0.75,     # 第1层透明度
    'opacity_layer2': 0.55,     # 第2层透明度
    'placeholder_opacity': 0.6, # 占位框透明度（图片未加载时）
    'placeholder_border_color': (255, 255, 255, 20),
    'placeholder_bg_color': (30, 30, 35, 200),
    'image_border_color': (255, 255, 255, 30),
    'image_surface_color': (17, 17, 17, 220),
    'border_color': (255, 255, 255, 25),  # 堆叠层边框色
    'bg_color': (20, 20, 23, 240),        # 堆叠层背景色
    'cascade_offset_x': 28,     # 递进层叠的基础间距；后层会按权重进一步拉开
    'cascade_opacities': (1.0, 0.78, 0.58, 0.42),
    'cascade_stagger': 0.06,    # 右侧镜像切换时每层错峰进度
}

# 文本预览。剪贴板只在变更事件中读取一次；UI 仅保留这份受控快照，
# 防止超大复制内容在动画或绘制中造成明显分配和卡顿。
MAX_TEXT_LENGTH = 65536

TEXT_VIEW = {
    # 横向导航按逻辑像素移动；字符数由当前字体的实际字宽决定。
    'scroll_pixels': 42,
    'scroll_duration': 110,
    # 滚动边界按较小窗口计算，保证 CJK/emoji 宽字符的中等长度行也能
    # 到达行尾；实际静态绘制会使用更大的窗口以填满内容框。
    'scroll_window_chars': 32,
    'render_chars': 192,
    'scroll_buffer_chars': 64,
    # 宽度计算最多探测每行的前 N 个字符。超过这个长度的行直接使用
    # 固定框宽，避免为超长行创建完整文本布局。
    'width_probe_chars': 512,
    'max_visible_lines': 5,
    'line_expand_duration': 150,
    # 单行框保持原高度；展开后的相邻行使用更紧凑的基线步进。
    'expanded_line_step': 20,
}

# Unicode 块字符池
BLOCK_CHARS = ['█', '▓', '▒', '░', '▖', '▗', '▘', '▙', '▚', '▛', '▜', '▝', '▞', '▟']
# SCRAMBLE_CHARS = '!@#$%^&*()_+-=[]{}|;:,./<>?'
SCRAMBLE_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+-=[]{}|;:,./<>?'
