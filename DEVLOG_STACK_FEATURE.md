# Dev Log: Multi-Image Stack Feature / 开发日志：多图堆叠功能

> Date: 2026-06-16 ~ 2026-06-17
> Affected files: `ui/feedback_widget.py`, `core/clipboard_monitor.py`, `config.py`

---

## 1. 状态机时序问题 / State Machine Timing Issue

### 问题 / Problem

`update_images()` 在异步图片到达后直接触发 `STACK_APPEAR`，绕过了状态机的正常序列，导致堆叠动画在错误的时机启动（例如在 `TEXT_REVEAL` 阶段就弹出了堆叠层）。

`update_images()` triggered `STACK_APPEAR` directly when async images arrived, bypassing the state machine's normal sequence. This caused the stack animation to start at the wrong time (e.g., popping up during `TEXT_REVEAL`).

### 根因 / Root Cause

```python
# update_images 中原有的错误逻辑：
if self._image_count >= 2 and self._stack_phase == 'hidden':
    self._stack_phase = 'appearing'
    self._stack_anim_timer.start()  # ← 直接启动，不管当前状态
```

`update_images` 在 Worker 回调中被调用，此时状态机可能还在 `TEXT_REVEAL` 或 `BOX_EXPAND` 阶段。

### 修复 / Fix

移除 `update_images` 中的堆叠触发逻辑，由 `_advance_state()` 的 `IMAGE_APPEAR` 分支在正确时机触发：

```python
# _advance_state 中的正确逻辑：
elif self._state == AnimationState.IMAGE_APPEAR:
    if self._image_count >= 2:
        self._state = AnimationState.STACK_APPEAR
        self._stack_phase = 'appearing'
        self._stack_anim_timer.start()
```

### 正确的动画序列 / Correct Animation Sequence

```
DOT_APPEAR → BOX_EXPAND → TEXT_REVEAL → IMAGE_APPEAR → STACK_APPEAR → VIEWING → STACK_RETRACT → BOX_SHRINK → LINE_SHRINK → DOT_DISAPPEAR
```

---

## 2. 绘制顺序问题 / Drawing Order Issue

### 问题 / Problem

堆叠层绘制在主图之上，视觉上不自然。应该主图在最上面，堆叠层从右下角微露出来。

Stack layers were drawn on top of the main image, which looked unnatural. The main image should be on top, with stack layers peeking out from the bottom-right corner.

### 修复 / Fix

在 `paintEvent` 中调整绘制顺序：先画堆叠层（底层），再画主图（最上层）：

```python
# 先绘制堆叠层（底层，从后往前：layer2 -> layer1）
for layer_idx in range(min(stack_layers, 2) - 1, -1, -1):
    self._draw_stack_layer(painter, base_x, base_y, base_size, layer_idx)

# 再绘制主图（最上层，覆盖堆叠层的大部分，只露出右下角边缘）
self._draw_main_image(painter, base_x, base_y, base_size, vanish_ratio)
```

---

## 3. 占位框在图片加载后消失 / Placeholder Disappears After Image Load

### 问题 / Problem

网页复制多图时，占位框先正确弹出，但当 Worker 下载完第一张图片后，占位框就消失了，最终只显示一张图片。

When copying multiple images from a webpage, placeholders appeared correctly at first, but disappeared after the first image was downloaded, ending up showing only one image.

### 根因 / Root Cause

`update_images()` 用 Worker 实际下载数量覆盖了 `_image_count`：

```python
# 原有错误逻辑：
self._image_count = min(image_count, IMAGE_STACK['max_display'])
# Worker 只下载了 1 张 → image_count = 1 → stack_layers = 0 → 占位框不画了
```

Worker 可能只成功下载了部分图片（超时等），但 `_image_count` 应该代表用户复制时的预估图片总数，不应被实际下载数覆盖。

### 修复 / Fix

`update_images` 不再修改 `_image_count`：

```python
# 注意：不修改 _image_count — 它代表复制时的预估图片总数，用于决定堆叠层数量
# 即使 Worker 只下载了部分图片，堆叠层仍应保持
self._total_image_count = image_count
self._has_image = True
if self._images:
    self._main_image = self._images[0]
```

---

## 4. 网页多图检测不准 / Web Multi-Image Detection Inaccuracy

### 问题 / Problem

网页上有多个 `<img>` 标签时，程序只检测到 1 张图片，因为 `_extract_src()` 只用 `re.search` 提取了第一个匹配。

When a webpage had multiple `<img>` tags, the program only detected 1 image because `_extract_src()` used `re.search` which only matched the first occurrence.

### 修复 / Fix

```python
# 旧：只提取第一个
def _extract_src(self, html):
    m = re.search(r'<img[^>]+src\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
    return m.group(1) if m else None

# 新：提取所有
def _extract_all_srcs(self, html):
    """提取 HTML 中所有 <img> 标签的 src 属性"""
    if not html:
        return []
    return re.findall(r'<img[^>]+src\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
```

同时更新 `_check_copy_result` 中的调用，遍历所有 src 分别归入 `data_uris` 或 `http_urls`。

---

## 5. 配置与优化 / Configuration & Optimization

### 5.1 `show_real_thumbnails` 统一配置

`IMAGE_STACK['show_real_thumbnails']` 已经是统一配置，无论是网页还是本地图片都读取同一个值。`True` 时堆叠层显示真实缩略图，`False` 时仅显示半透明占位框。

### 5.2 占位框透明度可配置

新增 `placeholder_opacity` 配置项：

```python
# config.py
IMAGE_STACK = {
    ...
    'placeholder_opacity': 0.5,  # 占位框透明度（图片未加载时）
}
```

`_draw_main_image` 中读取此配置：

```python
painter.setOpacity(IMAGE_STACK.get('placeholder_opacity', 0.5))
```

### 5.3 多线程并行下载

原有 Worker 串行下载图片（3 张图可能需要 3 × 0.8s = 2.4s），改用 `ThreadPoolExecutor` 并行下载：

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=min(len(tasks), 3)) as pool:
    futures = {}
    for kind, url in tasks:
        if kind == 'data':
            futures[pool.submit(self._decode_data_uri, url)] = None
        else:
            futures[pool.submit(self._download, url)] = None

    for future in as_completed(futures):
        d = future.result()
        if d and len(raw_list) < mx:
            raw_list.append(d)
```

3 张网络图片并行下载，总时间约 0.8s（而非 2.4s 串行）。

---

## 关键设计决策 / Key Design Decisions

| 决策 | 理由 |
|------|------|
| `_image_count` 在构造时确定，不被 `update_images` 修改 | 代表用户意图（复制了多少张），不应被网络下载结果影响 |
| 堆叠动画由状态机驱动，不由数据到达驱动 | 保证动画序列的正确性和可预测性 |
| 先画堆叠层再画主图 | 主图覆盖大部分堆叠层，只露出右下角边缘，视觉更自然 |
| `ThreadPoolExecutor` 并行下载 | 网络图片下载是 IO 密集型，并行可显著减少等待时间 |
| `show_real_thumbnails` 统一配置 | 简化用户理解，不区分图片来源 |

---

## 涉及文件 / Affected Files

| 文件 | 修改内容 |
|------|---------|
| `ui/feedback_widget.py` | 修复时序、绘制顺序、占位框消失、透明度配置 |
| `core/clipboard_monitor.py` | 多图检测、并行下载、日志清理 |
| `config.py` | 新增 `placeholder_opacity` 配置项 |