# Dose Ctrl+C 当前项目事实与演进总览

> 事实基线：`5bd31d278c267dcf988acca89306346db1db1d08`
> 审查日期：2026-08-14
> 审查方式：本地源码、测试、配置、文档与 Git 状态的只读静态审查
> 验证边界：本轮没有运行测试、构建或真实 Windows 桌面验收

## 文档用途

本文是当前代码基线的优先事实源，供维护者、代码审查者和 GPT Chat 使用。`planning711/` 下的旧记录仍保留完整演进过程，但其中的测试数量、实现状态和待办来自不同日期，不能单独代表当前 HEAD。

阅读本文时应区分三类状态：

- **已实现**：当前代码中存在对应实现。
- **已有测试**：当前测试源码中存在覆盖，但不表示本轮已执行通过。
- **待验证/建议**：尚未取得本轮运行或真实桌面证据，不能描述成已经完成。

## 当前结论

Dose Ctrl+C 已经是一个结构完整的 Windows 剪贴板反馈工具，而不是简单动画原型。系统剪贴板事件、图片加载、动画状态机、长文本视口、DPI/任务栏适配、托盘配置和 PyInstaller 精简均已有代码实现。

当前最合理的演进方向是先把它收敛成“可信、稳定、可发布”的单用途 Windows 工具。静态审查没有发现可以直接确认的 P0 阻断项，但存在四个应优先处理的 P1：全局快捷键回调跨线程操作 Qt、图片 worker 取消/退出不完整、自动远程图片请求及输入资源缺少统一安全边界，以及发布版本身份不一致。

## 仓库与版本快照

| 项目 | 当前事实 |
|---|---|
| 实际仓库根目录 | `dose-ctrlc/` |
| 分支 | `master` |
| 审查基线 | `5bd31d278c267dcf988acca89306346db1db1d08` |
| 基线提交时间 | 2026-07-21 14:20:54 +08:00 |
| 技术栈 | Python、PySide6、`keyboard`、PyInstaller |
| 本地环境元数据 | PySide6 6.11.1、keyboard 0.13.5、PyInstaller 6.21.0 |
| 测试源码 | 静态可数 81 个 `unittest` 测试方法 |
| CI/质量配置 | 未发现 GitHub Actions、lint、type-check 或依赖锁定配置 |
| 产品文档版本 | README 描述 v2.3.0 |
| Windows 文件元数据 | `version.txt` 仍为 1.0.1.0 |

本轮审查开始时 `master` 工作树干净，且与当时本地缓存的 `origin/master` 一致。文档发布前执行了 `git fetch origin master`，并确认本地 `master` 与刷新后的 `origin/master` 分歧为 `0/0`。

## 当前运行链路

```text
QClipboard.dataChanged
        │
        ├─ Windows clipboard sequence number 去重
        ├─ Ctrl+C pending intent / 700ms 失败确认
        │
        ▼
ClipboardMonitor
        │
        ├─ 文本快照
        ├─ QImage / raw image MIME
        ├─ 本地文件 / data URI
        └─ HTML 中的远程图片 URL
        │
        ▼
ClipboardFXApp
        │
        ├─ QSettings 持久化
        ├─ 托盘、主题、Holding、Silent Mode
        └─ 全局快捷键
        │
        ▼
FeedbackWidget
        ├─ 动画状态机
        ├─ PropertyEngine 单调时钟
        ├─ 长文本视口
        └─ 图片堆叠、边缘停靠、DPI/任务栏适配
```

主要代码入口：

- [`main.py`](../main.py)：应用生命周期、托盘、设置、快捷键与反馈窗口编排。
- [`core/clipboard_monitor.py`](../core/clipboard_monitor.py)：剪贴板事件、序列号、快照与图片 worker。
- [`ui/feedback_widget.py`](../ui/feedback_widget.py)：反馈生命周期、文本/图片动画和停靠绘制。
- [`ui/animation/state_machine.py`](../ui/animation/state_machine.py)：动画合法转换。
- [`ui/animation/property_engine.py`](../ui/animation/property_engine.py)：活动期属性动画时钟。

## 已实现能力

| 模块 | 当前实现 |
|---|---|
| 剪贴板监听 | 以 `QClipboard.dataChanged` 为事件源，在 Windows 使用 clipboard sequence number 去重 |
| Ctrl+C 关联 | Ctrl+C 只登记 pending intent；700ms 内没有剪贴板确认则提示失败 |
| 粘贴反馈 | Ctrl+V 表示粘贴按键意图；项目不保证目标应用已经接受内容 |
| 图片来源 | QImage、raw `image/*` MIME、本地文件、data URI、HTML `<img>` URL |
| 网络图片 | 最多三项并发、单次 3 秒超时、两次尝试、远程响应上限 2 MiB |
| 多图展示 | Fan 最多显示 3 张，Cascade 最多显示 4 张 |
| 长文本 | UI 快照上限 65,536 字符；支持多行展开与横向像素滚动 |
| 动画 | 集中状态机、单调计时属性引擎、图片 reveal、堆叠和完整退场路径 |
| 空闲行为 | 反馈不可见时停止属性动画和鼠标跟随高频 timer |
| Windows 适配 | 光标尺寸、DPI、多显示器边缘、任务栏和自动隐藏任务栏 |
| 设置 | Silent、Holding、语言、图片布局、配色和中英文字体通过 `QSettings` 持久化 |
| 打包 | 受版本控制的 PyInstaller onefile spec 排除未使用 Qt 模块和插件 |

## 当前优势

剪贴板成功事实已从旧的内容 fingerprint 轮询迁移为系统事件和 Windows sequence number。该模型能覆盖右键菜单、程序命令等非 Ctrl+C 的真实剪贴板更新，也避免把“内容与上次相同”简单等同为复制失败。

动画基础已经可维护：状态机负责合法顺序，`PropertyEngine` 使用单调时间计算进度并在空闲时停表；图片缩略图和最终文本布局已有缓存。当前没有证据支持为动画性能引入 Python+C++ 混合层。

图片路径优先使用剪贴板已经提供的 QImage/raw bytes；本地表示不存在时才进入文件、data URI 或网络 fallback。远程下载不会阻塞 Qt GUI 线程，并保留源任务顺序。

## P1 风险

### 1. 全局快捷键回调跨线程操作 Qt

`keyboard.add_hotkey` 的 callback 异步运行在独立线程。Ctrl+C、Ctrl+V 和文字导航已经通过 Qt signal 转回 GUI 线程，但退出、Silent 和 Holding 快捷键仍直接调用 `_quit`、`_toggle_silent_mode`、`_toggle_holding_mode`。这些方法会修改 Qt widget、QSettings、托盘和 QApplication 状态，存在间歇性竞争或崩溃风险。

建议建立统一的 Qt command bridge：所有 keyboard callback 只发射 signal，全部应用状态变更在 GUI 线程执行。

### 2. 图片 worker 取消和退出不完整

`_cancel_image_workers()` 只设置 cancellation Event，不会等待 QThread 结束，也不能中断已经进入的 `urlopen`。worker 内部还创建最多三个线程的 `ThreadPoolExecutor`；快速连续复制可能让旧请求继续占用后台线程。应用退出时立即关闭 QApplication，没有有界等待这些 worker。

建议引入明确的 worker manager、全局并发预算和关闭协议；退出时停止接收结果并在总 deadline 内等待。避免每个 QThread 再创建独立线程池。

### 3. 自动网络访问与输入资源边界

复制带 `<img src="http(s)://...">` 的 HTML 会自动发起网络请求。当前没有私网、loopback、重定向目标或用户授权策略，可能触发跟踪图片或访问本机/局域网服务。远程响应已有 2 MiB 上限，但本地文件使用整文件 `read()`，data URI 也会整体 base64 解码；它们没有同一套字节预算。

建议默认关闭或明确提示远程预览，拒绝 loopback/私网目标，并对 raw MIME、文件、data URI、下载响应和最终解码像素数设置统一预算。

### 4. 发布版本身份不一致

README 将当前能力描述为 v2.3.0，但 PyInstaller 使用的 `version.txt` 仍写 1.0.1.0。当前构建出的 exe 会携带旧文件版本，影响问题定位、发布核对和未来升级判断。

建议建立单一版本源，让 README、版本资源、发布说明、Git tag 和构建产物从同一位置生成或校验。

## P2 风险与维护债务

长文本可导航期间，方向键以 `suppress=True` 注册为全局快捷键，会短暂抢走前台应用的方向键。建议改为带修饰键、鼠标滚轮或不拦截输入的交互。

日志使用无轮转的永久 `FileHandler`。这是常驻应用，日志会持续增长；应使用固定大小和固定备份数量的滚动日志，并允许用户关闭详细图片诊断。

项目没有单实例保护。重复启动可能产生多个托盘图标、多个键盘钩子和重复反馈。

依赖只规定最低版本，`build.bat` 使用 PATH 中的 `python`，README 则推荐项目虚拟环境；仓库没有 CI、lint、type-check 或依赖锁定。当前构建可复现性依赖维护者人工选择正确环境。

`ui/feedback_widget.py` 约 942 行，同时负责状态编排、文字视口、图片缓存、停靠、动画和绘制；`ui/windows_tray_menu.py` 约 821 行。继续增加产品能力前，应先按生命周期、布局、渲染和输入控制拆分职责。

存在少量遗留代码和接口：未被主程序消费的 `copy_success` signal、没有参与判断的 `_pending_copy_id`/`_pending_event_sequence`，以及没有调用方的 `ui/scramble_text.py`。

图片 preload 的总量边界也不完全严密：worker 先加入 raw bytes 后，仍可再读取最多 `max_images` 个文件；`FeedbackWidget._append_images()` 只裁剪单次输入，没有根据已缓存总数停止追加。

## 测试与证据等级

当前测试源码静态包含 81 个 `unittest` 测试方法：

| 测试域 | 方法数 |
|---|---:|
| 动画、托盘与运行时 | 25 |
| 光标、DPI、任务栏和布局 | 24 |
| 文本视口 | 16 |
| 剪贴板和图片 worker | 10 |
| 主题和字体 | 6 |

测试大量使用 `QT_QPA_PLATFORM=offscreen` 和 mock。它们能验证状态、布局和绘制不变量，但不能替代真实 Windows 下的 Explorer 托盘、全局键盘钩子、多屏/DPI、DWM 帧表现和退出时线程清理。

本轮没有运行测试，因此当前只能确认“81 个测试方法存在”，不能声明“当前 HEAD 的 81 项已经通过”。旧文档中的 12、15、41、51、52、53 项通过记录属于各自历史阶段。

[`PACKAGING.md`](PACKAGING.md) 记录的 45.74 MiB 到 25.91 MiB 是 2026-07-13 的历史构建实验，不是本轮重新构建确认的发布产物。发布前仍需用锁定环境重建并完成真实桌面验收。

## 推荐演进路线

### 阶段一：可靠性基线

先处理 Qt 线程边界、worker 生命周期、统一图片资源预算、远程访问策略、日志轮转、单实例和版本源。这一阶段不扩展产品范围，但决定应用是否适合长期驻留和公开分发。

### 阶段二：发布工程

固定 Python、PySide6 和 PyInstaller 版本；增加 Windows CI、无网络单元测试、构建归档检查；建立 Windows 10/11、100%/150% DPI、多显示器、Explorer 隐藏图标栏、关机/退出和断网场景的手动验收表。

### 阶段三：同定位功能演进

优先考虑反馈强度档位、按应用启停、隐私/离线模式、鼠标交互替代全局方向键，以及更明确的“剪贴板已变化”和“检测到粘贴按键”文案。这些能力与当前定位一致，不需要持久保存用户剪贴板内容。

### 可选长期产品方向

| 方向 | 价值 | 主要代价 |
|---|---|---|
| 精致的单用途工具 | 最容易形成稳定、小而美的产品；当前推荐 | 需要持续打磨 Windows 细节 |
| 无障碍反馈层 | 声音、颜色、字体、低视力模式和反馈强度 | 与当前架构契合，但用户群更垂直 |
| 完整剪贴板助手 | 历史、搜索、收藏和格式转换 | 隐私、安全、存储和产品范围显著扩大 |

在可靠性和发布基线完成前，不建议增加云同步、账户体系、AI 剪贴板分析，也不建议因为包体积直接全量重写语言。

## GPT Chat 事实使用规则

将本文提供给 GPT Chat 时，应要求它遵守以下边界：

1. 以本文记录的 commit 为事实基线；如果仓库 HEAD 已变化，先重新审查。
2. 不把“测试源码存在”写成“测试已通过”。
3. 不把历史打包实验写成当前发布包结果。
4. 不把 offscreen/mock 覆盖写成真实 Windows 已验收。
5. 不把建议、可选方向或长期路线写成已实现功能。
6. 产品当前检测的是剪贴板变化与复制/粘贴按键意图，不保证目标应用实际完成粘贴。

## 当前状态摘要

```text
状态：功能丰富的 Windows 桌面工具，核心架构已成形
代码实现：README 所述 v2.3.0 主要能力在源码中存在
自动测试：81 个测试方法存在，本轮未执行
发布就绪：未确认
真实桌面验收：仍有多项待完成
最高优先级：线程安全、worker 退出、网络/输入边界、版本一致性
推荐路线：先可靠性和发布工程，再选择产品扩展方向
```
