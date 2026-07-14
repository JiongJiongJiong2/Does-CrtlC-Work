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
- Phase 7 的现有实现确认：`ClipboardMonitor` 仍使用 `keyboard` 触发后 0/40/120/260ms 轮询，并依赖 pyperclip 初始化文本；图片 worker 以完成顺序收集 future、共享已有图片字段，并以 `quit()/wait()` 尝试停止。这正是本轮需要替换的路径。
- Phase 7 实施决策：`QClipboard.dataChanged` 负责事件触发，Windows 上 `GetClipboardSequenceNumber` 负责去重；Ctrl+C 只记录 pending intent 并以单次 confirmation timeout 判断未确认。事件后若 MIME 暂不可读，允许有限次、与该事件绑定的短暂重试，但不再使用内容 fingerprint 或周期轮询。
- Phase 7 首轮代码已替换 ClipboardMonitor：去除 pyperclip 与 fingerprint 轮询，依赖项同步移除；worker 使用 cancellation event、request ID、顺序索引和独立 worker 集合，避免上一请求结果污染当前反馈。
- 静态编译、ClipboardMonitor import 与 `git diff --check` 已通过；检索确认旧 fingerprint/retry/same-content 路径已不存在，新的 Qt 事件、Windows sequence 和 confirmation timeout 已接线。
- Phase 7 测试结果：完整离屏测试 12/12 通过，覆盖 P2 空闲时钟停止、MouseTracker 无后台 timer、QClipboard 事件发射、Windows sequence 去重模拟、pending Ctrl+C 确认、worker 顺序与取消。真实 Windows 桌面录屏/CPU 基线仍需手动执行。
- 中文卡顿与“不原生”观感的直接代码原因位于 `ContentBox.paint`：每次 paint 创建 `QFont("Cascadia Code", 10)`，强制 Monospace，再加入 2px 绝对字距；中文 glyph 多数会走 fallback 字体，而混合的中文/英文/Unicode block 会在同一帧产生更多 glyph run 与 shaping 工作。
- 内容框宽度在 FeedbackWidget 中使用 `len(text) * SIZES['char_width']`（9.5px）估算，完全不等同于 CJK、emoji 或 fallback 后字体的真实 advance；可能导致框宽跳变、裁剪或空白过大。
- 中文 scramble 期间仍每 16ms 构造完整随机字符串并 `drawText`；即使只有 45 个字符，fallback、字形布局和每帧新建 QFont 会把这段 1 秒动画的主线程开销放大。应缓存文本样式，并把随机字面更新与 60fps 窗口运动解耦。
- 离屏 Qt 字体查询没有解析出可靠 family（所有候选 `exactMatch=False`），不能据此决定目标机字体；真实 Windows 上需要按优先级验证 `Segoe UI Variable` / `Microsoft YaHei UI` / `Microsoft YaHei` 的可用性和实际观感。
- Phase 8 实施设计：新增 `TextStyleResolver` 缓存脚本分类后的 QFont/QFontMetricsF；FeedbackWidget 在初始化时依据真实 metrics 省略过长文本并计算目标宽度；ContentBox 接收缓存样式与最终 `QStaticText`，不再在 paint 时创建字体；scramble 字符串仅每 33ms 更新，窗口帧时钟维持 60fps。
- Phase 8 实施完成：`ui/text_style.py` 按 CJK/emoji/Latin 解析并缓存 QFont/QFontMetricsF；中文使用 Windows UI 字体候选且 0 字距，Latin 保留轻微 0.5px 代码字距。FeedbackWidget 以真实 advance 宽度和省略文本创建目标宽度/最终 QStaticText，ContentBox 仅绘制缓存对象；scramble 刷新间隔为 33ms。
- 离屏测试目前覆盖 CJK、混排、emoji 样式选择，真实 metrics 宽度，33ms 节流，长中文省略和 QStaticText 绘制。真实 Windows 字体实际解析和视觉/帧耗时仍需人工验收。
- P8.1 复查确认：33ms 的 scramble 字面刷新约为 30fps，而 PropertyEngine 仍以约 60fps 推进窗口；两套节奏不同会使 ASCII block 看起来慢半拍。旧循环每次还为整段文字重新随机，导致噪声跳变过大。修复改用持久化字符缓冲：已解码字符只写入一次、前沿 4 个 block 每帧更新、远端噪声每帧只轮换有限字符；刷新间隔改为 16ms。
- Phase 10 打包审计（2026-07-13）：当前 `dist/DoesCtrlCWork.exe` 为 47,954,729 bytes（45.73 MiB），PyInstaller onefile CArchive 显示它包含 Python 3.14 runtime、PySide6/Qt 与插件。代码只导入 QtCore、QtGui、QtWidgets，却被打入 Qt6Network、Qt6OpenGL、Qt6Pdf、Qt6Qml、Qt6Quick、Qt6Svg、Qt6VirtualKeyboard、全部翻译和大量非 Windows 平台/图像/TLS 插件；`.spec` 的 `excludes` 为空，正是误收集的直接原因。
- 主要未压缩体积项包括：`opengl32sw.dll` 20.6 MiB、Qt6Core 10.0 MiB、Qt6Gui 9.1 MiB、Qt6Quick 6.3 MiB、Qt6Widgets 6.3 MiB、Qt6Qml 5.1 MiB、Qt6Pdf 4.4 MiB、Python runtime 6.5 MiB。前五个 Qt 非必需 DLL（Qml/Quick/Pdf/VirtualKeyboard/OpenGL）与软件 OpenGL 是第一轮排除目标；需通过构建后在干净 Windows 上运行托盘、复制文本/图片、网络图片、图标和高 DPI 验收。
- Markdown 盘点：根目录 `PLAN_CPP_HYBRID.md`（39.5 KB）已与当前“不做 Python+C++/C# 迁移”的决定冲突；`DEVLOG_STACK_FEATURE.md`（7.3 KB）是历史实现日志。当前结论在 `docs/planning711/PROJECT_REVIEW.md`，计划/发现/进度在同目录；应增加 `docs/README.md` 作为唯一导航，并把两份历史 Markdown 移到 `docs/archive/` 保留而非删除。
- Phase 11 基线（2026-07-13）：在新建 `.venv`（Python 3.14.4、PySide6 6.11.1、PyInstaller 6.21.0）中用当前 `DoesCtrlCWork.spec` 构建成功，输出 `packaging-artifacts/dist-baseline/DoesCtrlCWork.exe` 为 47,966,119 bytes（45.74 MiB），比旧包略大 11,390 bytes。新包告警中没有 `pyperclip`，证明旧包确实过时；仅升级 PyInstaller 不产生体积收益。
- 新基线仍自动处理了 `hook-PySide6.QtNetwork.py`，并收集 Qml/Quick/Pdf/VirtualKeyboard/OpenGL/Svg 等 DLL。PyInstaller 的默认 Qt hook 会根据动态依赖递归收集，因此 `Analysis.excludes` 不能单独保证二进制 DLL/插件被移除；需在受版本控制的 spec 中对 `a.binaries`/`a.datas` 执行明确过滤，并通过打包后验证。
- Phase 11 v2 结果：`DoesCtrlCWork.spec` 同时使用 `Analysis.excludes`（阻止无用 PySide6 模块）和对 `a.binaries`/`a.datas` 的目标路径过滤（移除递归带入的 DLL、插件和翻译）。保留 `qwindows`、QtCore/Gui/Widgets、QtNetwork、图片 GIF/JPEG/WebP/ICO 与所有业务依赖。v1 为 35,929,830 bytes；加入 `opengl32sw.dll` 排除后 v2 为 28,288,775 bytes（26.98 MiB），相对基线减少 19,677,344 bytes（18.77 MiB，41.0%）。
- v2 CArchive 确认无 Qml/Quick/Pdf/VirtualKeyboard/Svg/OpenGL/翻译、低风险插件和 `opengl32sw.dll`；离屏回归 15/15 与冻结包 3 秒启动 smoke test 通过。真实桌面的 clipboard 图片格式、托盘、高 DPI 与软件 OpenGL 回退仍是发布前手动验收项。
- Phase 11 交付性发现：原 `.gitignore` 的 `*.spec` 规则使 `DoesCtrlCWork.spec` 不受版本控制；已为该唯一标准构建规则增加否定白名单 `!DoesCtrlCWork.spec`。没有此修复，其他机器会回退到无裁剪的临时 spec，瘦身结果不可复现。
- Phase 11 v3 结果：代码不 import QtNetwork，网络图片下载使用 Python 标准库 `urllib`；因此在 v2 上排除 `Qt6Network.dll` 与 `QtNetwork.pyd`。产物为 27,163,975 bytes（25.91 MiB），相对基线减少 19.84 MiB（43.4%），再比 v2 减少 1.07 MiB。归档未包含 QtNetwork 或此前排除项，15/15 离屏测试和 4 秒冻结启动 smoke test 通过；真实桌面验收仍是发布门槛。
- Phase 12 审查：`main._on_paste()` 对任意活动反馈调用 `start_exit()`，尽管注释只说 holding；普通复制后 Ctrl+V 因而没有绿色 paste 提示。Holding 由全局快捷键 Ctrl+V 结束，语义只能是“检测到 Ctrl+V 意图”而不是系统级“粘贴成功”。原托盘使用原生 `QMenu`、灰色状态行和命令式“切换”动作，既没有可见 checked 状态，也无法可靠实现圆角深灰/黄色开关视觉；需要改为自绘 `Qt.Popup` 并使用持久化状态。
- Phase 12 实施：新增 `ui/tray_menu.py` 的无边框 `Qt.Popup`，用逻辑像素与应用默认字体跟随 Windows DPI；面板为紧凑圆角深灰，含黄色 Apple 风格开关以及 `EN`/`中` 语言标识。`QSettings` 保存 feedback、holding、language 三个状态。`FeedbackWidget.is_holding_copy` 把 Ctrl+V 退场限定到 Holding COPY，普通提示则改为绿色 PASTE。离屏 18/18 测试通过；真实 Windows 仍需确认托盘右键激活、位置、多显示器和 100/125/150% DPI 观感。
- Phase 13 发现：Windows 的隐藏图标溢出页由 Explorer 进程管理；它收起时，不保证向应用的 `Qt.Popup` 发送 `WindowDeactivate`，因此只在 popup 本身安装 event filter 会留下悬浮面板。应监听应用级 deactivation，并在 popup 可见期间以低频、边沿触发方式识别 Windows 鼠标在面板外的点击；这样不会引入常驻轮询，也能覆盖点击任务栏/隐藏图标箭头导致的溢出页收起。
- Phase 13 实施：`TrayMenuPopup` 同时监听自身与 QApplication 的 deactivation；显示时启动 40ms 的可见期定时器，借助 Windows `GetAsyncKeyState` 只在新的左/右/中键按下沿且指针位于面板外时隐藏。`hideEvent` 立即停止计时器，因此没有后台常驻轮询。新增测试覆盖面板外按下沿会收起、持续按住不会重复判定；离屏完整套件 19/19、`compileall` 与 `git diff --check` 通过。Explorer 的实际溢出页行为仍须在 Windows 任务栏人工验证。
- Phase 14 调查：Qt 的标准 `QCursor` 通常不能通过 `pixmap()` 得到系统光标位图；Windows 应使用 `GetCursorInfo → GetIconInfo → GetObject` 取得当前 HCURSOR 的位图尺寸和 hotspot，并释放 GetIconInfo 创建的 HBITMAP。`SM_CXCURSOR/SM_CYCURSOR` 只是 nominal size，不能独立代表第三方/辅助功能光标。Win32 物理像素必须除以鼠标所在 QScreen 的 devicePixelRatio 后再参与 QWidget 布局。
- Phase 14 布局发现：如果逐个放大 `SIZES`、字体和图片常量，ContentBox、ImageRenderer、StackLayer 与固定 DOT 坐标会产生多套坐标系；统一在 FeedbackWidget 的 QPainter 入口做逻辑坐标缩放更安全。但当前 `StackLayer.paint()` 使用 `painter.setTransform(transform)` 覆盖已有变换，会抹掉外层 scale，必须改为组合变换。窗口固定尺寸、鼠标热点锚点和 screen-edge clamp 也必须使用同一个比例，否则仍会裁剪或错位。
- Phase 14 实施：新增 `core/cursor_metrics.py`，Windows 每次创建反馈时读取一次 HCURSOR，按当前屏幕 DPR 换算并生成最大 1.50 的稳定档位和最大 72 DIP 的偏移；非 Windows/失败回退 1.00。FeedbackWidget 的窗口、QPainter、DOT hotspot 与 mouse offset 共用相同比例，位置按目标屏幕 availableGeometry 约束；StackLayer 改为组合 transform。默认本机实测 32×32 DIP → 1.00/16px，行为不变。完整离屏测试 25/25、Qt 1.5 scale 专项通过、`compileall` 与 `git diff --check` 通过；1.5 倍离屏预览确认文字/图片/堆叠层相对位置一致。真实第三方 cursor、辅助功能最大档、多屏异 DPI 仍需人工视觉验收。
- Phase 15 发现：Windows“设置 → 辅助功能 → 鼠标指针和触控 → 大小”对应的显示尺寸不能只依赖当前 `HCURSOR` 的位图。现有实现只读取该位图，若 Windows 对同一 cursor 资源按辅助功能设置进行显示缩放，仍会得出 32×32，因而 UI 和偏移均保持默认。本机当前 `CursorBaseSize=32`、`SM_CXCURSOR/SM_CYCURSOR=32`，属于默认档，不能复现用户设置的大尺寸；读取时应将 `HKCU\Control Panel\Cursors\CursorBaseSize` 作为 Windows 用户设置的补充，并取它和实际资源尺寸中的较大者。Microsoft 的 `UISettings.CursorSize` 也公开了 app-view cursor size，但项目没有 WinRT Python 绑定；读取同一用户设置可保持本项目轻量且无需新依赖。
- Phase 15 位置结论：先前 72 DIP 偏移上限不足以越过 96/128 DIP 的大鼠标，理论上即便尺寸检测成功仍可能遮挡。UI 内容缩放保留 1.50 上限，但鼠标避让偏移应以 cursor hotspot 到右/下边缘的有效尺寸加间隙计算，并单独在 160 DIP 限制；窗口边缘仍由 available geometry clamp 兜底。
- Phase 16 布局发现：反馈 QWidget 的最小透明画布为 500×180，而纯文本的可见内容通常只到约 33px 高；用画布做 clamp 会在底边提前停住约 147px，右边也会提前停住透明宽度。改为以内容的实际 right/bottom bounds 停靠：底边允许透明尾部越出屏幕、仅将可见内容留在安全边距内；右边切换镜像方向，将窗口右边放在安全边距上。离屏镜像预览还发现 `ContentBox` 的第二段黄线仍以 `box_x` 绘制，导致镜像时左侧多出黄线；两段竖线均应以 `dot_cx` 为轴。
- Phase 16 视觉验证：右侧离屏预览确认黄点与唯一黄线处于画布右端，文本保持未翻转并向左排布；离屏环境缺少 Windows 字体时文本显示为方框字形，但不影响锚点、镜像方向与重复黄线检查。
- Phase 17 本地审查：`FeedbackWidget.move_to_position()` 已使用鼠标所在屏幕的 `QScreen.availableGeometry()`，因此固定显示任务栏通常会通过 work area 被排除；自动隐藏任务栏弹出时若 available geometry 仍接近整屏，当前 12 DIP 底边停靠会落在任务栏区域上。需要增加“当前任务栏可见边界”补充来源，但只应在反馈活动且接近底边时读取，避免常驻 Explorer 轮询。
- Phase 17 帧链路：`PropertyEngine` 已使用 `Qt.PreciseTimer`，但 interval 固定为 16ms，理论上限约 62.5Hz；同一 tick 依次做属性、文字/图片/堆叠推进、`QCursor.pos()`、spring 积分、顶层透明 QWidget.move 和 update。120/144Hz 屏幕会直接感知为半刷新率，spring 近临界阻尼与最终整数窗口坐标还会造成“像掉帧”的滞后/量化感。Qt 官方明确警告不要用 `QScreen.refreshRate()` 配合 timer 驱动动画，建议使用 `QWindow::requestUpdate()`；但将现有 QWidget/QPainter 架构迁移到 requestUpdate 驱动超出小项目必要复杂度。推荐保留 16ms 视觉动画，另设仅在反馈活动期运行的 8ms 精确定时器，只做 cursor 采样、spring 和顶层窗口 move，不触发额外 paint；反馈结束立即停止，保留空闲零轮询。
- Phase 17 官方边界：Qt 定义 `availableGeometry` 为排除任务栏/系统菜单等窗口管理器保留区，适合固定任务栏；Microsoft `ABM_GETSTATE` 可确认自动隐藏状态，`ABM_GETAUTOHIDEBAREX` 可按指定显示器和边缘取得 autohide appbar HWND。因此 Windows 补充路径可以只针对 autohide：以 Qt work area 为基础，在鼠标/反馈接近底边时查询该 HWND 的当前矩形，取任务栏上沿与 Qt bottom 中更保守的边界。
- Phase 17 本机证据：当前 `DISPLAY1` 报告约 165.019Hz、DPR 1.5，Qt `geometry` 与 `availableGeometry` 均为 1707×1067，说明当前 Windows 没有为任务栏持续保留 work area，符合自动隐藏任务栏场景。现有 16ms 位置更新只有约 62.5Hz，不到屏幕刷新率的 40%，用户感知到低帧率具有直接证据；无需先归因于 Python 性能不足。
- Phase 17 API 取舍：只读 `FindWindowW("Shell_TrayWnd")` 在当前 Windows 会话返回 0，说明不应依赖 Explorer 私有窗口类名。正式实现用 `ABM_GETAUTOHIDEBAREX` 的显示器矩形与 `ABE_BOTTOM` 获取 HWND，再用 DPI-virtualized `GetWindowRect` 读取当前屏幕坐标；只查询、不注册 appbar、不改变自动隐藏状态。若 Win32 查询失败，回退 Qt work area，并仅在指针进入底部激活带时采用保守任务栏高度，避免永久抬高内容。
- Phase 17 推荐最小状态：`normal` 使用 `availableGeometry.bottom`；`autohide-hidden` 使用屏幕 bottom；当 appbar rect 实际进入当前屏幕时，`autohide-revealing/visible` 使用 `min(Qt bottom, taskbar rect.top)`。读取复用活动期 8ms 位置 tick，且仅在反馈已底部停靠或鼠标距底边约 96 DIP 内执行；任务栏矩形连续变化就直接贴合，若真实 Windows 验收发现只在动画末尾跳变，再增加约 80–120ms 的单一边界插值，不预先注册 AppBar 通知窗口。
- Phase 17 实施：新增 `core/taskbar_boundary.py`，固定任务栏继续信任 Qt work area；自动隐藏任务栏通过公开 `ABM_GETAUTOHIDEBAREX + GetWindowRect` 读取当前底部矩形，再按 native monitor 与 Qt screen 高度比换回逻辑坐标。隐藏状态仅剩不超过 4 DIP 激活条时仍使用屏幕底边，滑入后改用任务栏上沿。调用只发生在反馈可见且内容即将底部停靠或鼠标进入底部 96 DIP 时；失败/非 Windows 直接回退 Qt，不注册 appbar、不写设置。
- Phase 17 跟随实施：`MouseTracker` 现在拥有活动期 8ms `PreciseTimer` 与 `QElapsedTimer`，仅做 cursor 采样、真实 dt spring 积分和窗口位置通知；PropertyEngine 仍以 16ms 负责绘制。反馈结束、静默或退出均停止 motion timer；整数窗口位置未变化时跳过 `QWidget.move()`。这比把全部绘制提高到 125fps 更符合小工具的 CPU/流畅度平衡。
- Phase 18 托盘根因补充：Explorer 隐藏图标页可在没有新的鼠标按下沿、也不给 Qt 应用发送 deactivation 的情况下收起，Phase 13 的两条信号均无法覆盖。最小修复是在弹窗显示前用 `WindowFromPoint/GetAncestor` 捕获鼠标下方的小型顶层宿主，并在已有可见期 40ms timer 中检查 `IsWindow/IsWindowVisible`；通过窗口尺寸排除横跨屏幕的普通任务栏，不依赖 Explorer 类名。宿主消失就隐藏菜单；直接托盘入口没有小型宿主，继续使用原失焦/外部点击规则。
- Phase 18 真实 Windows 反馈推翻了第一版的充分性：外部点击和隐藏图标栏点击收起均正常，但无操作等待 Explorer 自动收起时菜单仍滞留。这说明捕获句柄可能被提升成长期存在的任务栏根窗口，或者 Windows 11 XAML 弹层收起后保留 HWND/WS_VISIBLE，仅停止实际合成；只判断 `IsWindowVisible` 不够。
- Phase 18 v2：用 `GetCursorPos` 的 Win32 原生坐标捕获托盘点击下方窗口（避免 Qt 逻辑坐标在 125/150% DPI 下喂给 `WindowFromPoint` 而命中错误位置），从命中的子窗口沿 `GetParent` 逐层筛选并按 native monitor 矩形保留尺寸最大的“小型弹层”，不再直接 `GetAncestor(GA_ROOT)`。呈现判断组合 `IsWindow/IsWindowVisible`、`DwmGetWindowAttribute(DWMWA_CLOAKED)` 与窗口矩形/虚拟桌面相交。微软文档说明 `IsWindowVisible` 主要反映 WS_VISIBLE 样式，而 `DWMWA_CLOAKED` 能报告 Shell cloaking，正好覆盖仍存在但用户不可见的弹层状态；API 失败仍选择不误关。
- Phase 19 跟随语义：横向不能只提高 stiffness，否则左右仍是同一种滞后且会同时改变原有拖拽手感。应以 cursor target 的移动方向分支：target 左移或静止时继续 spring；target 右移时将 current X 直接设为 target 并把旧 X velocity 清零。这样折返后的第一个右移像“鼠标推住内容框”，同时 Y spring、边缘停靠与绘制动画不变。
- Phase 20 托盘顺序：仅在 Explorer 已开始收起后再观察 HWND，无法严格保证自绘菜单先消失。改为两个前置路径：隐藏图标入口启动 1.6 秒的单次无交互 timer；若指针离开最初触发点且不在菜单内，16ms 可见期检查立刻隐藏。鼠标进入或点击菜单会取消单次 timer，避免妨碍实际操作；直接任务栏图标入口不受影响。仍保留宿主 DWM 状态检测作为兜底。
- Phase 20 真实反馈修正：1.6 秒预收起加上“从触发点离开即隐藏”会在用户从托盘图标移动到菜单的间隙抢先关闭，菜单不可操作。修正为 5 秒无交互 timer，且只有指针已经进入过菜单、随后再次离开时才执行外部预收起；进入菜单立即停止 timer。优先保证菜单可用性，保留 Explorer 宿主状态检测作为自动收起兜底。
- Phase 20 图片底边布局：图片不能只改成负 Y，否则会在透明 QWidget 顶部裁掉；也不能只移动图片而让旧的 visible bottom 继续参与 docking。底边停靠时按图片/堆叠高度下移 dot/content anchor，`image_base_pos` 改为向上放置，StackLayer 的 Y offset 同时反向，visible bounds 以内容框底部为准。这样主图和多图堆叠完整位于内容框上方，窗口仍用同一安全底边停靠。
- Phase 21 行业调研结论：托盘右键菜单属于 transient popup/menu，主流实现依赖 popup 自身的焦点、输入捕获和 light-dismiss 生命周期。正常语义是选择命令、按 Escape、点击外部或应用失去激活时关闭；不会因为鼠标离开或任意 5 秒无操作而自动关闭。
- Windows 官方 `TrackPopupMenu` 特别要求通知区菜单弹出前把 owner 设为前台窗口，否则外部点击后菜单可能无法消失；这说明可靠关闭的关键是正确的 owner/focus，而不是轮询 Explorer 隐藏图标窗口。Windows Flyout 文档也把外部点击和 Escape 定义为 light dismiss。
- Qt 官方路径是给 `QSystemTrayIcon` 设置 `QMenu`，并使用 `QMenu.popup()/exec()` 展示；`QMenu` 原生提供取消、失焦、键盘和 action 生命周期。`QWidgetAction` 可承载现有 Apple 风格开关与 EN/中控件，因此无需为了视觉设计继续维护独立顶层 QWidget。
- 当前 `TrayMenuPopup` 的 5 秒 idle timer、16ms `GetAsyncKeyState`/cursor polling、pointer-entered/departure 门槛，以及 Explorer host/DWM cloaking 检测互相叠加，形成多套关闭源。它们会制造“太快关闭”“不操作却残留”与时序竞争，并依赖非公开 Shell 呈现细节，属于根因而不是需要继续调参的边角问题。
- 推荐迁移为 `QMenu + QWidgetAction`：保留深灰、黄色、紧凑尺寸和圆角；普通退出项用 `QAction`。删除 idle/departure/Explorer host/DWM 逻辑，把关闭交给 QMenu。若像素级圆角在 Windows 主题下存在差异，优先保证菜单行为、键盘可访问性与稳定性，再用 stylesheet/QProxyStyle 微调外观。
- Phase 21 实施采用“单个 `QWidgetAction` 承载完整旧面板”而不是把每一行改成系统菜单项。旧面板的 210px 宽度、10/8px 内边距、2px 行间距、8px 圆角、颜色、字体、黄色 ToggleSwitch、EN/中布局和退出 hover 均原样保留；外层 QMenu 透明、无额外 margin/padding、无系统阴影并保留 frameless 外观。
- 标准生命周期现由 QMenu 处理：右键通过 `QSystemTrayIcon.setContextMenu()`，左键继续调用同一个 QMenu 的 `popup()` 并沿用原托盘锚点计算。开关和语言按钮作为嵌入控件点击后保持菜单打开；退出按钮先关闭菜单再发出退出信号。旧的 idle timer、鼠标按键轮询、pointer departure、Explorer HWND 和 DWM cloaking 路径已经全部删除。
- 离屏视觉检查得到 QMenu `210×104`、panel `210×104`、四边 contents margins 均为 0，圆角和原排版正常，没有平台菜单额外留白。离屏环境缺少 Windows 字体导致文字显示方框，与先前离屏预览一致，不是本次迁移回归；真实 Windows 仍需检查合成层圆角/边框和隐藏图标入口行为。
- Phase 22 真机反馈：Phase 21 修正了菜单自身的超时/外部点击规则，但右键打开后 Explorer 隐藏图标栏立即收起；其他常见托盘软件会让隐藏图标栏留在菜单后面，首次外部点击先关闭菜单，Shell flyout 随后再按自身延迟收起。
- 两个现象来自同一激活关系。当前 `main.py` 把 QMenu 交给 `QSystemTrayIcon.setContextMenu()`；Qt 文档说明该接口会在 context request 时自动弹出菜单，而 QMenu 本身继承 QWidget、作为顶层 popup 存在，并会隐式抓取鼠标。由此推断：该 Qt 顶层窗口成为新的激活 popup 后，Explorer 隐藏图标 flyout 因失活执行 light dismiss；一旦它已在菜单打开阶段收起，后续自然不可能出现分层关闭。
- Windows 官方 `TrackPopupMenu` 要求通知区菜单使用正确 foreground owner，以保证外部点击关闭；原生 HMENU 进入系统菜单模式，并不等同于一个普通的第三方顶层 QWidget。其他软件的具体实现不可一概而论，但常见路径是原生菜单或 non-activating flyout，因此能和 Shell overflow 暂时共存。这里属于从官方生命周期与用户实测做出的实现推断。
- 适合当前项目的最小修正：保留 Phase 21 的 QMenu + QWidgetAction 和全部视觉参数；取消 `setContextMenu(menu)` 的自动显示，重新监听 `ActivationReason.Context/Trigger` 并手动 `popup()`；在 Windows 创建菜单时设置 `WA_ShowWithoutActivating`。QMenu 继续利用 popup mouse grab 处理首次外部点击，不添加任何人为延迟。若真机证实 WA 属性仍不足，再单独试 `WindowDoesNotAcceptFocus`，但它可能牺牲 Escape/键盘导航，不能预先无条件启用。
- 精确复刻原生 HMENU 可以更贴近 Windows 系统菜单模式，但无法低成本保留当前完整自定义开关、语言控件和像素级面板；owner-draw HMENU 对这个小项目明显过度工程化，因此不列为首选。
- Phase 22 官方资料：Qt QSystemTrayIcon <https://doc.qt.io/qt-6.11/qsystemtrayicon.html>；Qt QMenu <https://doc.qt.io/qt-6/qmenu.html>；Qt window/widget attributes <https://doc.qt.io/qt-6/qt.html>；Microsoft TrackPopupMenu <https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-trackpopupmenu>。
- Phase 22 实施：`main.py` 现在保持 `tray.setContextMenu(None)`，在 `activated(Context/Trigger)` 中统一调用现有 `show_near_tray()`；`TrayMenuPopup` 在 Windows 构造早期设置 `WA_ShowWithoutActivating`，并继续使用 QMenu popup 的 mouse grab、Escape 与外部点击生命周期。完整 QWidgetAction 面板及其视觉参数完全未改。
- 本轮没有启用 `WindowDoesNotAcceptFocus`，因为它会明确阻止输入焦点，存在损害 Escape 和键盘导航的风险；只有真实 Windows 复验表明 `WA_ShowWithoutActivating` 仍不足时才进入第二层评估。也没有恢复任何 timer、Explorer HWND 或 DWM 逻辑。
- Phase 23 更正：用户要的不是“Shell overflow 收起后菜单跟随”，也不只是“菜单不抢激活”，而是菜单打开期间让 Windows 隐藏图标栏暂停自身 idle retract；只有选择菜单或点击外部后，菜单先结束，Shell 再按自己的短延迟结束。Phase 22 的 non-activating QWidget 让 Explorer 仍处于普通 flyout 空闲计时状态，因此不能满足目标。
- Win32 `GUITHREADINFO` 明确定义 `GUI_INMENUMODE`、`GUI_POPUPMENUMODE` 和 `hwndMenuOwner`；`TrackPopupMenu` 进入 modal menu loop 并产生 `WM_ENTERMENULOOP/WM_EXITMENULOOP`。Qt Widgets QMenu 官方文档则明确其继承 QWidget、是顶层 popup。由此可知，窗口激活标志无法把 Qt popup 变成 Windows 原生菜单状态。
- 为同时满足行为与视觉，Windows 路径采用 ctypes owner-draw HMENU：系统负责菜单 loop、外部点击、Escape 和 Shell 协调，项目只处理 `WM_MEASUREITEM/WM_DRAWITEM` 以复刻现有紧凑深灰/黄色 UI。保留现有 QMenu 作为非 Windows 和安全回退，不引入 pywin32、Qt Quick 或 Windows App SDK。
- Phase 23 实施新增 `ui/windows_tray_menu.py`：透明离屏 Qt Tool 只作为 Win32 owner/message sink，菜单本体由 `CreatePopupMenu/TrackPopupMenuEx` 创建；`WM_MEASUREITEM/WM_DRAWITEM` 负责 210px 等比例 DPI 尺寸、深灰背景、选中 hover、Segoe UI 文本、黄色/灰色圆角开关、EN/中选中层级和分隔线。命令返回后再发送 Qt signals，开关/语言操作也按标准菜单语义先关闭菜单。
- Windows 工厂现在返回 `WindowsNativeTrayMenu`，非 Windows或 ctypes 构造失败回退原 `TrayMenuPopup`；`main.py` 继续手动处理 Context/Trigger，`setContextMenu(None)` 避免 Qt 再弹出第二套菜单。首次真实预览进入了原生 loop 但暴露未声明 GDI argtypes 的 64 位句柄截断；补齐全部绘制签名后第二次真实预览无异常完成。
- 官方资料：Microsoft TrackPopupMenu <https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-trackpopupmenu>；Windows Flyouts <https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/dialogs-and-flyouts/flyouts>；Qt QSystemTrayIcon <https://doc.qt.io/qt-6.11/qsystemtrayicon.html>；Qt QMenu <https://doc.qt.io/qt-6/qmenu.html>；Qt QWidgetAction <https://doc.qt.io/qt-6/qwidgetaction.html>。
- Phase 24 根因：`ctypes.windll.user32` 返回的 API 函数对象在进程内共享。`ui/windows_tray_menu.py` 与 `core/taskbar_boundary.py` 分别把 `GetMonitorInfoW.argtypes[1]` 设为各自定义的 `POINTER(MonitorInfo)`；菜单初始化后覆盖了签名，反馈靠近右下角时另一结构体会被 ctypes 在调用 Windows 前拒绝，因 8ms 鼠标位置时钟而连续刷出 traceback。这不是任务栏 API 本身失败，也不是鼠标坐标越界。
- 修复统一使用 `c_void_p` 表达 Win32 输出结构指针，同时仍由各调用方创建布局正确、带 `cbSize` 的结构体；`GetWindowRect`/`SHAppBarMessage` 同样显式声明 64 位安全签名。任务栏读取额外捕获 `ctypes.ArgumentError`，保证辅助边界失败只回退 Qt `availableGeometry`，绝不打断鼠标移动链路。
- 原生 HMENU 的系统窗口默认外框没有复刻旧 QWidget 面板圆角。为保留真正的 Windows menu mode，不回退 QMenu；改为仅监听当前 UI 线程的 `EVENT_SYSTEM_MENUPOPUPSTART`，确认窗口类为 `#32768` 后设置 `DWMWA_WINDOW_CORNER_PREFERENCE`，并用 8 DIP `CreateRoundRectRgn` 保证裁剪。Hook 只在菜单打开期间存在。
- `TrackPopupMenuEx` 选择命令后必然结束本次原生 loop，因此语言项无法像 QWidget 子控件一样直接原地改字。轻量实现是在命令返回后同步更新语言/持久化 signal，并立即在相同坐标重新进入同一个 HMENU；用户不需要关闭后再次点托盘，其他开关和退出仍按正常命令语义关闭菜单。
- Phase 25 视觉取舍：退出操作不再显示“退出/Quit”文本，而是使用同一套线条语言绘制的电源符号；这样中英文宽度不变且不依赖 Segoe UI 是否包含特定 Unicode glyph。Qt 回退路径用抗锯齿 `QPainter` 圆弧和竖线，Windows 路径用 GDI 椭圆轮廓、擦除顶部缺口和竖线组合。
- 菜单宽度仍固定 210px，避免英文标签和开关位置横向重排；紧凑感通过垂直方向微调实现：Qt 面板上下边距 8→6、布局间距 2→1、行上下内边距 2→1；原生行高总和从 110→97 DIP。外轮廓圆角从 8→10 DIP，电源符号自身保持 16 DIP，避免“放大圆角”误伤控件比例。
- Phase 26 行业调研结论：Microsoft 通知区指南把上下文菜单的退出项明确写作 `"Exit"`，并说明它结束当前 Windows 会话中的程序、移除托盘图标；规范没有要求用电源图标替换该命令。对于小型通知区菜单，普通文本更符合可发现性、键盘访问和本地化。
- Microsoft 的 Windows 图标指南建议动作图标使用系统图标资源；Windows 11 推荐 `Segoe Fluent Icons`，其 glyph 属于私有使用区且不应直接当作普通行内文字。WinUI 紧凑按钮的行业模式是“图标隐藏文字 + tooltip/可访问标签”，而不是无标签图形命令。参考：[Notification Area](https://learn.microsoft.com/en-us/windows/win32/uxguide/winenv-notification)、[Icons in Windows apps](https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/icons)、[Segoe Fluent Icons](https://learn.microsoft.com/en-us/windows/apps/design/iconography/segoe-fluent-icons-font)、[AppBarButton](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.controls.appbarbutton)。因此本项目恢复 `退出/Quit` 文本是更稳妥的默认方案；未来若要图标化，应使用系统 glyph/资源并保留可访问名称，而不是继续维护两套自绘线稿。
- Phase 26 卡顿基线（项目 `.venv`、Qt offscreen、单反馈窗口）：文本动画 1.8 秒收到 113 帧，约 62.3 FPS；帧间隔均值 16.0ms、P95 16.78ms、最大 18.06ms，CPU 约 5.2%。图片+3 张堆叠收到 112 帧，约 61.9 FPS，CPU 约 19.0%，P95 17.11ms、最大 17.59ms。说明 16ms 视觉时钟是确定性的约 62.5 FPS上限，图片场景 UI 线程负担明显更高。
- 同一环境下鼠标跟随 8ms `PreciseTimer` 在 1 秒收到 124 次更新，约 123.9Hz；因此“跟随不连续”不是鼠标监听完全失效，而是视觉重绘仍以 16ms 驱动，并且在约 165Hz 屏幕上只覆盖约三分之一刷新节奏。真实 Windows 上还会叠加 DWM 合成、显示器刷新率、窗口移动与电源计划差异。
- 当前每个视觉 tick 都执行属性同步、文字/图片/堆叠推进、`QWidget.update()` 和透明窗口绘制；图片场景还包含缩放后的 pixmap 合成。建议后续只做小范围性能改进：先把视觉时钟从固定 16ms 改为活动期 8ms/自适应 tick，保留 8ms 位置跟随；再用 Windows 真机记录实际帧间隔与 CPU，暂不重写渲染架构。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Phase 17 使用公开只读 AppBar API 与双速时钟 | 不改变系统设置，在不重写 QWidget 渲染循环的前提下处理任务栏动画和高刷跟随 |

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
