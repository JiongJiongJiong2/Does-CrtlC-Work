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
