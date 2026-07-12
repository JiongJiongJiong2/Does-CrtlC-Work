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
