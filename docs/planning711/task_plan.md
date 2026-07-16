# 项目技术审查与演进计划

## Goal
基于当前未暂存改动、历史实现与 TMP 动画原型，明确动画退化原因、核心剪贴板逻辑问题，以及 Python/C#/C++ 的合理演进路线，并给出可执行的优先级计划。

## Current Phase
Phase 29 (菜单持久交互与 cascade 视觉修正；实现与自动化完成，待真实 Windows 视觉验收)

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

### Phase 14: 鼠标尺寸自适应反馈 UI
- [x] 调查 Windows 当前 HCURSOR、位图尺寸/hotspot 与 Qt device-independent pixel 的换算边界
- [x] 明确采用 1.00/1.15/1.30/1.50 分段比例，内容最大 1.50 倍，偏移单独限制，非 Windows 回退 1.00
- [x] 新增轻量 `CursorMetrics`：每次反馈创建时读取一次，动画期间固定，不增加常驻轮询
- [x] 使用统一逻辑坐标系缩放窗口、绘制、锚点和偏移，修复会覆盖外层变换的组件，避免文字/图片/堆叠错位
- [x] 增加屏幕边缘约束、纯函数与离屏绘制测试，验证默认尺寸完全不变、最大尺寸不溢出画布
- [x] 新增鼠标自适应设计文档并同步 findings/progress；真实 Windows 自定义光标、多屏/DPI 视觉另列
- **Status:** complete (待真实 Windows 大光标、多屏与 DPI 视觉验收)

### Phase 15: Windows 系统鼠标大小与反馈位置修复
- [x] 确认现有 `HCURSOR` 位图检测无法独立覆盖 Windows“指针大小”显示缩放；补充系统设置尺寸来源
- [x] 将 `CursorBaseSize` 纳入 `CursorMetrics`，并保持第三方自定义 cursor 的位图检测兼容
- [x] 根据有效鼠标显示尺寸调整反馈 UI 比例和鼠标避让偏移，验证默认尺寸不回归
- [x] 补充系统设置优先级、相对位置和边缘 clamp 的自动化测试
- [x] 更新设计文档、findings 与 progress，并列出仍需手动验收的真实 Windows 场景
- [ ] 在 Windows 设置分别调至 64/128 DIP 后，确认新复制反馈的大小、避让距离和屏幕边缘表现
- **Status:** complete (待真实 Windows 大鼠标手动验收)

### Phase 16: 可见内容边缘停靠与右侧镜像布局
- [x] 将边缘判断从透明 QWidget 画布改为实际可见内容的边界，消除下/右边界提前停住的问题
- [x] 底部停靠时保留固定安全边距，锁定纵向位置但保持横向跟随
- [x] 右侧停靠时切换为镜像布局：黄点/黄线靠右，内容与渐隐方向延伸到左侧，文字保持可读
- [x] 让图片及多图堆叠与右侧镜像方向一致，并保留已有 cursor-scale 坐标系
- [x] 增加纯布局、镜像绘制和完整回归测试；同步设计、findings 与 progress
- [ ] 在真实 Windows 单/多屏与任务栏边缘确认停靠阈值、12 DIP 留白和右侧切换手感
- **Status:** complete (待真实 Windows 边缘停靠手动验收)

### Phase 17: 自动隐藏任务栏边界与鼠标跟随帧率方案
- [x] 审查当前底边使用的 `QScreen.availableGeometry()` 与自动隐藏任务栏的冲突边界
- [x] 审查 PropertyEngine、MouseTracker、spring 与 QWidget.move 的逐帧链路
- [x] 实现仅在反馈活动且接近底边时工作的 Windows taskbar boundary provider
- [x] 对固定任务栏使用 work area，对自动隐藏任务栏使用当前可见矩形跟随其展开/收起
- [x] 反馈活动期使用 8ms 视觉动画与 8ms 窗口位置时钟；不按 `QScreen.refreshRate()` 驱动动画
- [x] 增加任务栏隐藏/展开边界、8ms 活动跟随/空闲停止与实际 frame interval 测试
- [ ] 在真实 Windows 自动隐藏任务栏动画中确认 `GetWindowRect` 是否连续更新；仅在发生末帧跳变时再加 80–120ms 单一插值
- **Status:** complete (自动化完成，待真实 Windows 任务栏动画手动验收)

### Phase 18: 托盘隐藏图标页无点击收起联动
- [x] 复核仅靠 `WindowDeactivate` 与鼠标按下沿无法覆盖 Explorer 隐藏图标页自行收起
- [x] 第一版打开菜单前记录鼠标下方的小型外部托盘宿主窗口，不依赖 Explorer 私有类名
- [x] 真实 Windows 验收确认：点击外部可正确联动，但无操作等待自动收起时 HWND 仍存在且 `IsWindowVisible` 不足以代表实际呈现
- [x] 第二版使用 Win32 原生 cursor 坐标命中窗口并沿父链选择最大的小型弹层候选，避免高 DPI 错位和误选任务栏根窗口
- [x] 检查 DWM cloaked、WS_VISIBLE 与窗口矩形是否仍和虚拟桌面相交；复用可见期 40ms timer，隐藏后立即停表
- [x] 增加 DWM cloaked/移出桌面以及宿主收起关闭菜单的离屏回归测试
- [ ] 在真实 Windows 11 重新等待隐藏图标页自动收起，确认第二版同步关闭；同时确认直接托盘入口不误关
- **Status:** complete (v2 自动化完成，待真实 Windows 复验)

### Phase 19: 水平单向拖拽/推动跟随
- [x] 鼠标向左移动时保留现有 spring 滞后，使内容框维持拖拽感
- [x] 鼠标向右移动时立即把 X 锚点贴到目标位置并清除旧速度，保持固定相对位置形成推动感
- [x] 垂直方向继续使用原 spring，不改变底边任务栏与右边镜像停靠逻辑
- [x] 增加左移处于 current/target 之间、右移精确贴住 target 的纯 spring 测试
- [ ] 在真实 Windows 以慢速折返和快速划动检查方向切换是否自然
- **Status:** complete (自动化完成，待真实 Windows 手感复验)

### Phase 20: 托盘先收起顺序与底边图片上置
- [x] 对来自隐藏图标栏的菜单增加仅可见期、无交互的 5 秒预收起，给正常菜单操作留出充足时间
- [x] 仅在鼠标已进入过菜单后，离开菜单去外部点击时才以 16ms 可见期检查主动隐藏，避免从托盘图标移入菜单途中误关
- [x] 鼠标进入/点击菜单后取消预收起；直接任务栏图标入口不启用该计时器
- [x] 底边停靠且含图片时，将圆点/内容框锚点下移、图片和堆叠改为在其上方展开
- [x] 将图片上置状态接入可见边界、窗口位置、主图、堆叠和离屏绘制测试，避免裁剪/错位
- [ ] 在真实 Windows 验证：无操作菜单先收起再由 Explorer 收起隐藏图标栏；外部点击顺序正确；底边图片不遮挡任务栏且离开边界后恢复下方布局
- **Status:** complete (自动化完成，待真实 Windows 复验)

### Phase 21: 托盘菜单关闭语义行业调研
- [x] 对照 Windows 原生通知区菜单、Windows light-dismiss flyout、Qt `QSystemTrayIcon/QMenu` 与当前自绘 `Qt.Popup`
- [x] 确认标准菜单不使用“无操作 N 秒关闭”、鼠标离开关闭或 Explorer 私有窗口状态作为主要生命周期依据
- [x] 确认标准关闭条件：执行命令、Escape、外部按下/失去激活；鼠标停留或无操作时继续保持可用
- [x] 给出保留深灰/黄色/圆角设计的最小迁移方案：`QMenu + QWidgetAction`
- [x] 经用户确认后移除 5 秒 idle timer、16ms 全局按键轮询、隐藏图标宿主/DWM 猜测，并迁移菜单实现
- [ ] 在真实 Windows 验证外部点击、Escape、键盘导航、开关行、语言切换、直接托盘与隐藏图标入口
- **Status:** complete (自动化与离屏视觉检查完成，待真实 Windows 复验)

### Phase 22: 隐藏图标栏共存与分层收起
- [x] 复核真实 Windows 反馈：打开菜单会立即收起隐藏图标栏；外部点击缺少“菜单先关、Shell 稍后关”的分层时序
- [x] 对照 Qt `QSystemTrayIcon/QMenu`、QWidget popup 激活/抓鼠标语义与 Win32 通知区菜单要求
- [x] 确认两个现象共享同一根因：右键 `setContextMenu()` 自动路径展示可激活的顶层 QWidget，触发 Explorer flyout light-dismiss
- [x] 明确不恢复 idle timer、Explorer HWND/DWM 轮询或人工模拟 Shell 延迟
- [x] 右键改回由 `activated(Context)` 手动调用同一个 QMenu，避免 `setContextMenu()` 自动激活路径
- [x] Windows 菜单设置 `WA_ShowWithoutActivating`，暂不启用会影响 Escape/键盘导航的 `WindowDoesNotAcceptFocus`
- [ ] 真机验证：打开时隐藏图标栏保持；外部点击先关闭菜单，隐藏图标栏随后按系统时序收起；直接托盘入口不回归
- **Status:** superseded (真机证明 non-activating QWidget 不能暂停 Shell overflow 空闲收起)

### Phase 23: Windows 原生菜单循环与现有视觉复刻
- [x] 更正目标：无操作时设置菜单与隐藏图标栏都保持；发生操作后先关菜单，Shell 再按系统间隔收起
- [x] 确认 Win32 `TrackPopupMenu` 会进入 `GUI_INMENUMODE/GUI_POPUPMENUMODE`，Qt Widgets QMenu 只是顶层 QWidget popup
- [x] Windows 使用 owner-draw `HMENU + TrackPopupMenuEx`，非 Windows/失败路径保留现有 QMenu
- [x] 复刻 210px 深灰面板、黄色开关、EN/中、紧凑行高和 hover，不引入 Qt Quick/WinUI/新依赖
- [x] 接回 feedback/holding/language/quit 信号与状态同步，并补齐纯逻辑/工厂/回归测试
- [ ] 真机验证无操作共同保持、外部点击分层关闭、菜单命令、DPI 与圆角观感
- **Status:** complete (实现/真实原生预览完成，待隐藏图标栏真机复验)

### Phase 24: 原生菜单圆角/即时语言刷新与任务栏边界崩溃修复
- [x] 定位右下角连续异常：两个模块为共享的 `user32.GetMonitorInfoW` 注册了不同 `POINTER(MONITORINFO)` 类型
- [x] 将 Win32 输出参数统一为兼容的 `c_void_p` 签名，并让任务栏边界读取捕获 `ctypes.ArgumentError` 安全回退
- [x] 在当前 UI 线程的原生 `#32768` 菜单出现时应用 Windows 11 DWM 圆角偏好与 8 DIP 圆角 region
- [x] 保持原 210px 深灰/黄色/紧凑排版；点击语言项后同步切换状态并在原锚点继续显示刷新后的菜单
- [x] 增加 native 调用失败不逃逸到鼠标移动回调的回归测试，并真实连续调用任务栏边界 5 次
- [ ] 从 Windows 11 隐藏图标栏入口复验：圆角、语言切换观感、静置共同保持与外部点击分层关闭
- **Status:** complete (实现、自动化与独立原生预览完成；待隐藏图标栏组合场景复验)

### Phase 25: 退出电源线稿与菜单视觉微调
- [~] 曾短暂将中文/英文退出项改为线条电源符号；经行业规范复核后恢复文字
- [~] Qt/Win32 线稿实现已移除，退出 command 保持普通本地化菜单文本
- [x] 菜单外轮廓圆角从 8 DIP 调整为 10 DIP
- [x] 保持 210px 宽度，轻微压缩上下边距、行高、分隔线和行间距，避免语言/开关错位
- [x] 恢复退出/`Quit` 文字并增加本地化文本回归测试
- **Status:** superseded (圆角/紧凑布局保留，退出线稿方案被 Phase 26 行业审查否决)

### Phase 26: 退出项行业规范与卡顿证据审查
- [x] 搜索 Microsoft 通知区、Windows 图标/Fluent Icons、WinUI 紧凑按钮和菜单规范
- [x] 将退出项恢复为中文“退出”/英文“Quit”普通菜单文本
- [x] 测量反馈动画帧率、计时器抖动、鼠标跟随频率和文本/图片场景 CPU 占用
- [x] 区分应用侧可复现因素与机器/桌面合成因素，形成后续优化边界
- [x] 将活动期视觉帧钟从 16ms 调整为 8ms，空闲时继续停表
- [x] 完成文本/图片场景的离屏 A/B 帧率与 CPU 对比
- [ ] 在真实 Windows/DWM/165Hz 屏幕上完成最终帧间隔与 CPU A/B 验收
- **Status:** complete (代码优化与自动化 A/B 完成；真实桌面验收待进行)

### Phase 27: 边缘停靠过渡与图文视觉长度方案
- [x] 审查右边界镜像、底边界图片上置、窗口停靠和鼠标 spring 的现有切换链路
- [x] 确认突兀来源：停靠状态、窗口位置和内部布局目前在同一帧以布尔值跳变
- [x] 给出不破坏“左拖、右推”手感的最小动画方案：只插值停靠修正量，内部布局使用独立过渡进度
- [x] 评估 80–450px 文字框与 120–148px 图片堆叠的视觉长度关系
- [x] 确定视觉建议：不全局缩短文字框、不固定向右平移图片，采用镜像感知且有上限的小幅视觉配平
- [x] 实现右侧停靠修正动画、底部图片上置动画、迟滞阈值与可逆中断
- [ ] 实现并真机比较图片堆叠的 0–20 DIP 自适应配平；确认后再决定是否保留
- [ ] 在 100%/150% DPI、单图/三图、短文本/长文本及任务栏自动隐藏场景完成验收
- **Status:** in_progress (边界动画与自动化完成；图文长度配平未实施，真实 Windows 手感待验收)

### Phase 28: 图片横向层叠模式与菜单图形切换
- [x] 明确新模式的层级、数量、透明度和普通/右侧停靠位置关系
- [x] 审查现有三图旋转堆叠、缩略图缓存、右侧 dock progress 与菜单状态持久化路径
- [x] 调查 Fluent System Icons、Material Symbols/Icons 的候选素材、格式与许可
- [x] 确定菜单采用两枚白色缩影的单行图形选择器，并兼容原生 HMENU 与 Qt 回退
- [x] 增加 `fan/cascade` 图片布局枚举、QSettings 持久化和托盘菜单信号
- [x] 实现横向 cascade：最多显示四张、首图最高层、后层逐步降低不透明度
- [x] 将右侧 dock progress 接入四张图片的位置反转与按层错峰移动
- [x] 引入 Fluent 官方素材的多分辨率本地资源及许可声明，不增加运行时 SVG/图标字体依赖
- [x] 增加两种模式、1–4/4+ 图片、右侧切换、DPI、菜单状态与打包资源回归测试
- [ ] 在真实 Windows 隐藏图标栏入口确认两枚缩影、黄色选中态、即时刷新和 100%/150% DPI 观感
- [ ] 真机比较 4 图 normal/right-dock 反转的错峰速度；仅在感觉拖沓时微调 `cascade_stagger`
- **Status:** complete (实现、51 项自动化及 one-file 归档验证完成；待真实 Windows 视觉手感验收)

### Phase 29: 菜单持久交互与 cascade 视觉修正
- [x] Windows 开关命令在一次菜单会话内保持打开，Qt/Win32 两条路径都不因状态切换丢失菜单上下文
- [x] 移除菜单外轮廓边框，重新设计图片布局选择器为清晰的文字分段选项
- [x] 将 cascade 间距从固定值改为“略微展开、受内容宽度上限约束”的计算，图片组不超过合理可视长度
- [x] 让 cascade 初次展开复用原始 stack spring 的弹性进度，保持右侧 dock 反转的可逆错峰动画
- [x] 增加菜单持久交互、无边框、动态间距和弹性端点回归测试，并更新文档
- [ ] 在真实 Windows Explorer 隐藏图标栏入口确认开关重进的主观闪烁、文字选择器点击和无边框观感
- **Status:** complete (实现、51 项自动化、one-file 构建与归档检查完成；待真实 Windows 视觉验收)

### Phase 30: 托盘菜单信息架构与原生菜单闪烁修复决策
- [x] 审查 Windows 原生 owner-draw 菜单与 Qt 备用菜单的实际控件、对齐、间距和点击语义
- [x] 确认现有“扇形 / 层叠”在 Windows 路径中整行只有一个命令热区，视觉上却伪装成两个独立按钮，容易误导且显得拥挤
- [x] 确认闪烁根因：每次选择 `TPM_RETURNCMD` 项都会结束一次 `TrackPopupMenuEx`；当前循环只能重开新的 `#32768` 菜单，`TPM_NOANIMATION` 不能保留同一窗口
- [ ] 方案 A（推荐的紧凑方案）：将图片布局改为一行“图片布局    当前值  ›”，整行点击切换；移除假分段按钮和图标缩影
- [x] 移除 Quit 上方装饰分隔线；标题、普通选项和 Quit 统一为 14 DIP 左对齐；Windows 原生菜单从 125 DIP 收紧到 113 DIP，Qt 备用面板离屏高度为 101 DIP
- [ ] 若“开关点击后菜单原地更新且绝不闪烁”是硬要求，迁移为真正的设置 flyout（可交互 popup），并单独回归隐藏图标栏共存；不能靠调整 `TrackPopupMenuEx` flag 达成
- [ ] 在真实 Windows 隐藏图标栏入口测试最终方案：静置、外部点击、语言/开关/布局切换、Esc、100%/150% DPI
- **Status:** in_progress (紧凑视觉重排已完成；等待确认采用紧凑单值行，或投入独立 flyout 迁移)

### Phase 31: 图片布局子菜单与系统主题适配方案
- [x] 审查当前两条菜单实现：Windows 为 owner-draw `HMENU`，Qt 仅为备用 `QMenu`；二者均为固定深灰色令牌，Windows 图片布局项目前仅是一个命令热区
- [x] 调查 Windows 官方主题、颜色和 backdrop API，以及 Qt/PySide6 的主题变更能力与版本兼容性
- [x] 设计主菜单中的 SVG 图标 + 文案 + 悬停子菜单：两种字体/展示方式、与主菜单比例一致的圆角、离开父/子区域后的关闭语义与键盘可访问性
- [x] 评估浅色模式的配色令牌、透明度和磨砂边界：菜单保持实色主题；毛玻璃仅评估文字内容框和图片占位/堆叠底板，不涉及原生 `HMENU`
- [x] 给出最小可实施范围、风险、真实 Windows 验收矩阵与是否需要改变原生菜单架构的结论
- [x] 实现 Windows owner-draw 图片布局父项、两个原生子项、16 DIP 既有 Fluent ICO、根/子 10/8 DIP 圆角与 Quit 后 3 DIP 无 hover 留白
- [x] 实现 Qt 备用路径的单行图标入口/子菜单，以及 PyInstaller 对两枚 ICO 的收集
- [x] 实现 Qt `colorSchemeChanged` 驱动的深浅主题令牌；覆盖托盘菜单、内容框、图片占位和图片/堆叠底板
- [x] 完成离屏主题切换、原生菜单创建、静态编译和 diff 检查
- [ ] 在真实 Windows 托盘与隐藏图标栏入口验收：子菜单 hover、左右边界翻转、模式选择后的刷新、Quit 视觉位置、深浅主题切换和反馈表面可读性
- **Status:** in_progress (实现与自动化检查完成；待真实 Windows 视觉/交互验收)

### Phase 32: 可选配色与底边界回弹修复
- [ ] 将系统自动主题改为用户持久化选择：经典深色、浅色玻璃、和自定义表面色；自定义色自动推导文本/hover/图片表面以保证可读性
- [ ] 为托盘菜单新增“配色”父项、三项原生/Qt 子菜单，并将“自定义”接入 Windows 原生颜色选择盘而非新依赖
- [ ] 让反馈内容框、图片占位和堆叠底板读取用户选择；菜单与子菜单保持实色且随选择同步
- [ ] 诊断任务栏已升起时，鼠标自屏幕底边向上移动导致内容框先回到底部再追上的状态/坐标竞争
- [ ] 以最小改动修复边界回弹，并添加离屏/纯逻辑回归覆盖
- **Status:** in_progress (用户于 2026-07-16 提出并要求开始实施)

### Phase 32 implementation update (2026-07-16)

- [x] Replaced system-following theme logic with persisted app palette choices: Classic, Light glass, and Custom.
- [x] Added a native/Qt `Colour` submenu; `Custom...` opens the platform colour picker and derives contrast-safe text, hover, content-box, placeholder, and image-stack tokens.
- [x] Added a subtle top/bottom content-box gradient softening layer without changing the feedback anchor or layout dimensions.
- [x] Fixed the raised-taskbar rebound: retain the taskbar boundary until bottom-dock progress reaches zero, avoiding the screen-bottom anchor snap.
- [x] Added an offscreen regression test for the taskbar-boundary unwind path; real Explorer visual acceptance remains pending.

### Phase 32 detail adjustment (2026-07-16)

- [x] Replaced the native layout-row glyph with the alternate bundled `fluent_slide_multiple.ico` for more reliable Win32 rendering.
- [x] Removed redundant trailing arrows from layout and colour rows in both native and Qt fallback menus.

### Phase 32 icon transparency follow-up (2026-07-16)

- [x] Removed the extra light rounded tile behind the native image-layout icon so the ICO transparency reveals the menu surface directly.

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
| Phase 14 最终回归首次调用了缺少 PySide6 的系统 Anaconda Python | 1 | 改用项目 `.venv\\Scripts\\python.exe`，完整测试 25/25 通过。 |
| Phase 15 首次读取 cursor 注册表时将两个属性名写成一个参数 | 1 | 改用 `Select-Object -Property` 后成功读取；本机当前 `CursorBaseSize=32`。 |
| Phase 16 右侧镜像绘制测试断言画布最末像素，受 Qt 画笔边界裁剪影响为透明 | 1 | 改为验证 2px 竖线的内侧像素，继续保留镜像锚点的视觉覆盖。 |
| Phase 16 左侧黄线回归断言把渐隐背景的低透明黑色也视为失败 | 1 | 改为验证该像素不含黄色锚点色，而非要求透明度绝对为零。 |
| Phase 17 只读 `FindWindowW("Shell_TrayWnd")` 在当前 Windows 会话返回空句柄 | 1 | 放弃依赖 Explorer 私有类名，方案改用官方 `ABM_GETAUTOHIDEBAREX` 按显示器/边缘取得 HWND。 |
| Phase 17 尝试启动真实 Qt Windows 平台诊断无可用输出并以 exit 1 结束 | 1 | 不把不可复现的 GUI 会话结果用于验收；保留纯函数/离屏测试并把真实任务栏动画列为手动验收。 |
| Phase 18 新增测试单独运行时 `unittest.mock` 未被 Python 3.14 懒加载 | 1 | 改为 `from unittest.mock import patch` 显式导入；专项与完整套件重新通过。 |
| Phase 21 首次专项测试命令误用了 `AnimationStateTests` 类名 | 1 | 用 `rg` 定位测试实际位于 `TrayAndHoldingTests`，改用正确类名重跑。 |
| Phase 21 托盘绑定测试直接构造第二个 `QApplication` | 1 | 改用 `ClipboardFXApp.__new__` 的轻量 harness 单独调用 `_setup_tray()`，避免改变产品启动逻辑。 |
| Phase 23 首次真实 owner-draw 预览的 GDI 句柄按默认 32 位解释 | 1 | `FillRect` 暴露 HDC/HBRUSH overflow；补齐 FillRect/DrawText/SetBkMode/SetTextColor/RoundRect/Ellipse 的 64 位 argtypes 后重测。 |
| Phase 23 回归命令末尾用 CIM 查询已有进程被系统拒绝访问 | 1 | 测试、compileall、diff check 已先完成并通过；进程枚举不是实现验收条件，不申请额外系统权限。 |
| Phase 27 首次组合补丁使用了与实际 `ContentBox.paint` 不一致的类型签名上下文 | 1 | 整组补丁未写入；重新读取目标文件并拆分为逐文件精确补丁。 |
| Phase 28 首次 one-file 构建被 60 秒命令上限中止 | 1 | 保留产品代码不变，以可持续返回进度的长任务重新构建；99.6 秒成功生成并检查归档。 |
| Phase 29 首次分段读取脚本出现 PowerShell“参数类型不匹配” | 1 | 停止复用混合数组范围，改为逐文件精确读取；产品文件未被该错误修改。 |

## Notes
- 规划文件持续记录审查、实现和剩余真实桌面验收；Phase 29 已修改菜单、布局和测试代码，未修改系统设置或用户数据。
- 对动画的判断需要结合代码、资源及可运行验证；无法运行的部分要明确证据边界。
