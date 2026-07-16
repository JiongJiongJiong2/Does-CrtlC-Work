# Progress Log

## Session: 2026-07-11

### Phase 1: 仓库与变更盘点
- **Status:** complete
- Actions taken:
  - 读取并启用 planning-with-files 工作流。
  - 将用户的三个问题拆分为仓库、动画、核心逻辑、技术栈和路线图五个阶段。
  - 枚举项目文件，确认 TMP 是 React 原型、产品是模块化 Python 项目。
  - 尝试读取 Git 状态；发现当前工作区根目录不是有效 Git 工作树，已记录并调整调查路径。
  - 定位实际仓库为 `dose-ctrlc/`，确认未暂存范围集中在反馈窗口动画架构重写。
  - 阅读剪贴板、鼠标、入口、动画引擎、状态机、布局和打包配置，发现相同内容复制误判、弱 fingerprint、常驻高频鼠标轮询、固定 dt 等问题。
  - 对照 TMP React 原型与新旧反馈窗口 diff，发现 `spring_ease` 接口错接、文字解码算法改变、图片显现提速等具体动画回归。
  - 执行静态编译、diff 检查和 spring 数值验证；静态检查通过，但复现了堆叠退场除零异常。
  - 检查 PyInstaller CArchive、构建告警、现有 C++ 计划与 README，确认体积主要来自 Qt 误收集模块，并重新评估 C++ 混合方案的真实收益。
  - 查阅微软 Win32/.NET 与 Qt 官方文档，确认剪贴板事件驱动 API、系统 sequence number、C# 部署体积权衡及 Qt 官方部署优化路径。
  - 以离屏 Qt 小测试验证状态表缺口，并审查多计时器和逐帧图片处理路径。
  - 形成 `PROJECT_REVIEW.md`，包含结论、动画目标序列、核心架构、技术栈比较、分阶段计划和验收矩阵。
- Files created/modified:
  - `task_plan.md`（创建）
  - `findings.md`（创建）
  - `progress.md`（创建）
  - `PROJECT_REVIEW.md`（创建，最终审查报告）

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Python 静态编译 | `python -m compileall -q .` | 无语法错误 | 无输出，完成 | PASS |
| Spring 入场 | 当前调用 `spring_ease(0,1,0.5)` | 0~1 的中间进度 | 0.0 | FAIL |
| Spring 退场 | 当前调用 `spring_ease(1,0,0.5)` | 1~0 的中间进度 | ZeroDivisionError | FAIL |
| Git whitespace | `git diff --check` | 无 whitespace 错误 | 无输出 | PASS |
| ERROR 状态路径 | DOT_APPEAR + `done_error_paste` | 进入短时错误提示 | 进入普通 VIEWING | FAIL |
| 动画中退出 | IMAGE_APPEAR + `exit_no_stack` | 转入退场 | transition=False，状态不变 | FAIL |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-07-11 | 根目录执行 git status/diff/log 均提示不是 Git 仓库 | 1 | 检查 `.git` 和子目录，改在实际仓库根执行 |
| 2026-07-11 | `spring_ease(1,0,t)` 触发 ZeroDivisionError | 1 | 证实调用接口错配，列入动画 P0 根因 |
| 2026-07-11 | 规划文档补丁上下文不匹配 | 1 | 重新读取文件并拆分为精确补丁 |
| 2026-07-11 | 再次从工作区根调用 git status | 2 | 最终检查切换到实际仓库 `dose-ctrlc/` |

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Phase 5 已完成 |
| Where am I going? | 本轮分析与计划已交付；下一轮可按用户选择实施 Phase 1 |
| What's the goal? | 对三个核心问题做基于代码证据的审查并给出实施计划 |
| What have I learned? | 见 findings.md |
| What have I done? | 完成代码/构建/架构审查并产出 PROJECT_REVIEW.md；未修改产品代码 |

## Session: 2026-07-15

### Phase 31: Image-layout submenu and system-theme research
- **Status:** in progress; implementation started on 2026-07-16.
- 已建立研究范围：SVG + 文案的图片布局主项、悬停子菜单的圆角/关闭语义，以及深浅主题与 Windows backdrop 的可行性必须分别评估 Windows owner-draw `HMENU` 和 Qt 备用路径。
- 本机为 PySide6 6.11.1，确认具备 Qt 6.5+ 的 `QStyleHints.colorScheme` / `colorSchemeChanged`。该方案不需要触碰注册表，适合作为主题变化入口；Windows 原生菜单在每次打开时读取当前令牌，活动反馈窗口通过 theme-change 信号重绘。
- 官方资料确认 Windows 11 22621+ 对 transient window 提供 Desktop Acrylic 类型的 `DWMSBT_TRANSIENTWINDOW`；但当前 `HMENU` 是 GDI owner-draw，固定不透明背景刷会遮蔽 backdrop，不能把“真实毛玻璃”承诺给该路径。已记录为需要独立 flyout 才能可靠提供的可选增强。
- **Plan completed:** 主菜单改为 16 DIP 既有 Fluent 图标 + “图片布局”文案 + 当前值/箭头；使用真正 HMENU 子菜单承载“扇形/层叠”，由系统处理 hover、离开关闭和方向键，主/子圆角分别为 10/8 DIP。既有 SVG 仅作为设计源，运行时打包转换后的 ICO，不恢复 QtSvg。
- **Theme decision (clarified):** 菜单只跟随深浅色实色令牌；毛玻璃视觉仅用于鼠标旁文字框、图片占位和堆叠底板。第一阶段采用跨版本稳定的半透明 tint；真实 Acrylic 不纳入本轮基础实现，未来若独立反馈窗可安全使用 DWM backdrop，再按系统支持状态回退。
- **Quit adjustment:** Qt 底部内边距增加至 6 DIP；原生 HMENU 在 Quit 后增加 3 DIP 无 hover 的背景留白，使其在托盘底部锚定时上移但没有分隔线。
- **Implementation started:** 用户确认开始执行图片布局子菜单、Quit 底部安全留白以及系统深浅主题/反馈表面 tint。
- **Implemented:** 新增 `ui/theme.py`。Qt `QStyleHints.colorSchemeChanged` 现在驱动菜单实色主题与反馈绘制令牌；深色复刻原搭配，浅色为暖白/白灰半透明内容表面。`ContentBox`、`ImageRenderer` 和 `StackLayer` 所依赖的字典均随主题更新。
- **Implemented:** Windows 菜单的图片布局改为 16 DIP ICO + 文案/当前值/箭头父项，并使用 `MF_POPUP` 的扇形/层叠子菜单；子菜单从现有 WinEvent hook 获得较小 8 DIP 圆角。Qt 备用路径也改为单行图标入口与圆角子菜单。spec 仅新增两枚转换后的 ICO。
- **Implemented:** 原生 Quit 后追加 3 DIP 无 hover 背景留白，Qt 备用面板底边距为 6 DIP；不恢复任何横线。
- **Verification:** `theme-switch-ok`、`native-submenu-ok`、`python -m compileall -q config.py main.py ui`、`git diff --check` 均通过。仍待用户在真实托盘/隐藏图标栏入口进行视觉与 hover 验收。
- **Build note:** 运行 `pyinstaller DoesCtrlCWork.spec --noconfirm` 用于确认新增 ICO 收集时，在动态库扫描阶段超过 120 秒工具时限而被终止；尚未得到成功或失败的最终构建结论。本轮不重复相同长构建，保留为后续单独验证项。

### Phase 32: Configurable palette and bottom-boundary rebound
- **Status:** in progress; user requested implementation on 2026-07-16.
- 新需求取代自动跟随系统主题：菜单需要“经典深色 / 浅色玻璃 / 自定义”三级配色入口，所有反馈表面使用同一选择；同时调查任务栏已升起时自底边向上移动出现的内容框回弹。

### Phase 30: Tray menu information architecture and native lifecycle review
- **Status:** in progress; the compact layout pass is complete, while the image-layout interaction and no-flash architecture decision remain open.
- 用户反馈图片布局选择器视觉不协调、Quit 位置不自然，并观察到开关和其他状态项选择后整个菜单闪烁。
- 代码审查确认：原生菜单当前为 `TrackPopupMenuEx(... TPM_RETURNCMD | TPM_NOANIMATION ...)`，命令返回后通过 `while command in REOPEN_COMMANDS` 重新进入菜单。任何状态命令都会结束一次原生菜单会话；`TPM_NOANIMATION` 仅关闭系统菜单动画，不能避免原生窗口销毁与重建。
- 已将后续执行拆分为两层：先做无分隔线、14 DIP 左对齐、约 100 DIP 高的紧凑视觉重排，并把图片布局改成语义真实的一行当前值；若必须“点击后原地更新且完全无闪烁”，再单独迁移为可交互 flyout，并回归 Windows 隐藏图标栏的保持语义。
- **Implemented:** 已在 `ui/windows_tray_menu.py` 与 `ui/tray_menu.py` 移除 Quit 上方装饰线；标题、标签与 Quit 统一为 14 DIP 左边界。Windows 原生各行高度调整为 23/21/21/26/22 DIP（总计 113 DIP）；Qt 备用面板上下 margin 改为 4 DIP、行间距改为 0，离屏高度为 101 DIP。
- **Verification:** Qt offscreen 构建成功（固定面板宽度 210 DIP），`python -m compileall -q ui` 与 `git diff --check` 通过。

## Session: 2026-07-16 — Phase 32 palette and boundary continuity

### Completed

- Replaced `colorSchemeChanged` system following with persisted `QSettings` palette selection (`classic`, `light`, `custom`).
- Added the Colour submenu and platform custom colour dialog to both the Win32 owner-draw menu and the Qt fallback menu.
- Applied derived palette tokens to menu, feedback box, image placeholders, and image-stack surfaces; added subtle vertical edge softening to the content box.
- Fixed bottom-dock/taskbar boundary continuity and added a focused offscreen regression test.
- Verified with `python -m unittest discover -s tests -v`: 52 tests passed; `git diff --check` passed.

### Remaining manual acceptance

- Verify the native Explorer tray submenu, custom picker and raised/auto-hide taskbar movement on a real Windows desktop.

### Follow-up UI polish (2026-07-16)

- Switched the native layout parent row to the alternate `fluent_slide_multiple.ico` asset.
- Removed redundant layout/colour arrows from native and Qt menu presentations.
- Regression suite remains green: 52 tests passed.

### Icon transparency follow-up (2026-07-16)

- Removed the native layout icon's manually painted background tile; the icon now renders directly against the transparent/solid menu surface.
- Regression suite remains green: 52 tests passed.

## Session: 2026-07-16 — Phase 33 UI and rich-image follow-up

### Completed

- Removed the requested content-box top/bottom softening overlay while preserving the original horizontal reveal gradient.
- Replaced fixed white ICO rendering with the Windows Fluent `PhotoCollection` system glyph (`U+E7AA`), coloured from the active menu foreground. This removes the light-theme contrast failure and lets the spec stop bundling both layout ICO files.
- Changed native submenu selection text/marker from yellow to the palette title colour; hover remains neutral grey.
- Fixed custom-colour lifecycle by excluding `Custom…` from the native popup re-entry loop, closing the HMENU before the colour dialog opens, and assigning the dialog an application owner.
- Made cascade spacing progressive (later gaps wider) and capped the total image-group span to the text-content width when one exists.
- Fixed placeholder exit drawing to respect `vanish_ratio`, matching loaded-image shrink/fade behaviour.
- Updated README with the lean, spec-driven virtual-environment PyInstaller command and recorded that direct clipboard bitmap extraction is already first priority.

### Verification

- `python -m unittest discover -s tests -q`: 53 passed.
- `python -m compileall -q .` and `git diff --check`: passed.

### Pending desktop acceptance

- Check the native Fluent glyph on the actual Windows version(s), custom picker focus/dismissal, and cascade spacing against both short and long copied text.

## Session: 2026-07-12

### Phase 6: P0–P2 动画与运行时修复
- **Status:** complete
- Actions taken:
  - 用户决定继续 Python，实现 P0–P2，不做 Python+C++ 混合或 C#。
  - 已读取现有规划与审查证据，准备在不覆盖用户现有 UI 重构的前提下修复。
  - 确认当前 Git 改动仅为本轮更新的 planning711 文档，产品代码仍处于审查时记录的待修状态。
  - 完成 P0–P2 首轮代码修改：状态机、单调帧时钟、反馈窗口、鼠标追踪、图片缓存及动画时长配置。
  - 执行 `compileall`、state-machine smoke 与 spring smoke，均通过；`git diff --check` 通过。
  - 添加并执行 6 项 offscreen Qt 回归测试，覆盖 PULSE、运行中退出、spring、完整 copy 退场的 2px 线、图片 reveal/缩略图缓存和单时钟结构。
  - 在 `PROJECT_REVIEW.md` 写明已完成、未完成以及“不做”的架构决策。
- Files created/modified:
  - `docs/planning711/task_plan.md`（更新）
  - `docs/planning711/progress.md`（更新）
  - `tests/test_animation_runtime.py`（创建）

### Phase 7: P2 真实验证与 P3 剪贴板事件重构
- **Status:** complete
- Actions taken:
  - 用户要求继续 P2 剩余验证并开始 P3。
  - 计划采用 Qt 剪贴板事件为跨平台触发源，在 Windows 叠加系统 sequence number；保留 Ctrl+C 仅作为确认意图。
  - 已确认旧实现的轮询、pyperclip 初始化、worker 共享状态和完成顺序问题，准备整体替换 ClipboardMonitor。
  - 完成 ClipboardMonitor 首轮替换、配置与 requirements 清理；静态编译、import 和 whitespace 检查通过。
  - 添加 P3 事件链与 worker 测试，并补充 P2 空闲时钟/鼠标无后台 timer 测试；完整离屏套件通过 12 项。
  - P2 的真实 Windows 桌面 CPU、帧耗时与视觉录屏仍待手动验收；本轮完成的是可重复的结构与事件链验证。

### Phase 8: 中文排版与文本渲染性能（审查完成，待实施）
- **Status:** complete
- Actions taken:
  - 审查 ContentBox、FeedbackWidget、布局与旧 ScrambleText 的字体、字距、宽度和逐帧更新路径。
  - 确认 CJK fallback、固定字符宽度、每帧新建字体、60fps 全量随机文本是主要风险；离屏字体可用性查询结果不可靠，需真实 Windows 验收。
  - 开始实施：将新增文本样式解析器、真实宽度测量、静态最终布局缓存与 30fps scramble 文本节流。
  - 首次联合验证命令因 PowerShell 正则引号未闭合而失败；已记录，改用拆分命令验证。
  - 完成 `TextStyleResolver`、QFontMetricsF 宽度/省略、缓存 QStaticText、ContentBox 样式注入和 33ms scramble 节流。
  - 添加中文/混排/emoji、长中文省略和缓存布局绘制测试；离屏完整套件通过 15 项。
  - 真实 Windows 桌面字体 fallback、视觉与性能验收仍待手动完成。
- Files created/modified:
  - `ui/text_style.py`（创建）
  - `ui/components/content_box.py`（更新）
  - `ui/feedback_widget.py`（更新）
  - `config.py`（更新）
  - `tests/test_animation_runtime.py`（更新）

### Phase 9: P8.1 ASCII block 伪加载平滑度
- **Status:** complete
- Actions taken:
  - 用户反馈文字出现时 ASCII block 伪加载有轻微慢、卡顿感。
  - 确认原因是 33ms（约 30fps）文本刷新与 60fps 窗口帧不同步，且每次刷新会全量重随机整段文字。
  - 已改为 16ms 同频刷新和持久化字符缓冲：只写入新增的最终字符，前沿 block 与远端少量噪声增量变更，保留中文最终文本的 UI 字体路径。
  - 更新运行时测试，验证 16ms 刷新、缓冲长度和已解码前缀稳定；完整离屏测试 15/15 通过，`compileall` 与 `git diff --check` 通过。
  - 真实 Windows 桌面下的 ASCII block 观感、中文字体 fallback 和帧耗时仍需手动验收。
- Files created/modified:
  - `docs/planning711/task_plan.md`（更新）
  - `docs/planning711/findings.md`（更新）
  - `docs/planning711/progress.md`（更新）

### Phase 10: 打包瘦身审计与文档整理
- **Status:** complete
- Actions taken:
  - 用户要求调查 45 MB 打包体积、明确可做的瘦身措施，并整理 Markdown 文件。
  - 读取当前 PyInstaller CArchive：确认代码只使用 QtCore/Gui/Widgets，但产物收集了 Qml、Quick、Pdf、VirtualKeyboard、OpenGL、软件 OpenGL、翻译和大量无关插件；`.spec` 没有排除规则。
  - 盘点 Markdown：根目录的 C++ 混合计划和多图开发日志均为历史文档，当前结论和执行记录集中在 `docs/planning711/`，准备建立 docs 导航和归档目录。
  - 新增 `docs/PACKAGING.md`，记录 45.73 MiB 旧包的归档证据、可排除组件、28–35 MiB 的合理首轮目标、隔离环境基线构建和分组验收矩阵；明确当前 `build.bat` 与 spec 的产物名已分叉。
  - 新增 `docs/README.md` 作为唯一索引；根目录 `PLAN_CPP_HYBRID.md` 和 `DEVLOG_STACK_FEATURE.md` 移入 `docs/archive/`，README 改为链接到文档入口并移除已废弃的 pyperclip 描述。

### Phase 11: PyInstaller 瘦身实验
- **Status:** in_progress
- Actions taken:
  - 用户授权开始执行打包瘦身；采用“隔离基线 → 低风险裁剪 → 构建内容/大小对比 → 回归与桌面验收”的顺序。
  - 保留 `qwindows` 平台插件、当前图片相关路径和 `opengl32sw.dll`，直到前一轮裁剪证明稳定；不直接删除 Python 或 PySide6 安装目录中的文件。
  - 创建隔离 `.venv`；首次 pip 安装因沙箱网络策略（WinError 10013）失败，获得授权后成功安装 PySide6 6.11.1、keyboard 0.13.5、PyInstaller 6.21.0 及构建依赖。
  - 用当前 spec 成功构建 `packaging-artifacts/dist-baseline/DoesCtrlCWork.exe`：47,966,119 bytes（45.74 MiB）；新构建不含 pyperclip，但大小与旧包基本一致，确认需实施显式 Qt 收集裁剪。
  - 在 spec 固化 v1：移除翻译、QML/Quick/PDF/VirtualKeyboard/SVG/Qt OpenGL API、无关触摸/TLS/平台和部分图像插件；v1 为 35,929,830 bytes，减少 11.48 MiB（25.1%）。归档检查、15 项离屏测试和冻结包启动 smoke test 通过。
  - 在 v1 基础上单独移除可选 `opengl32sw.dll`；v2 为 28,288,775 bytes（26.98 MiB），相对基线减少 18.77 MiB（41.0%），冻结包启动 smoke test 通过。保留真实桌面功能/高 DPI 验收为发布前待办。
  - 继续单独验证 QtNetwork：应用网络图片路径使用 `urllib`，未 import QtNetwork；排除 `Qt6Network.dll` 与 `QtNetwork.pyd` 后 v3 为 27,163,975 bytes（25.91 MiB），相对基线减少 19.84 MiB（43.4%），比 v2 再少 1.07 MiB。归档检查、15 项离屏测试和 4 秒冻结启动 smoke test 通过。
  - 统一 `build.bat`、README 与 `DoesCtrlCWork.spec`；构建脚本不再安装全局依赖或生成名称分叉的 `DoseCtrlC.exe`。
  - 修复 `.gitignore`：为 `DoesCtrlCWork.spec` 加入白名单，使标准瘦身规则能够被 Git 提交和在其他机器复现。

### Phase 12: Holding 语义与自定义托盘面板
- **Status:** complete (真实 Windows 视觉/DPI 验收待发布前执行)
- Actions taken:
  - 用户要求修复反直觉的 Holding 逻辑，并将 Windows 托盘菜单改为极简深灰、黄色开关、圆角、小尺寸和 EN/中切换的界面。
  - 修复 `_on_paste`：仅 Holding 的 COPY 实例会在 Ctrl+V 后退场；普通 COPY 继续显示绿色 PASTE 提示。关闭 Holding 同样只退出该类型会话。
  - 使用 `QSettings` 持久化复制反馈、Holding 和语言；tooltip 显示当前开关状态，移除灰色不可操作的状态行。
  - 新增 `ui/tray_menu.py`：以 `Qt.Popup` 替代无法稳定自定义的原生 `QMenu`，提供圆角深灰面板、黄色 Apple 风格开关、`EN`/`中` 小标识和本地化按钮文本。
  - README 补充 Ctrl+Shift+H，并把 Holding 改为准确的“Ctrl+V 意图”语义。
  - 新增 Holding/托盘回归测试；完整离屏套件 18/18、`compileall` 和 `git diff --check` 通过。真实 Windows 托盘位置、右键激活与 DPI 视觉仍需手动验收。

### Phase 13: 托盘隐藏图标页收起联动
- **Status:** complete (待真实 Windows 隐藏图标页手动验收)
- Actions taken:
  - 用户反馈：Windows 右下角隐藏图标页收起后，自绘托盘面板仍停留在原位置。
  - 确认仅监听 popup 自身 `WindowDeactivate` 无法可靠获知 Explorer 溢出页关闭；新增 QApplication 级 deactivation 收起。
  - 在弹层显示期间启动 40ms 定时器，以 Windows 鼠标按键的按下沿判断面板外点击；点击任务栏、隐藏图标箭头或其它外部位置导致溢出页收起时，面板会立即隐藏。`hideEvent` 停止计时器，空闲期没有轮询。
  - 新增外部点击边沿测试，并更新旧语言控件断言以匹配 EN/中双标识；离屏完整测试 19/19、`compileall` 与 `git diff --check` 均通过。

### Phase 14: 鼠标尺寸自适应反馈 UI
- **Status:** complete (待真实 Windows 大光标、多屏与 DPI 视觉验收)
- Actions taken:
  - 用户要求把已调查的鼠标尺寸方案写入 Markdown 并实现，同时重点防止单独放大组件造成错位。
  - 新增 `docs/CURSOR_SCALING.md`，记录 Win32 HCURSOR 位图/hotspot、DPR 换算、1.00–1.50 分段比例、16–72 DIP 偏移和验收矩阵；文档索引已增加入口。
  - 新增 `core/cursor_metrics.py`：通过 `GetCursorInfo/GetIconInfo/GetObjectW` 获取当前 cursor，显式声明 64 位 handle 签名并释放 bitmap；每次反馈读取一次，无常驻 timer，失败/非 Windows 回退原尺寸。
  - FeedbackWidget 使用统一逻辑坐标：窗口尺寸与 QPainter 同比缩放，鼠标锚点使用 scaled DOT，位置约束在当前屏幕 availableGeometry；修复 StackLayer 覆盖外层 transform 导致堆叠错位的问题。
  - 新增 6 项 cursor scaling 测试，覆盖比例上限、偏移上限、非 Windows 回退、屏幕 clamp、默认尺寸不变以及 1.5 倍多图堆叠实际绘制。完整测试 25/25，Qt 1.5 scale 专项通过，静态编译与 whitespace 检查通过；本机默认 cursor 实测为 32×32 DIP、1.00 倍。
  - 生成 1.5 倍文字与多图堆叠离屏预览，确认各组件共享外层缩放后相对位置、圆角和堆叠偏移保持一致；离屏环境缺少项目字体时出现的方框字形不属于缩放回归。

### Phase 15: Windows 系统鼠标大小与反馈位置修复
- **Status:** complete (待真实 Windows 大鼠标手动验收)
- **Started:** 2026-07-14
- 用户在 Windows 设置提高鼠标大小后观察到反馈仍为原尺寸、与鼠标的相对位置也未改变。初步代码审查显示当前仅以 `GetIconInfo/GetObjectW` 读取 `HCURSOR` 位图资源尺寸；需确认 Windows 辅助功能设置是否在显示层缩放该资源，并补充独立的系统设置尺寸来源。
- **Completed:** 2026-07-14
- 新增 `CursorBaseSize` 读取：当系统辅助功能尺寸大于 `GetIconInfo` 得到的 cursor 资源尺寸时，等比例放大资源 footprint 与 hotspot 后再选择 UI 档位。普通或第三方资源本身较大时仍以资源尺寸为准。
- 反馈内容视觉尺寸继续封顶 1.50 倍；避让偏移改为超过 32 DIP 时移动到 cursor 右/下边缘外加间隙，单独封顶 160 DIP。这样 96/128 DIP 光标不会因内容封顶而仍压住反馈；靠近屏幕边缘继续由现有 clamp 约束整个窗口。
- 新增 Windows 设置覆盖资源尺寸的测试；`tests.test_cursor_scaling` 7/7、完整离屏回归 26/26、`compileall` 和 `git diff --check` 通过。本机当前 `CursorBaseSize=32`，native 检测为 32×32 DIP、1.00 倍与 16 DIP 偏移，默认外观不变。

### Phase 16: 可见内容边缘停靠与右侧镜像布局
- **Status:** complete (待真实 Windows 边缘停靠手动验收)
- **Started:** 2026-07-14
- 用户反馈底/右边缘会过早停止：现有 `clamp_window_position` 按完整透明 QWidget（文本反馈最小 500×180）做约束，而实际文本框只占画布左上角，因此提前留下大块不可见余量。目标改为：底边让可见内容底部保留少量间距并继续横向跟随；右边让黄点/黄线贴近右边安全边距，内容及渐隐方向镜像到左侧。
- **Completed:** 2026-07-14
- 新增纯函数 `visible_content_bounds` 和 `dock_feedback_position`：边缘判断以文本、图片与堆叠的可见 right/bottom bounds 为准；底边允许透明画布尾部越出可用工作区，使可见内容底部保持 12 DIP（按 UI scale 换算）间距，同时 X 坐标继续跟随。
- 右边触发后将画布右侧停在安全边距：`FeedbackWidget` 使用右侧 dot anchor，`ContentBox` 向左绘制并反向渐隐，文字右对齐但不镜像字形；图片与 StackLayer 同步向左展开。修复镜像时第二段黄线误画在左端的问题，黄点与唯一黄线现共用右侧 `dot_cx`。
- 新增底边横向跟随、右边停靠位置、右侧黄线、文字正常方向和图片/堆叠镜像的离屏测试；cursor scaling 专项 11/11、完整离屏回归 30/30、`compileall` 与 `git diff --check` 通过。生成并人工检查右侧离屏预览；真实 Windows 任务栏、双屏与边界切换手感仍需手动验收。

### Phase 17: 自动隐藏任务栏边界与鼠标跟随帧率方案
- **Status:** complete (待真实 Windows 任务栏动画手动验收)
- **Started:** 2026-07-14
- 当前固定任务栏可由 `QScreen.availableGeometry()` 规避；方案重点是自动隐藏任务栏从屏幕边缘滑出时的动态边界，以及固定 16ms 帧钟在 120/144Hz 显示器上的半刷新率观感。本轮只审查和制定最小实现路线，不修改产品代码。
- 官方资料确认 Qt work area 适用于固定保留区，并提供 `availableGeometryChanged` 信号；Windows 可用 `ABM_GETSTATE/ABM_GETAUTOHIDEBAREX` 识别指定显示器底边的自动隐藏 appbar。帧率路线修正为“16ms 视觉动画 + 活动期 8ms 位置跟随”，避免违反 Qt 对 refreshRate-driven timer 的警告，也不把 QWidget 架构扩张成新的渲染循环。
- 读取本机 Qt 屏幕信息（只读）：`DISPLAY1` 约 165Hz，geometry 与 availableGeometry 同为 1707×1067，DPR 1.5。该结果同时支持自动隐藏任务栏边界缺失与固定 16ms 跟随低于高刷屏观感两项诊断。
- 本机用私有窗口类名查找任务栏句柄失败，方案因此明确不用 `Shell_TrayWnd`；改用公开的 per-monitor `ABM_GETAUTOHIDEBAREX`。不注册 appbar、不监听全局 shell 事件、不写注册表或任务栏配置，只在反馈靠近底边的活动期读取当前矩形。
- **Completed:** 2026-07-14
- 新增 `core/taskbar_boundary.py`：固定任务栏沿用 `availableGeometry`；自动隐藏任务栏按当前 monitor 获取底边 appbar 的实时窗口矩形，将 native top 换算为 Qt 逻辑坐标。隐藏激活条不抬高反馈，任务栏进入屏幕后以其上沿作为停靠底边；调用失败安全回退。
- MouseTracker 从 16ms 绘制 tick 解耦，改为反馈活动期 8ms 精确位置 timer，以实际 elapsed 推进 spring；停止反馈时立即停表。FeedbackWidget 仅在接近底边时查询 taskbar，并在整数位置没有变化时跳过重复 move。
- 新增自动隐藏任务栏 visible/hidden strip、8ms timer 生命周期和 120ms 活动更新密度测试。专项 16/16、完整离屏回归 33/33、`compileall` 与 `git diff --check` 通过。真实 Qt Windows GUI 诊断在当前执行会话 exit 1 且无可靠输出，因此没有冒充手动验收；自动隐藏任务栏滑入/收起仍需桌面确认。

### Phase 18: 托盘隐藏图标页无点击收起联动
- **Status:** complete (v2 待真实 Windows 复验)
- **Started/Completed:** 2026-07-14
- Phase 13 的 application/window deactivation 与外部鼠标按下沿只能处理失焦/点击；Explorer 隐藏图标页无新点击自行收起时，两者都不会触发。
- `TrayMenuPopup` 现在在显示前捕获鼠标下方的小型外部顶层窗口，并复用现有仅可见期运行的 40ms timer 观察该宿主是否仍可见。宿主收起时菜单同步隐藏；横跨屏幕的普通任务栏不会被记录，且不依赖 Explorer 私有窗口类名。hideEvent 会停止 timer、清空按钮状态和宿主句柄。
- 新增“已捕获宿主不可见即关闭菜单”测试；首次单独运行暴露 Python 3.14 `unittest.mock` 未显式导入，修复后专项与完整套件均通过。
- **Real Windows feedback / v2:** 2026-07-14
- 用户确认点击外部与隐藏图标栏点击收起的时机已经正确，但无操作等待隐藏图标栏自动收起仍会留下菜单。第一版“句柄存在 + IsWindowVisible”因此判定为不足，未继续标作已验收。
- v2 使用 `GetCursorPos` 原生坐标捕获托盘点击下方窗口，避免高 DPI 下把 Qt 逻辑坐标错误传给 `WindowFromPoint`；沿父窗口链按 native monitor 尺寸选择最大的小型弹层而不是持久任务栏根窗口。呈现检查增加 `DWMWA_CLOAKED` 与窗口矩形/虚拟桌面相交，覆盖 Shell cloaking 和移出屏幕但保留 HWND 的路径。仍复用菜单可见期 40ms timer，无后台常驻工作。

### Phase 19: 水平单向拖拽/推动跟随
- **Status:** complete (待真实 Windows 手感复验)
- **Started/Completed:** 2026-07-14
- SpringAnimator 记录本帧 target 是否右移：左移/停止继续按原 stiffness、damping 和真实 dt 积分；右移立即把 current X 设为 target 并清空 X velocity。垂直 spring、8ms 活动期 timer、任务栏边界和右侧镜像均未改变。
- 新增纯 spring 回归：100→80 的第一帧必须仍位于 80–100 之间，验证拖拽滞后；随后 80→90 必须精确到 90 且速度归零，验证固定偏移推动。托盘 DWM 状态纯函数测试一并增加。
- 专项测试 18/18、完整离屏回归 35/35、`compileall` 与 `git diff --check` 通过。
- 在未打开隐藏图标页的当前桌面执行只读 native host probe，Win32 调用链正常返回 `None`（没有误把普通桌面/任务栏识别为小型弹层）。

### Phase 20: 托盘先收起顺序与底边图片上置
- **Status:** complete (待真实 Windows 复验)
- **Started/Completed:** 2026-07-14
- 用户明确要求菜单先于隐藏图标栏自动/点击收起。宿主失效检测只能在 Explorer 已经开始收起后运行，因此增加隐藏图标入口专用的 1.6 秒无交互单次 timer；鼠标进入或点击菜单会取消。可见期检测从 40ms 提升为 16ms，并在指针离开触发点、位于菜单外时抢先隐藏菜单，减少外部点击与 Explorer 收起的竞态。直接显示在任务栏中的图标不启动无交互 timer。
- 图片反馈处于底边停靠时，`bottom_dock_dot_y` 计算画布内锚点，主图用向上 `image_base_pos`，多图 StackLayer Y 方向反转。可见边界改以文本框底部为准，避免图片仍按下方布局参与计算导致提前停靠或裁剪。
- 新增托盘离开预收起/idle timer、图片上置纯布局和离屏渲染测试。完整离屏测试 39/39、`compileall` 与 `git diff --check` 通过。
- **Interaction correction:** 用户真机反馈 1.6 秒预收起过快，且指针从图标移动到菜单时会被 departure 检查误判为外部离开。改为 5 秒无交互 timer，并新增 `pointer_entered_menu` 门槛：只有鼠标进入菜单后再离开才预收起；进入/点击菜单立即取消 idle timer。

### Phase 21: 托盘菜单关闭语义行业调研与迁移
- **Status:** complete (自动化与离屏视觉检查完成，待真实 Windows 复验)
- **Started/Completed:** 2026-07-14
- 本轮按用户要求只调查与分析，没有修改产品代码。对照 Microsoft 通知区菜单/TrackPopupMenu、Windows light-dismiss flyout、Qt `QSystemTrayIcon/QMenu/QWidgetAction` 后，确认行业通用语义是由 transient popup 自己处理 owner、焦点和输入：选择命令、Escape、外部按下或失活时关闭；无操作、鼠标仍在外部或悬停离开本身不触发固定倒计时关闭。
- 当前自绘弹窗把 5 秒 idle、16ms 外部按键/指针轮询、鼠标进入后离开、Explorer 隐藏图标宿主和 DWM 状态共同作为关闭条件，导致多套状态机竞争。推荐下一步迁移为托盘原生 `QMenu`，用 `QWidgetAction` 保留两个黄色开关与 EN/中切换，用 `QAction` 承载退出，并删除所有 Explorer/idle/departure 猜测逻辑。
- 迁移后需真机验收：直接任务栏图标和隐藏图标入口、外部点击、Escape、键盘导航、开关点击后是否按产品预期保持或关闭、DPI/圆角与 Windows 字体渲染。本轮未运行代码测试，因为没有改变运行代码。
- **Implementation started:** 用户确认开始迁移，并要求 99% 保持现有窗口的深灰背景、黄色开关、圆角、紧凑排版与展示效果。实现将复用现有 ToggleSwitch/语言控件的布局参数，通过 `QWidgetAction` 放入标准 `QMenu`，只替换顶层弹窗生命周期。
- **Implementation completed:** `TrayMenuPopup` 现继承 `QMenu`，完整旧面板作为单个 `QWidgetAction` 嵌入，原 210px 宽度、圆角、颜色、间距、开关、语言控件和 hover 样式未改。右键交给 `QSystemTrayIcon.setContextMenu()`，左键仍使用原托盘相对位置调用 `popup()`；开关/语言操作保持菜单，退出按钮主动关闭。
- 删除全部 5 秒 overflow idle timer、16ms outside-click timer、`GetAsyncKeyState`、pointer departure、Explorer `WindowFromPoint` 宿主捕获和 DWM cloaking 判断。Escape 关闭、控件不误关、托盘持有 context menu 等专项测试通过。
- 离屏渲染测得 QMenu 与 panel 均为 `210×104`，contents margins 为 `0/0/0/0`，确认没有系统菜单边距改变排版。专项 3/3、完整回归 37/37、`compileall` 与 `git diff --check` 通过；真实 Windows 圆角合成、外部点击、隐藏图标入口与多 DPI 仍保留为最终手动复验。

### Phase 22: 隐藏图标栏共存与分层收起
- **Status:** complete (自动化完成，待真实 Windows 分层收起复验)
- **Started/Completed:** 2026-07-14
- 用户真机确认 Phase 21 迁移后的 QMenu 一打开就让 Explorer 隐藏图标栏收起，因而也失去了“外部点击先关菜单、Shell flyout 稍后按系统延迟收起”的常见层次。
- 当前右键路径是 `QSystemTrayIcon.setContextMenu()` 自动展示可激活的顶层 QMenu。结合 QMenu 继承 QWidget、popup 隐式抓鼠标以及 Windows flyout 的 light-dismiss 语义，定位为菜单打开时抢激活导致 Explorer 立即失焦；两个问题是同一根因。
- 本轮按用户表述先完成诊断，没有修改产品代码。下一步最小实施为：保留完整 QWidgetAction 视觉面板；`setContextMenu(None)`，Context/Trigger 统一手动 `popup()`；Windows 设置 `WA_ShowWithoutActivating`。首次外部点击仍由 QMenu mouse grab 关闭菜单，Shell 延迟完全交还系统，不新增 timer/Explorer 轮询。若该属性真机不足，再评估不接受焦点标志及其键盘可访问性代价。
- **Implementation completed:** `main.py` 取消自动 context menu，Context 与 Trigger 现在统一手动展示同一个 QMenu；`TrayMenuPopup` 在 Windows 设置 `WA_ShowWithoutActivating`。视觉结构、尺寸、圆角、开关和语言布局均未改变，且未加入 `WindowDoesNotAcceptFocus`、timer 或 Shell 窗口探测。
- 新增/更新测试覆盖 non-activating 属性、托盘 context menu 为空、左右键共用入口、Escape 关闭和内部开关不误关。托盘专项 4/4、完整回归 38/38、`compileall` 与 `git diff --check` 通过。是否能让 Windows 11 隐藏图标栏保持并在首次外部点击后延迟收起，仍必须在真实任务栏会话中确认。

### Phase 23: Windows 原生菜单循环与现有视觉复刻
- **Status:** complete (实现/真实原生预览完成，待隐藏图标栏真机复验)
- **Started:** 2026-07-14
- 用户再次真机确认：non-activating QMenu 仍会让隐藏图标栏在无操作时自行收回，而菜单独自残留。目标已更正为菜单打开期间暂停 Shell overflow idle retract，交互后菜单先关闭、Shell 随后按系统节奏关闭。
- 官方 Win32 状态证明原生 `TrackPopupMenu` 会进入线程 menu mode，而 QWidget QMenu 没有 HMENU/GUI_POPUPMENUMODE。开始实现无新增依赖的 Windows owner-draw HMENU；现有 QWidgetAction QMenu 保留为跨平台/失败回退。
- **Implementation completed:** 新增 Windows owner-draw HMENU，使用 `TrackPopupMenuEx` 获取真正的系统 menu loop；GDI 复刻 210px 深灰面板、Segoe UI、黄色开关、EN/中状态、分隔线和 hover。Windows 工厂选择原生实现，其他平台/失败路径保留 QMenu，不新增依赖。
- feedback、holding、language、quit 均由原生命令返回后发射现有 Qt signals；操作菜单项会先结束菜单 loop，符合用户要求的“发生操作后菜单先收起”。外部点击和 Escape 由 TrackPopupMenuEx 自身处理。
- 首次真实预览发现 FillRect 等函数缺少 64 位 argtypes，修复后第二次真实菜单预览无异常退出。原生菜单创建验证为 5 项；完整回归 39/39、`compileall` 与 `git diff --check` 通过。剩余验收只是在实际 Windows 11 隐藏图标栏入口静置，确认 Shell 确实因 GUI_POPUPMENUMODE 保持，并在菜单结束后按系统间隔收起。

### Phase 24: 原生菜单视觉/语言回归与任务栏边界异常
- **Status:** complete (待隐藏图标栏组合场景真机复验)
- **Started/Completed:** 2026-07-14
- 定位右下角刷屏异常并非边界算法错误，而是托盘菜单初始化把共享 `GetMonitorInfoW` 的 ctypes 参数签名覆盖为另一份 `MonitorInfo` 类型。两个调用点现统一使用兼容的输出指针签名；任务栏路径补充 `ctypes.ArgumentError` 兜底，失败时安全沿用 Qt 可用区域。
- 原生菜单显示期间安装当前线程、限定 `EVENT_SYSTEM_MENUPOPUPSTART` 的短生命周期 WinEvent hook；只对 `#32768` 菜单窗口应用 Windows 11 圆角偏好和 8 DIP region，恢复旧设计的 210px 深灰圆角轮廓，不改变黄色开关、字体与紧凑行高。
- 语言命令现在同步更新状态和 Qt signal 后在同一锚点立即继续原生菜单 loop；界面直接显示新语言，不再要求用户重新点击托盘。feedback/holding/quit 仍会正常结束菜单。
- 相关专项 35/35、完整回归 40/40、`compileall` 与 `git diff --check` 通过；按真实冲突顺序创建原生菜单后连续读取任务栏边界 5 次，无异常；独立可见原生菜单预览完成且进程无错误退出。最终仍需从 Windows 隐藏图标栏入口确认圆角主观观感与 Shell 静置/分层关闭组合行为。

### Phase 25: 退出电源线稿与菜单视觉微调
- **Status:** complete (待真实 Windows DPI/隐藏图标栏入口复验)
- **Started/Completed:** 2026-07-14
- 退出项在 Qt 与 Windows 两条路径均移除中文/英文文字，改为字体无关的简约电源线稿；Qt 保留中英文 tooltip，Windows 原生菜单继续发出原有 `quit_requested` signal。
- 菜单边缘圆角由 8 DIP 调整为 10 DIP。210px 宽度保持不变；Qt 上下边距、间距和行内边距微缩，Win32 行高从 26/24/24/7/29 调整为 24/22/22/5/24，整体更紧凑但不改变开关/语言的横向锚点。
- 新增电源按钮类型、尺寸与中英文 tooltip 测试；完整回归 41/41、`compileall` 与 `git diff --check` 通过。更新后的可见原生预览正常退出，未出现 GDI/菜单循环异常；仍需用户在自己的 DPI 与隐藏图标栏入口下确认最终主观观感。

### Phase 26: 退出项行业规范与卡顿基线
- **Status:** complete (性能优化待用户确认)
- **Started/Completed:** 2026-07-14
- 查阅 Microsoft 通知区规范后确认普通托盘上下文菜单的标准退出项就是 `Exit`；图标不是退出项必需形式。Windows 11 的系统图标推荐通过 `Segoe Fluent Icons`/Symbol 资源使用，并在紧凑图标按钮场景保留 tooltip/可访问标签。项目已将两条菜单路径的退出项恢复为原有中文“退出”/英文“Quit”文字，保留 Phase 25 的 10 DIP 圆角和紧凑间距。
- 性能基线：文本反馈约 62.3 FPS、CPU 5.2%；图片+堆叠约 61.9 FPS、CPU 19.0%；帧间隔 P95 分别约 16.78/17.11ms。鼠标 8ms 跟随计时器约 123.9Hz。结论是应用侧确实存在固定 16ms（约 62.5 FPS）视觉上限，165Hz 显示器上会显得不够顺滑；图片场景还有更高绘制压力，但当前没有证据表明电脑故障。
- 本轮没有擅自改动动画时钟，避免把“卡顿”修复和菜单视觉回退混在一起。下一步可选方案是活动期 8ms/自适应视觉 tick + 真机帧间隔/CPU A-B 验收；仍保持项目小型 QWidget/QPainter 架构。
- **Implementation update:** 用户确认开始执行后，将 `PropertyEngine` 活动期 timer 从 16ms 改为 8ms；新增测试锁定视觉/鼠标双 8ms 以及空闲停表。
- **A/B 结果:** 完整回归 41/41、`compileall` 与 `git diff --check` 通过。离屏文本场景 62.3→125.0 FPS、CPU 5.2%→12.9%；图片+堆叠 61.9→124.9 FPS、CPU 19.0%→32.1%；8ms 后帧间隔 P95 约 8.96–9.01ms。真实 Windows 165Hz/DWM 下的最终观感与功耗仍待手动复验。

### Phase 27: 边缘停靠过渡与图文视觉长度方案
- **Status:** planning complete (未修改产品代码)
- **Started/Completed:** 2026-07-15
- 审查确认右边界和底边界变化目前都是离散切换：窗口停靠位置、左右镜像、黄色锚点、图片上下布局及堆叠方向在一次 8ms tick 内共同跳变。高帧率只能增加重绘次数，不能消除这种坐标不连续。
- 实施建议分为两层：保留现有鼠标“左拖、右推”算法；新增可逆的 dock correction 动画，只平滑边界额外位移。水平建议 140–160ms，底部图片上置建议 180–200ms，并增加 12 DIP 进入、24–28 DIP 退出的迟滞阈值。内部组件应按进度插值实际位置，不能只在终点翻转布尔状态。
- 视觉长度结论：暂不缩短所有文字框，也不把图片堆叠固定向右移动。文字宽度 80–450 DIP，图片堆叠约 120–148 DIP，允许存在层级差；后续只试验镜像感知的 0–20 DIP 自适应配平。若真机 A/B 仍显示图文比例失衡，再考虑仅为“图片+长文本”设置 240–280 DIP 软上限。
- 本轮按用户要求仅完成方案、取舍和文档记录，没有修改 `FeedbackWidget`、布局函数或渲染组件，也未运行代码回归。
- **Implementation started:** 2026-07-15。用户确认开始实现边界切换动画。本轮范围限定为右侧/底部停靠的连续过渡、迟滞和回归测试；不实施图片堆叠视觉长度配平。
- **Implementation completed:** 新增水平/垂直 dock progress，首次定位直接就位，后续右侧以 150ms、底部以 190ms `OutCubic` 过渡；12/26 DIP 进入/退出迟滞防止边缘抖动，中途反向从当前进度继续并按剩余距离缩短时长。
- 窗口停靠修正与内部布局使用同一进度：黄色锚点、文字框位置/文字锚点、主图、堆叠偏移/旋转/pivot 全部连续变化。鼠标 normal endpoint 仍来自原有 spring，因此没有改变“向左拖、向右推”的跟随关系。文字框渐变固定轴向并插值两侧 alpha，消除了中点潜在闪烁。
- 验证结果：`tests.test_cursor_scaling` 20/20、完整离屏回归 46/46、`compileall`、`git diff --check` 全部通过。图文长度配平没有实施；真实 Windows 下仍需体验右侧 150ms、底部 190ms 是否需要各自微调约 ±20ms。

### Phase 28: 图片横向层叠模式与菜单图形切换
- **Status:** complete (实现/自动化/打包归档完成，待真实 Windows 视觉验收)
- **Started/Completed:** 2026-07-15
- 新增 `fan/cascade` 布局状态并写入 `QSettings.image_layout_mode`，升级默认仍为 `fan`。新复制反馈读取当前设置，已经播放中的反馈不强制改布局。剪贴板最多预取 4 张；原扇形仍显示 3 张，新横向层叠显示 4 张。
- `cascade` 不改变文字框长度：首图位于最高层，后层向右以 20 DIP 展开，不透明度为 `1.00/0.78/0.58/0.42`；贴右时图片组改为向左展开。复用 Phase 27 的 `dock_right_progress`，各层以 0.06 归一化相位错峰和 smoothstep 反转，保持可逆端点和首图最高 z-order。
- Qt 与 Windows 原生菜单都增加一行 64×24/28 DIP 的 icon-only 两态选择器。使用 Microsoft Fluent 官方 `Image Multiple` 与 `Slide Multiple` 白色线性缩影，当前模式用黄色描边/底条表示；Windows 选择后重进同一 HMENU 循环，状态立即刷新而无需关闭后再打开。
- 官方 SVG、生成的 16–64px 多分辨率 ICO、来源说明和 MIT 许可保存在 `assets/image_layout/`；spec 只收集两枚 ICO 与许可。运行时使用 Qt `QIcon`/Win32 `LoadImageW`，没有重新引入 QtSvg、GDI+ 或图标字体。
- 验证结果：完整离屏测试 51/51、`compileall`、`git diff --check` 通过；PyInstaller one-file 构建成功，27,226,027-byte 归档确认含两枚 ICO 和许可，检索不到 Qt6Svg/qsvg。真实 Windows 下仍需验收图标区分度、菜单即时刷新、150% DPI 与四图右侧反转手感。

### Phase 29: 菜单持久交互与 cascade 视觉修正
- **Status:** in_progress
- **Started:** 2026-07-15
- 用户反馈：Windows 菜单点击开关后会退出且有闪烁；cascade 20 DIP 间距仍显得偏窄，展开缺少原始 stack 的弹性；菜单轮廓边框和图标选择器摆放不够协调。
- 初步根因：`TrackPopupMenuEx` 每次命令选择都会结束当前 native loop，而循环目前只对语言/布局命令重进；cascade 的偏移只使用 dock progress，没有乘入 `_stack_progress` 的 spring 展开进度；Qt panel 仍保留 1px border。
- **Implementation completed:** native loop 将 feedback/holding 也纳入同一 HMENU 重进集合，应用状态后使用 `TPM_NOANIMATION` 立即回到原锚点；Qt panel 外轮廓设为无边框。图片布局选择器改为实际可点的 `Fan/Cascade`（中文 `扇形/层叠`）文字分段按钮，native owner-draw 使用同一行文字和黄色选中态。
- cascade 默认层差从 20 调整为 24 DIP；`cascade_step(target_width, count)` 在内容框足够宽时限制图片组足迹，短文本保留 20 DIP 最小层差；每层偏移乘入已有 `_stack_progress`，因此初次展开沿用原 stack 的 spring 弹性，右侧 dock 的错峰反转保持不变。
- 资源仍保留在 `assets/image_layout/` 作为 Phase 28 设计来源，但不再被 `.spec` 收集或由运行时加载；这次文字选择器更适合原生菜单尺寸，也减少了成品无用资源。
- 验证结果：完整离屏测试 51/51、`compileall`、`git diff --check` 通过；新 one-file 构建成功，`DoesCtrlCWork.exe` 为 27,211,938 bytes，归档检索不到 `assets/image_layout`、`Qt6Svg` 或 `qsvg`。真实 Windows 菜单重进的主观闪烁和 Shell 隐藏图标栏组合仍需手动确认。
