# Dose Ctrl+C 技术审查与演进建议

审查日期：2026-07-11  
范围：当前 Git 基线、未暂存 UI 重构、`TMP/clipboard-fx-preview` 原型、剪贴板与鼠标链路、现有构建产物。

## 结论先行

1. 当前动画退化包含多个确定性代码错误，不是 Python 天生做不出原型效果。最严重的是 `spring_ease` 新旧接口错接，堆叠入场进度恒为 0、退场会除零；另外竖线退场步骤被隐藏、错误/粘贴提示从约 0.9 秒被拉长到约 3.6 秒、文字解码算法和图片显现速度也被改了。
2. 当前核心并非“监听系统剪贴板变化”，而是“先捕捉 Ctrl+C，再轮询 Qt 剪贴板并比较自制 fingerprint”。它确实读取系统剪贴板，但成功判定不可靠；复制相同内容会误报失败，图片变化也可能漏报。
3. 45.7 MiB 的主因不是业务代码，而是 PyInstaller 把大量未使用 Qt 模块和插件打进了 exe。仅明显可疑的 QML/Quick/PDF/software OpenGL 就约占 15 MB（压缩后）。应先做构建瘦身实验。
4. 不建议做 Python + C++ 核心混合：它保留 Python、PySide6 和 Qt，几乎不减体积；当前 spring/MIME 计算也不是主要性能瓶颈。
5. 如果未来做 Windows-only 原生重写，优先考虑 C# WPF；如果硬指标是完全自包含且小于约 10 MB，再考虑 C++ Win32 + Direct2D。不要为了“小”选择 WinUI 3 自包含部署，它还会带 Windows App SDK。

## 1. 动画审查

### 1.1 TMP 原型的目标时序

```text
圆点 spring 入场
  → 内容框 250 ms easeOut 横向展开
  → 文字 1000 ms scramble（整个未解码区持续有噪点）
  → 展示 2800 ms
  → 宽度 350 ms easeIn 收到 2 px
  → 这条 2 px 竖线在 250 ms 内 linear 向上收回并淡出
  → 圆点 200 ms backIn 消失
```

ERROR/PASTE 是另一条短路径：圆点出现 → 停留 700 ms → 圆点消失，不应经过内容框和竖线阶段。

### 1.2 当前未暂存版本的确定问题

| 优先级 | 问题 | 结果 | 建议 |
|---|---|---|---|
| P0 | `spring_ease(t, stiffness, damping)` 被调用成 `spring_ease(from, to, t)` | 堆叠入场为 0；退场 `ZeroDivisionError` | 调用后先求 eased，再做 `from + (to-from)*eased`；退场单独用 easeIn |
| P0 | ERROR/PASTE 进入普通 VIEWING | 700 ms 变成 2800 ms，且多走框/线退场 | 增加 `PULSE_VIEWING` 或独立的 `done_pulse` 短路径 |
| P0 | 框宽从目标直接收到 0，且收缩开始即 `_box_opacity=0` | 原型的“2 px 竖线向上回收”完全看不到 | 宽度先收到 2；高度阶段同步 opacity 从 1 到 0 |
| P1 | 高度退场、圆点退场 easing 改变 | 节奏变硬，尾部缺少回拉感 | 分别恢复 Linear、BackIn |
| P1 | 新 scramble 未开始区域用空格 | 从“全域噪点解码”变成稀疏逐字出现 | 恢复原型算法：solved 区 + 4 字符块状前沿 + 后方随机噪点 |
| P1 | 图片显现从约 1 秒加快到约 360 ms | 图片突然清晰，与文字节奏脱节 | 用 elapsed/duration 算进度，先恢复 900–1000 ms 基线再调参 |
| P1 | `IMAGE_APPEAR` / `STACK_APPEAR` 没有退出转换 | 动画中粘贴或关闭 holding 时 transition=False | 给所有活动状态定义 cancel/exit，或统一转换到 EXITING |
| P2 | 多个独立 timer 仍并存 | 帧时钟漂移、重绘节奏不一致 | 只保留一个活动期 frame clock，展示超时可保留 single-shot timer |
| P2 | 每帧缩放 QImage、生成 QPixmap | 多图时主线程更容易掉帧 | 缓存最终图、缩略图和有限级别的像素化帧 |

### 1.3 推荐动画结构

- 状态机只负责“合法顺序”，不负责具体插值。
- 一个 `AnimationClock` 使用 `QElapsedTimer`/单调时钟和 `Qt.PreciseTimer`，每帧以真实 elapsed 计算所有属性。
- 动画配置用数据描述：`property / from / to / duration / easing / delay`，不要把时序散落在多个回调中。
- `cancel` 是一等事件：任何活动状态都能安全进入退场；新一次 copy 可从当前可视值开始交叉过渡，避免瞬间消失再重建。
- 为状态机写纯逻辑测试，为关键帧写数值测试；视觉上录制 60 fps 并与 TMP 同时间点截图对比。

### 1.4 动画验收标准

- 状态测试覆盖 COPY(text/no text)、ERROR、PASTE、single image、multi-image、holding、动画中再次 copy/paste。
- ERROR/PASTE 总时长约 900 ms；文本 copy 各阶段时长误差不超过一帧或约 20 ms。
- 2 px 竖线阶段肉眼可见；scramble 从第一帧起填满目标字符宽度。
- 60 Hz 环境连续动画无未捕获异常；多图路径 UI 主线程单帧工作尽量低于 8 ms。

## 2. 核心产品逻辑审查

### 2.1 当前实际链路

```text
keyboard 全局捕捉 Ctrl+C
  → 立即读取 QClipboard
  → 未变化则 40 / 120 / 260 ms 后重试
  → 比较 (文本前 200 字、是否有图、前 5 个 URL、MIME formats)
  → fingerprint 不同 = 成功，否则 = 失败
```

这不是完全“自己伪造内容”，因为最终读的是系统剪贴板；但它监听的是按键，系统剪贴板只是被轮询验证。问题在于验证依据不是系统版本号，而是内容摘要。

### 2.2 现有逻辑的产品错误

- 配置声明 `same_content_as_success=True`，代码没有使用；重复复制相同内容会误报失败。
- fingerprint 不含图片内容，换一张图片仍可能被判为没变化；长文本只看前 200 字。
- Ctrl+C 不是所有 Copy：右键菜单、Ctrl+Insert、应用内 Copy 命令会漏掉。
- Ctrl+C 也不必然表示 Copy：终端里可能是中断；应用可能接管快捷键。
- 420 ms 固定重试窗口对延迟渲染、远程桌面或繁忙应用不稳。
- 全局鼠标 120 Hz + spring 60 Hz 在没有反馈 UI 时也一直运行，没有产品收益。
- worker 的完成顺序可能改变图片顺序；旧 worker 不会因 `quit()` 自动中止；共享字段可能和下一次复制串数据。

### 2.3 推荐的正确模型

产品需要先确定语义：

- 模式 A（推荐默认）：只要系统剪贴板变化，就显示“已复制”。这能覆盖快捷键、菜单和程序性复制。
- 模式 B（“Does Ctrl+C Work”诊断模式）：Ctrl+C 只创建 pending intent；在 deadline 内收到系统剪贴板更新才确认成功，超时显示“未检测到剪贴板更新”，不要武断写“复制失败”。

Windows 实现：

```text
HiddenMessageWindow
  ├─ AddClipboardFormatListener → WM_CLIPBOARDUPDATE
  ├─ GetClipboardSequenceNumber → 系统剪贴板版本
  └─ WH_KEYBOARD_LL（仅诊断模式）→ pending Ctrl+C intent

WM_CLIPBOARDUPDATE
  → 读取 sequence
  → 去重/关联最近 pending intent
  → 快速提取轻量元数据并立即显示反馈
  → 图片解码、HTML 解析、网络获取放到可取消 worker
```

Python 版本可先用 Qt 的 `QClipboard.dataChanged` 做事件驱动 MVP；Windows 专属版本再通过 native event filter/ctypes 接入 `WM_CLIPBOARDUPDATE` 与 sequence number。不要每次复制都用自制 fingerprint 证明系统是否变化。

## 3. 性能与体积

### 3.1 当前体积证据

现有 `dist/DoesCtrlCWork.exe` 为 47,954,729 bytes（约 45.7 MiB）。归档包含未显式使用的：

- Qt6Quick、Qt6Qml、Qt6QmlModels；
- Qt6Pdf；
- Qt6VirtualKeyboard；
- Qt6OpenGL 和约 7.6 MB（压缩后）的 `opengl32sw.dll`；
- qdirect2d/qminimal/qoffscreen、多个无关图片格式、TLS 与翻译资源。

业务代码和 Python 运行时不是主要体积来源；混合 C++ 扩展不会移除这些依赖。

### 3.2 不重写时的体积实验顺序

1. 在干净虚拟环境构建，固定 Python/PySide6/PyInstaller 版本，先保存功能基线。
2. PyInstaller spec 显式排除 Qml/Quick/Pdf/VirtualKeyboard/OpenGL 等未使用模块，并只保留 Windows platform、实际需要的 imageformats。
3. 分别验证文本、PNG/JPEG/GIF/WebP、托盘、高 DPI、多屏、无 OpenGL 机器；不要只看能否启动。
4. 试验 Qt 官方 `pyside6-deploy`/Nuitka，关闭 translations、排除 QML plugins，并比较：文件大小、冷启动、内存、误报率。
5. 给体积设决策门槛：若 Python 版本能降到可接受范围并保持稳定，就不因语言偏好重写。

## 4. Python、C#、C++ 选择

| 方案 | 体积 | 开发/维护 | Windows 集成 | 本项目建议 |
|---|---|---|---|---|
| Python + PySide6（优化后） | 中等，Qt 有下限 | 最快，现有代码可复用 | 通过 Qt/ctypes 足够 | **当前首选**，先修正确性和构建 |
| Python + C++/pybind11 | 几乎不改善 | 构建和调试更复杂 | 无本质改善 | **不推荐**；没有证据证明计算是瓶颈 |
| C# WPF，framework-dependent | app 本体可小，但依赖已装 runtime | 中等，动画和 Win32 interop 成熟 | 很好 | **长期 Windows-only 首选** |
| C# WPF，self-contained | 通常仍较大 | 中等 | 很好 | 不能以“必然比 45 MB 小”为前提 |
| C# WinUI 3 | framework-dependent 小，自包含较大 | 部署模型更复杂 | 很好 | 对这个小托盘工具没有明显收益 |
| C++ Qt | 仍需 Qt DLL | 高 | 好 | 为体积改写却保留 Qt，不划算 |
| C++ Win32 + Direct2D/DirectComposition | 最有机会做到很小 | 最高，UI/文本/DPI/无障碍成本大 | 最强 | 仅在“完全自包含且极小”为硬指标时选择 |

### 推荐决策

- 未来 1–2 个版本：继续 Python，先把产品语义、动画和打包做好。
- 若之后确定只支持 Windows、希望长期维护且可接受 runtime/installer：全量迁移 C# WPF，不做 Python+C++ 中间层。
- 若必须单 exe、无外部 runtime、目标小于约 10 MB：做 C++ Win32/Direct2D 技术样机后再决策；不要直接全量重写。

## 5. 分阶段实施路线图

### Phase 0：保护当前工作（半天）

- 为当前未暂存动画重构建独立分支或 WIP commit。
- 添加最小 smoke tests，确保后续能对比 HEAD、当前重构和 TMP。
- 明确产品文案：`复制成功` 还是 `检测到剪贴板更新`。

完成条件：任何实验都能一键回到当前版本；产品成功/失败语义写成一页规则。

### Phase 1：动画 P0 修复（1–2 天）

- 修复 spring 接口；恢复 ERROR/PASTE 短路径、2 px 竖线、正确 easing。
- 恢复 TMP scramble 算法和约 1 秒图片显现。
- 补齐所有活动状态的 cancel/exit 转换。
- 加状态表测试和属性关键帧测试。

完成条件：P0 测试全过，序列与 TMP 一致，无 timer callback 异常。

### Phase 2：真正统一动画时钟（2–3 天）

- 使用单调时钟 + 单 frame clock；按真实 elapsed 计算进度。
- 只在反馈窗口活动时追踪鼠标；空闲时停止 8/16 ms timer。
- 缓存图片缩放、缩略图和像素化帧。
- 录制性能基线：空闲 CPU、活动 CPU、帧耗时、内存。

完成条件：空闲无高频 timer；多图动画无明显掉帧；性能指标可重复。

### Phase 3：剪贴板核心重构（2–4 天）

- 先接 `QClipboard.dataChanged`，再实现 Windows `WM_CLIPBOARDUPDATE + sequence number` backend。
- 把 Ctrl+C hook 变为可选的 intent correlator，不在 hook 回调做重活。
- 设计 request id/cancellation token，杜绝旧图片 worker 污染新反馈。
- 保持图片顺序，去掉重复合并，给延迟渲染设置可配置 deadline。

完成条件：相同文本、不同图片同格式、右键复制、Ctrl+Insert、连续快速复制、延迟图片等用例均符合产品规则。

### Phase 4：打包瘦身实验（1–2 天）

- 产出 PyInstaller-minimal 与 pyside6-deploy/Nuitka 两个候选包。
- 做干净 Windows VM 测试，而不是只在开发机测试。
- 记录大小、启动时间、内存、功能矩阵；选一个可复现构建方案。

完成条件：有数据决定是否仍需语言迁移，而不是凭 45 MB 一个数字重写。

### Phase 5：C# 技术样机（可选，3–5 天）

只做垂直切片：隐藏窗口监听剪贴板 + Ctrl+C 关联 + 鼠标旁圆点/文本动画 + 托盘。分别发布 framework-dependent 与 self-contained，实测体积和冷启动。

Go 条件：核心用例正确，动画手感达到 Python 修复版，且部署/体积收益足以覆盖重写成本。否则停在优化后的 Python 版本。

## 6. 建议的测试矩阵

- 内容：相同文本、长文本前 200 字相同、空选择、单图、多图、HTML 图、文件路径、网络图。
- 入口：Ctrl+C、Ctrl+Insert、右键 Copy、应用菜单、程序性剪贴板更新、终端 Ctrl+C。
- 时序：连续快速复制、复制后立刻粘贴、图片下载中再次复制、holding 中退出。
- 环境：普通/高权限应用、远程桌面、高 DPI、多显示器、系统休眠恢复。
- 发布：干净 Windows VM、无开发环境、离线启动、杀毒软件冷启动扫描。

## 最终优先级

```text
P0 动画运行时错误与状态路径
  → P0 剪贴板成功判定语义
  → P1 空闲轮询与图片帧缓存
  → P1 PyInstaller/Qt 瘦身
  → 用数据决定是否做 C# 样机
  → 不做 Python+C++ 混合过渡
```

## 7. 实施状态（2026-07-12）

| 项目 | 状态 | 说明 |
|---|---|---|
| P0：spring 接口、ERROR/PASTE 短路径、退场 2 px 竖线 | 已完成 | 堆叠 spring 已改为正常化时间调用；短提示改用 `PULSE`；框宽先收至 2 px，线阶段线性淡出，圆点使用 InBack 退场。 |
| P1：TMP scramble、图片 reveal、动画中退出 | 已完成 | 恢复全域噪点解码，图片 reveal 恢复为 1000 ms；IMAGE/STACK/TEXT/PULSE 都能安全进入退出路径。 |
| P2：单时钟、按需鼠标跟随、图片缓存 | 已完成 | `PropertyEngine` 改为 `QElapsedTimer + PreciseTimer` 单帧时钟；MouseTracker 不再保留内部 timer；主图 25 帧 reveal 和堆叠缩略图在更新图片时缓存。 |
| P2：结构化空闲验证 | 已完成 | 自动化测试确认 PropertyEngine 在没有 frame client/属性时停止，MouseTracker 没有内部后台 timer。 |
| P2：真实桌面性能基线与录屏对照 TMP | 未完成 | 需要在正常 Windows 桌面实测空闲 CPU、多图帧耗时和 60fps 录屏。 |
| Phase 3：系统剪贴板事件与 sequence number | 已完成（Qt 后端） | 使用 `QClipboard.dataChanged` 通知，并在 Windows 用 `GetClipboardSequenceNumber` 去重；Ctrl+C 改为 pending intent + 700ms 确认超时。 |
| Phase 3：直接 `WM_CLIPBOARDUPDATE` 后端 | 未开始 | 仅当 Qt 事件在目标 Windows 环境出现平台问题时再增加，避免两套监听器重复触发。 |
| Phase 4：PyInstaller/Qt 瘦身实验 | 自动验证完成；桌面验收待办 | 隔离环境基线为 45.74 MiB；spec 裁剪后的 v3 为 25.91 MiB（-43.4%），离屏测试和冻结包启动通过。发布前仍需手动验证托盘、剪贴板图片/多图、Holding、高 DPI 与软件 OpenGL 回退。 |
| Phase 5：Holding 与托盘交互 | 自动验证完成；桌面验收待办 | Ctrl+V 只会结束 Holding COPY，普通 COPY 会显示绿色 paste 提示；托盘改为可持久化的自绘圆角深灰 `Qt.Popup`，带黄色开关和 EN/中标识。真实 Windows 仍需验证右键、位置、多显示器和 DPI。 |
| Python+C++ 混合、C# 迁移 | 不做 | 按本轮产品决策不实施。 |

验证：`QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v` 已通过 12 项测试；`python -m compileall -q .` 和 `git diff --check` 通过。

## 8. 中文文本卡顿与“原生感”改进计划

### 已确认的问题

- 内容框每次 `paintEvent` 都重新创建 `Cascadia Code` 等宽字体，并强制追加 2px 字距；对中文而言，这既不是 Windows 原生排版，也会触发 fallback 字体与过大的字符间距。
- 内容框宽度是 `len(text) × 9.5`，不是最终字体的真实像素宽度。中文、emoji、全角符号和中英混排都可能出现框宽估算错误。
- scramble 在 60fps 每帧重建整段字符串。中文目标字符、ASCII 乱码和 block 字符混排会增加字体 fallback 和 layout 的负担，表现为复制中文时更容易掉帧。

### 实施顺序

1. 新增 `TextStyleResolver`：英文/代码保持 Cascadia Mono 风格；中文或中英混排优先使用 Windows UI 字体（真实桌面验证 Segoe UI Variable、Microsoft YaHei UI、Microsoft YaHei），中文取消绝对 2px 字距。
2. 用 `QFontMetricsF.horizontalAdvance` 测量真实文本宽度；布局从固定 `char_width` 改为 style + metrics 驱动，并为 emoji 留出安全边距。
3. 将 QFont、metrics 和最终文本布局缓存到 FeedbackWidget；ContentBox 只接收已经确定的样式，不在 paint 中创建字体。
4. 窗口/鼠标仍维持 60fps；scramble 字面仅以 24–30fps 更新，或仅在 reveal 前沿变化时刷新。这样视觉连续，但中文不会每帧做完整 glyph layout。
5. 添加中文、混合中英、emoji、45 字上限文本的宽度和截图测试；在真实 Windows 桌面录制 60fps，对比中文和英文复制的帧耗时。

### 验收标准

- 中文、英文和混排文本均不被裁剪，内容框宽度与真实字形宽度一致。
- 中文不再带有 2px 英文式追踪字距，字体与 Windows UI 视觉一致。
- 中文 scramble 的平均帧处理时间不高于英文路径的 1.5 倍；窗口跟随不因文本更新明显掉帧。

### 实施状态（2026-07-12）

- 已完成：脚本感知的 `TextStyleResolver`、Windows UI 字体候选、中文零字距、真实 metrics 宽度、文本省略、QFont/QFontMetricsF/QStaticText 缓存，以及 P8.1 的 16ms 增量 scramble 缓冲。
- 自动验证：中文、混排、emoji 样式选择；长中文不超框且省略；缓存最终布局可以绘制；完整离屏测试已达 15 项。
- 未完成：真实 Windows 桌面实际 fallback 字体、视觉“原生感”、中文/英文帧耗时对比和 60fps 录屏验收。

### P8.1：ASCII block 伪加载平滑度（2026-07-12）

- 已完成：scramble 刷新由 33ms 改为 16ms，与窗口帧时钟同频；使用持久化字符缓冲，已解码前缀不再反复随机，前沿 block 和远端少量噪声增量更新。
- 自动验证：离屏测试 15/15 通过，覆盖 16ms 刷新、缓冲长度和已解码前缀稳定性；`compileall` 与 `git diff --check` 通过。
- 未完成：在真实 Windows 桌面确认 ASCII block 的视觉连续性及实际帧耗时。
