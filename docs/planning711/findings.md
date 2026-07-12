# Findings & Decisions

## Requirements
- 检查当前未暂存改动，分析动画为何不能复刻 TMP 原型的丝滑效果、是否缺步骤或顺序错误。
- 评估转 C#，或将核心功能迁往 C++/C# 的合理性，重点关注约 45 MB 打包体积。
- 审查核心产品逻辑：目标是确认 Ctrl+C 是否真的复制成功，而当前实现疑似自行捕捉、没有监听系统剪贴板。
- 以产品与全栈视角给出方案、建议、优先级和可实施计划。
- 2026-07-12：用户选择继续 Python，实现审查报告的 P0–P2；不做 Python+C++ 混合与 C#。

## Research Findings
- 工作区根目录包含三个历史发布 zip、`TMP` 原型目录和 `dose-ctrlc` 项目目录。
- 动画实现已拆为 `spring_ease.py`、`state_machine.py`、`property_engine.py`，UI 组件也已分层；TMP 原型是 React/Vite/TypeScript。
- 根目录的 git 命令失败，说明实际仓库元数据可能位于项目子目录或 `.git` 不是有效仓库目录，尚不能据此判断未暂存改动。
- 实际 Git 仓库位于 `dose-ctrlc/`；根目录只是工作区容器。
- 当前产品改动为：`ui/feedback_widget.py` 大幅重写（302 行新增、585 行删除），并新增未跟踪的 `ui/animation/`、`ui/components/`、`ui/feedback_layout.py`。
- `core/mouse_tracker.py`、`core/clipboard_monitor.py`、`main.py` 当前没有未暂存变化，因此核心逻辑疑问主要是既有架构问题，不是本次动画重构直接引入。
- HEAD `4edd35c` 本身是“动画文件重构、C++ 重构、跨平台”规划文档提交，实际代码基线来自此前 v2.1.0 系列提交。
- 核心检测不是持续监听系统剪贴板：它先用 `keyboard.add_hotkey('ctrl+c')` 捕捉按键，再在 0/40/120/260 ms 读取 Qt 剪贴板并比较自制 fingerprint。也就是说，触发源是按键，验证源才是系统剪贴板。
- `ClipboardMonitor` 的成功条件要求 fingerprint 与上次不同；尽管配置存在 `same_content_as_success=True`，当前已读代码中没有使用该配置。因此“再次复制相同内容”会在约 420 ms 后误报失败，这是明显的产品逻辑 bug。
- fingerprint 只含文本前 200 字、是否有图、最多 5 个 URL 和 MIME 格式；两份内容可能 fingerprint 相同，图片像素变化也检测不到，不能可靠代表系统剪贴板是否更新。
- 鼠标跟随当前固定启动两个永久定时器：8 ms 轮询系统光标（约 120Hz）+ 16 ms 弹簧计算/重绘（约 60Hz），即使没有反馈窗口也持续运行，属于可避免的后台开销。
- 鼠标弹簧积分使用固定 `dt=0.016`，没有按真实帧间隔计算；当 UI 线程掉帧时动画时间尺度会变慢、手感不稳定。
- PyInstaller 使用 onefile 打包 PySide6，45–48 MB 发布体积主要由 Python 运行时、Qt 库/插件和压缩方式决定，不是业务代码体积；spec 还保留 `strip=False`、`optimize=0`。
- 新动画架构引入单一 16 ms `PropertyEngine` 和集中状态机，这个方向有利于一致性，但目前需要核对状态事件是否真正接线、属性默认值是否能在动画结束后保留。
- 已发现确定性动画 bug：`spring_ease.py` 的签名是 `spring_ease(t, stiffness=180, damping=14)`，但 `feedback_widget.py:364` 按旧接口调用 `spring_ease(from, to, t)`。例如入场传 `(0,1,t)` 时函数实际把 `t=0, stiffness=1, damping=当前进度`，返回恒接近 0；堆叠动画基本无法正确展开。退场传 `(1,0,t)` 还会令 `stiffness=0`，涉及除零风险。这是“动画步骤缺失/不对”的直接根因之一。
- TMP 原型的基础顺序是：圆点 spring 入场 → 250 ms easeOut 横向展开 → 文字 scramble → 展示 2800 ms → 350 ms easeIn 宽度收至 2 px → 250 ms linear 高度/透明度收至 0 → 200 ms backIn 圆点消失。
- TMP 的文字 scramble 在整个未解码区域持续显示随机块/字符，并仅让前沿 4 字符使用块状字符；新 Python 改为每字符延迟启动，尚未开始的区域全部为空格。这会改变原型的“数据流从满屏噪点逐渐解码”观感，视觉上更稀疏且像逐字出现。
- TMP 使用浏览器 `requestAnimationFrame` 和 Motion 的 spring；Python 属性引擎用 16 ms QTimer，理论帧率相近，但实际需要采用单调时钟和真实 elapsed，避免系统时间调整及 UI 主线程阻塞造成跳帧。
- 新代码把图片像素化步进从每 40 ms `+0.04`（约 1 秒）改为 `+0.12`（约 360 ms），图片显现速度约快 3 倍，这也是手感变化而非单纯重构。
- 动画退场还有三处明确偏差：新代码将框宽直接收到 `0`（原型/旧版为 `2px`）；在宽度收缩开始时立刻把 `_box_opacity=0`，导致本应可见的竖线收缩阶段消失；高度收缩从 `linear` 变成 `InQuad`、圆点退场从 `backIn` 变成 `InQuad`。
- ERROR/PASTE 被状态机合并到普通 `VIEWING` 并调用 2800 ms `view_time`，丢失旧版/原型的 700 ms `error_display`。之后还无意义地走 350 ms 框收缩和 250 ms 线收缩，总反馈可能从约 900 ms 拉长到约 3.6 秒。
- `start_exit()` 声称允许在 `STACK_APPEAR` / `IMAGE_APPEAR` 状态触发，但状态机没有这两个状态对应的退出转换；此时 `transition()` 返回 False，粘贴或关闭 holding 可能无法让动画退出。
- `spring_ease` 错接已用运行结果证实：入场调用返回 0；退场调用触发 `ZeroDivisionError`。这是运行时错误，静态编译无法发现。
- 当前源码可通过 `compileall`，`git diff --check` 未见空白错误。
- 当前 `dist/DoesCtrlCWork.exe` 为 47,954,729 bytes（约 45.7 MiB），与用户描述一致。
- Ctrl+V 逻辑优先让任何活动反馈退场并直接 return，并不只限 holding 模式；若状态转换无效，可能既不退场也不显示绿色 paste 提示。
- 可执行文件归档证据显示体积主因非常具体：除必要的 QtCore/Gui/Widgets 外，还被收集了 Qt6Qml、Qt6Quick、Qt6Pdf、Qt6VirtualKeyboard、Qt6OpenGL、软件 OpenGL (`opengl32sw.dll`) 及大量无关平台/图片/TLS 插件；这些并非当前 QWidget/QPainter 功能显式使用。
- 仅归档中几个明显可疑的大项压缩后就约占：Qt6Quick 2.9 MB、Qt6Qml 2.1 MB、Qt6Pdf 2.46 MB、opengl32sw 7.64 MB，合计约 15 MB。先做 PyInstaller 排除/最小 Qt 插件实验，比立刻重写成本低得多。
- Python 运行时本身在归档中压缩后约 2.7 MB，真正主导 45.7 MiB 的是 Qt 及其误收集模块，而不是 Python 语法或业务代码。因此“把少数核心函数换成 C++/pybind11”几乎不会显著减小最终 exe，仍会携带 Python+PySide6+Qt。
- 现有 `PLAN_CPP_HYBRID.md` 把 MIME 解析和 spring 计算列为高收益 C++ 项，但代码证据不支持这一优先级：MIME 查询只在 Ctrl+C 后短时执行，spring 每帧只是少量浮点运算；当前瓶颈更可能是高频常驻轮询、每帧图片缩放/QPixmap 转换以及错误的状态/时序。
- README 将项目称为 lightweight，但当前打包包含约 15 MB 可疑 Qt 组件；在优化发布管线前这个产品表述容易与用户感知不一致。
- Windows 原生正确路径是事件驱动：给隐藏窗口调用 `AddClipboardFormatListener`，接收 `WM_CLIPBOARDUPDATE`；再用 `GetClipboardSequenceNumber()` 作为系统级版本号，而不是自行对文本片段做 fingerprint。微软文档明确说明序列号在剪贴板内容变化/清空时递增。
- 如果产品承诺的是“这次 Ctrl+C 是否成功”，需把低级键盘事件当作一次 pending intent，把之后的 `WM_CLIPBOARDUPDATE`/sequence 增量当作成功确认；超时才显示失败。如果产品只承诺“剪贴板发生了变化”，则完全不需要全局 Ctrl+C hook。
- `WH_KEYBOARD_LL` 是 Windows 官方支持的低级全局键盘 hook，但微软也强调全局 hook 是共享资源，应限制在专用场景并及时移除；因此回调只记录 intent/时间戳，不能在 hook 内做 MIME、网络或图片工作。
- C# self-contained single-file 同样会携带 .NET runtime，官方文档明确提示这种文件会较大；不能假设“换 C# 自动变成几 MB”。framework-dependent 会小，但要求目标机安装匹配 runtime。
- .NET trimming 可减小自包含体积，但反射/部分桌面框架存在兼容风险，不能在没有发布测试矩阵的情况下把它视为免费优化。
- Qt 官方当前推荐可尝试 `pyside6-deploy`（Nuitka 封装），并提供排除未使用 QML plugins、关闭 Qt translations 等配置；这与本项目归档中误带 QML/Quick/PDF 的证据高度吻合，可作为不重写的第二条打包实验线。
- 状态机小测试证实：ERROR/PASTE 的 `done_error_paste` 确实进入普通 VIEWING；`DOT_APPEAR` 和 `IMAGE_APPEAR` 收到 `exit_no_stack` 均返回 False。相关问题不是推测，而是可重复的状态表缺口。
- 新重构名为“统一动画引擎”，但单个 FeedbackWidget 仍同时持有 PropertyEngine timer、stack timer、text scramble timer、image scramble timer、view timer、holding timer；加上 MouseTracker 两个常驻 timer，活动期仍存在多个独立时钟。模块拆分了，时钟并未真正统一。
- 图片动画的 QPainter 路径每帧重新做 QImage 缩放、像素化二次缩放、QPixmap 转换；堆叠缩略图也逐帧缩放/转换。多图动画时这比 Python spring 数学更可能造成主线程掉帧，应缓存最终 pixmap 与有限级别的像素化帧。
- 异步图片 worker 还有并发/顺序风险：`as_completed` 按下载完成顺序追加，可能打乱原图片顺序；`quit()` 不会主动中止自定义 QThread.run 内的 ThreadPool 下载；共享 `_worker_existing_images` 可能被下一次复制覆盖；初始已有图片又在 `images_updated` 中合并后追加，存在重复图片风险。
- 当前未暂存范围在本轮开始前只包含 planning711 文档；动画、状态机、鼠标和渲染器仍是审查时的待修版本。
- P0–P2 实施范围明确为：P0 状态/时序错误；P1 scramble、图片 reveal 与退出路径；P2 单一活动期时钟、按需鼠标追踪、图片/缩略图缓存。剪贴板事件重构和打包瘦身不在本轮实施范围。
- P0–P2 首轮实现已完成：状态机新增 PULSE 短路径和中途退出转换；PropertyEngine 改为 `QElapsedTimer + PreciseTimer`，作为窗口活动期唯一 frame clock；FeedbackWidget 取消三个独立逐帧 QTimer；MouseTracker 取消内部双定时器并由窗口 `frame_tick` 推进。
- 图片路径已在图片更新时缓存 25 个像素化 reveal 帧、主图和堆叠缩略图；每次 paint 不再缩放 QImage 或创建 QPixmap。
- 静态编译、spring 数值检查和状态机 smoke test 已通过；`rg` 确认 FeedbackWidget/MouseTracker 不再保留旧的 stack/scramble/image/poll/update timer。`ui/scramble_text.py` 仍是未接入的旧独立组件，不参与 FeedbackWidget 动画。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 暂不实施修复 | 本轮范围是检查、分析和计划；先保护用户未暂存改动 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 根目录不是 Git 工作树 | 检查隐藏目录和子目录后，在实际仓库根运行 Git |
| 更新规划文档时补丁上下文不匹配 | 重新读取文件并按实际表格位置拆分补丁 |

## Resources
- `dose-ctrlc/core/mouse_tracker.py`（IDE 当前文件）
- `TMP`（用户说明为 Google AI Studio 的动画原型）

## Visual/Browser Findings
- 待检查本地原型资源后补充。
