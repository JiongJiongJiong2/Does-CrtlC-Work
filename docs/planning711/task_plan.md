# 项目技术审查与演进计划

## Goal
基于当前未暂存改动、历史实现与 TMP 动画原型，明确动画退化原因、核心剪贴板逻辑问题，以及 Python/C#/C++ 的合理演进路线，并给出可执行的优先级计划。

## Current Phase
Phase 13 (Tray overflow dismissal lifecycle complete; Windows desktop verification pending)

## Phases

### Phase 1: 仓库与变更盘点
- [x] 识别项目结构、依赖、打包方式和入口
- [x] 对比未暂存改动与当前基线
- [x] 定位 TMP 原型及动画相关代码
- **Status:** complete

### Phase 2: 动画链路审查
- [x] 还原原型动画的状态、时序、缓动和渲染路径
- [x] 对比 Python 实现，定位缺失步骤与卡顿来源
- [x] 提出最小修复方案和验收标准
- **Status:** complete

### Phase 3: 核心功能与性能审查
- [x] 追踪 Ctrl+C、选区、剪贴板和提示 UI 的事件链
- [x] 判断是否真正监听系统剪贴板及是否存在误判/低效轮询
- [x] 给出正确、低开销的 Windows 实现建议
- **Status:** complete

### Phase 4: 技术栈与体积方案评估
- [x] 分析当前 45 MB 体积来源和 Python 优化空间
- [x] 比较 Python、C#、C++ 的开发/体积/部署/系统集成成本
- [x] 提出推荐架构与迁移边界
- **Status:** complete

### Phase 5: 综合路线图与交付
- [x] 汇总结论、风险、优先级和阶段性实施计划
- [x] 为每阶段定义验证方式和建议目录/模块边界
- [x] 交付用户可直接决策的建议
- **Status:** complete

### Phase 6: P0–P2 动画与运行时修复
- [x] 修复堆叠 spring、ERROR/PASTE 短路径、退场线条和缺失退出转换
- [x] 将 FeedbackWidget 的逐帧效果合并到一个单调时钟，并让鼠标追踪仅在反馈活动时运行
- [x] 缓存主图/缩略图渲染，减少逐帧缩放与 QPixmap 转换
- [x] 添加可运行的状态机和动画逻辑测试，验证不回归
- [x] 在 planning711 文档标记完成项、剩余项和验证结果
- **Status:** complete

### Phase 7: P2 真实验证与 P3 剪贴板事件重构
- [x] 对 P2 增加可重复的运行时计时/空闲计时器验证
- [x] 以 `QClipboard.dataChanged` 作为剪贴板变更事件源，并在 Windows 使用 sequence number 去重
- [x] 将 Ctrl+C 从轮询触发改为 pending intent + 有界确认超时
- [x] 为异步图片任务增加请求 ID、取消标记、顺序保持和无重复更新
- [x] 增加事件链与 worker 的自动化测试，更新 planning711 状态
- **Status:** complete

### Phase 8: 中文排版与文本渲染性能
- [x] 建立文本脚本识别与 `TextStyleResolver`：英文/代码、中文/混合、emoji 分别选择合适的 Windows UI 字体与字距
- [x] 以 `QFontMetricsF.horizontalAdvance` 计算内容框宽度，移除 `len(text) × char_width` 的固定宽度假设
- [x] 缓存 QFont、QFontMetricsF 和最终文本布局；避免 `paintEvent` 每帧创建字体
- [x] 将 scramble 的随机文本更新限制为视觉足够的节奏（建议 24–30fps），保持窗口和鼠标动画 60fps
- [x] 以中文、混合中英、长文本、emoji 建立宽度、绘制与不裁剪测试
- [ ] 在真实 Windows 桌面验收实际字体 fallback、视觉效果和帧耗时
- **Status:** complete

### Phase 9: P8.1 ASCII block 伪加载平滑度
- [x] 确认卡顿来自 33ms（约 30fps）刷新与 60fps 窗口动画不同步，以及每次全量重随机字符串
- [x] 改为 16ms 同频刷新、持久化 scramble 缓冲，并限制每帧噪声变更数量
- [x] 更新回归测试并运行离屏验证（15 项通过）
- [ ] 在真实 Windows 桌面确认 ASCII block 与中文最终文本的观感
- **Status:** complete

### Phase 10: 打包瘦身审计与文档整理
- [x] 从当前 PyInstaller onefile 产物读取归档清单，量化主要体积来源
- [x] 对照实际 import，识别可排除的 Qt 模块、插件、翻译和重复构建配置
- [x] 整理 Markdown：建立文档入口，归档过时的 C++ 计划与开发日志，更新 README 链接
- [x] 写出可执行的 PyInstaller 瘦身实验步骤、预期收益和功能验收清单
- **Status:** complete

### Phase 11: PyInstaller 瘦身实验
- [x] 用隔离环境从当前代码构建未裁剪基线，并记录大小/依赖版本（47,966,119 bytes）
- [x] 在 spec 中加入可复现的低风险裁剪：翻译、未使用 Qt 模块和非运行时插件
- [x] 构建裁剪候选包，对比 CArchive 内容与基线大小（v3：25.91 MiB，减少 43.4%）
- [x] 运行离屏回归测试，并完成冻结包启动 smoke test
- [ ] 在真实桌面完成托盘、文本/图片/多图剪贴板、Holding 和高 DPI 手动验收
- [x] 同步 README、PACKAGING 和 planning711 的构建命令、结果与遗留风险
- **Status:** in_progress

### Phase 12: Holding 语义与自定义托盘面板
- [x] 审查 Holding 的 paste、关闭开关、超时与状态显示路径，确认普通反馈会被错误退出且 Ctrl+V 仅代表按键意图
- [x] 只让 Holding 的复制会话响应 Ctrl+V 退场；普通复制后 Ctrl+V 改为显示绿色 paste 提示
- [x] 将静默/Holding 改为可勾选、可持久化状态，并补齐状态同步与自动化测试
- [x] 以圆角深灰自绘 `Qt.Popup` 替代原生托盘 `QMenu`：黄色 Apple 风格开关、EN/中语言标识、小尺寸与 DPI 自适应
- [x] 补齐中文/English 菜单文案、README 快捷键与计划/发现/进度记录
- [x] 运行离屏交互测试、静态检查；真实 Windows 托盘位置与视觉/DPI 验收另列
- **Status:** complete (真实 Windows 视觉/DPI 验收待发布前执行)

### Phase 13: 托盘隐藏图标页收起联动
- [x] 确认 `Qt.Popup` 仅监听自身 `WindowDeactivate`，无法稳定得知 Explorer 管理的隐藏图标页已收起
- [x] 增加应用级失活收起，以及仅在弹层可见期间运行的 Windows 外部点击检测
- [x] 为外部点击的按下沿判定增加离屏测试
- [x] 更新计划、发现和进度，并保留真实 Windows 隐藏图标页验收项
- **Status:** complete (待真实 Windows 隐藏图标页手动验收)

## Key Questions
1. TMP 原型与当前动画在状态机、帧时序、缓动、合成方式上分别差在哪里？
2. 当前实现检测的是 Ctrl+C 按键、选中文本，还是系统剪贴板实际变化？
3. 45 MB 是否值得用跨语言重写解决，还是先优化打包更划算？
4. Windows 原生剪贴板监听和 UI 动画最合适的技术边界是什么？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 先审查再修改代码 | 用户当前要的是分析和计划，且未暂存改动可能属于待发布版本，不能贸然覆盖 |
| 以未暂存 diff、历史基线和 TMP 原型三方对照 | 能区分动画回归、原型遗漏和架构固有问题 |
| 当前版本继续 Python，暂不做 pybind11 混合 | 现有瓶颈不是 CPU 数学，混合方案不移除 Python/PySide/Qt，体积收益极低 |
| 长期 Windows-only 候选为 C# WPF | 原生剪贴板/消息窗口集成成熟，维护成本明显低于 C++ Win32 |
| 系统剪贴板事件与 sequence number 作为成功依据 | 比内容 fingerprint 更符合产品语义，并覆盖非 Ctrl+C 的复制入口 |
| 本轮只实施 P0–P2 动画/运行时修复 | 用户明确排除 Python+C++ 与 C#，剪贴板事件重构和打包瘦身留待后续阶段 |
| P0–P2 的实现验收以自动化测试为准，视觉验收单列 | 当前环境能够可靠运行 offscreen Qt 测试；原型手感仍应在真实桌面录屏下确认 |
| P3 先使用 Qt 事件，Windows sequence 用于去重 | Qt 负责剪贴板变更通知；保留原生 `WM_CLIPBOARDUPDATE` 作为未来 Qt 平台行为不足时的后端增强，而非重复注册两套事件源 |
| 中文文本采用“原生 UI 字体优先、代码字体按脚本启用”的策略 | 对所有文本强制 Cascadia Code + 2px 字距会造成 CJK fallback、字距失真和宽度计算错误 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| 在工作区根目录执行 git 命令提示“not a git repository” | 1 | 已定位实际仓库为 `dose-ctrlc/`，后续 Git 调用均在该目录执行 |
| 当前 `spring_ease(1,0,t)` 调用触发 ZeroDivisionError | 1 | 已确认是新旧函数接口错配；列为动画 P0 修复 |
| 更新规划文档时 apply_patch 上下文不匹配 | 1 | 已读取实际内容并改用更小的精确补丁 |
| 完成报告后再次从工作区根调用 git status | 2 | 已保留已知仓库边界；最终状态检查改到 `dose-ctrlc/` |
| P8 验证命令中的 PowerShell 引号未闭合 | 1 | 拆分测试与检索命令，避免在正则中嵌套双引号 |
| P8.1 更新 PROJECT_REVIEW 的首个补丁上下文不匹配 | 1 | 读取实际段落后使用精确上下文补丁完成更新 |
| Phase 10 首次同时新增文档并修改 README 的补丁上下文不匹配 | 1 | 拆分为新增文档和 README 精确补丁后完成 |
| Phase 10 检索 PyInstaller Qt hook 时误用了已移动的旧文件路径 | 1 | 定位到 `utils/hooks/qt/__init__.py` 后完成源代码审计 |
| Phase 11 用 `git check-ignore -v` 验证 spec 白名单时误读否定规则输出 | 1 | 改用普通 `git check-ignore -q` 与 `git status`，确认 spec 未被忽略 |
| Phase 11 使用了不存在的 `pyi-archive_view` 入口，并尝试通过模块入口调用 | 1 | 改用已安装的 `pyi-archive_viewer.exe`；v3 归档确认不含 QtNetwork、QML/Quick/PDF 或软件 OpenGL。 |
| Phase 12 在两个开关行显示完整快捷键后，离屏面板宽度达到 350px | 1 | 移除弹窗中的冗长快捷键文本，保留 README 中的快捷键说明，使紧凑面板宽度回到 280px 以内。 |
| Phase 13 首次最终检查发现 `ui/tray_menu.py` 两处尾随空格 | 1 | 移除空白行尾空格后重新执行 `git diff --check`。 |

## Notes
- 只创建本次审查所需的规划文档，不修改产品代码。
- 对动画的判断需要结合代码、资源及可运行验证；无法运行的部分要明确证据边界。
