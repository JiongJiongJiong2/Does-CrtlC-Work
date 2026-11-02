# 设备间文字传送：目标、架构与边界

调查始于 2026-11-02，产品方向更新于 2026-11-03。当前开发分支为 `feature/device-transfer`，实现与验证状态见 [开发状态](TRANSFER_PREVIEW.md)。本文区分最终体验、已写入代码的后台能力和尚未完成的链路。

## 当前产品目标

两台 Windows 电脑开启蓝牙、运行 exe 后，工具应自动发现并完成可信匹配。用户主动拖送一小段文字，接收设备收到后播放项目原有的黄色圆点、展开和文字显现动画。产品流程不要求用户填写 IP、端口、密钥或手动设置设备列表；本轮专注后台基础，不新增前端设计。

早期提出的“先做 LAN、手动摆放设备、通过配置面板建立配对”方案已被这一要求替代。对应面板与边缘拖放 UI 已撤下，LAN 和 Qt BLE central 代码仅作为内部协议实验保留。历史研究中的手动布局、摄像头校准和额外硬件方案不构成当前产品的配置步骤。

## 当前架构与尚缺的连接

| 层次 | 当前状态 | 不能由此推导的能力 |
|---|---|---|
| Windows BLE 发现 | 原生 legacy 服务 UUID 广播 + Watcher；普通启动尝试运行 | 不保证任意蓝牙硬件支持广播，也不等于已互相认证 |
| 附近设备注册表 | Bluetooth 地址临时 ID、去重、TTL、RSSI 多样本近远提示；进程随机身份独立保存 | 单候选不是可信配对；信号强度不是左右方向 |
| 自动可信匹配 | 尚未实现零配置密钥交换与身份绑定 | 不可把收到广播直接当作允许读取或接收剪贴板 |
| BLE 文字收发 | Qt central 实验与通用消息协议保留；Windows 文字接收外围端尚缺 | 未完成两台 Windows 的自动发现到文字送达链路 |
| 主动拖送与接收动画 | 最终体验目标；本轮不设计新前端 | 现有复制动画不等于跨设备接收已接通 |

原生发现使用 `GattServiceProvider` 广播服务 UUID，设置 `IsConnectable=True`、`IsDiscoverable=True`，并由 `BluetoothLEAdvertisementWatcher` 接收。当前不把 ServiceData 放入 Windows legacy 广播：本机原生实测中，附加 23 字节 AD `0x21` 的方案未完整播出，禁止连接的方案也未正常发出广播；服务 UUID 方案已进入完整 `STARTED` 状态。不能将这一台适配器的结果推广为所有硬件保证。Qt 的 `QLowEnergyController` 在 Windows 上不支持 peripheral，原生 WinRT 后端仍是独立实现边界。[Microsoft：GATT 广播参数](https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.genericattributeprofile.gattserviceprovideradvertisingparameters)、[Qt：角色限制](https://doc.qt.io/qt-6/qlowenergycontroller.html#Role-enum)

发现服务提供 `b7d0ca13-4d11-4e7d-901c-6e66b55f4800` 这一公开只读 characteristic，静态值为版本 `1` 和 6 字节进程随机身份，供后续连接读取。当前没有文字写入或通知确认 characteristic。后续仍需完成可信身份、会话密钥、文字接收、分片重组和断连恢复；可连接的发现服务本身不授权发送正文。

## 自动发现与可信匹配

真实进程随机身份在本次运行内保持不变，并公开在只读 characteristic 中；扫描阶段尚未连接读取它。Watcher 无论通过服务 UUID 还是兼容 AD `0x21` 识别实例，都以 Bluetooth 地址的 6 字节值作为发现事件的临时 ID，注册表通过 `observe_identity()` 入表。地址变动时新旧记录可能短暂并存，旧记录由 TTL 清除，不能声称稳定识别了同一台电脑。

AD `0x21` 编解码器仍保留为内部兼容格式，但当前 Windows 后端不发送该格式。进程身份、Bluetooth 地址、设备名称、服务 UUID 和 RSSI 都不是认证秘密。单一候选只表示当前可见记录为一个，不能直接标记为已配对；多个候选不能按最强信号悄悄选中。

“用户不填写密钥”要求由协议完成安全的密钥建立和身份绑定，不能简化成所有安装使用同一个内置共享密钥。多台设备同时出现时如何确定用户的目标，以及首次建立信任如何处理，仍需后台协议与产品行为共同解决。本轮不以新的配置表单代替这项要求。

发现模块、信任模块和消息传输应保持独立。收到一段广播只更新注册表；完成认证后才建立可发送会话；用户主动发送时固定目标和正文快照。目标变化、窗口退出、蓝牙断开或任务取消都应终止旧会话的后续操作。

## 现实方位研究仍然成立

| 方法 | 能提供什么 | 对当前需求的意义 |
|---|---|---|
| 普通 BLE 广播与 RSSI | 发现实例、粗略近远参考 | 一个强度标量不能唯一确定左、右、前、后；遮挡与反射还会改变强度 |
| Bluetooth Direction Finding | AoA/AoD 方向估计 | 至少一端需要天线阵列及相应控制器/协议，普通蓝牙适配器不等于测角设备 |
| Bluetooth Channel Sounding | 更精确的距离信息 | 测距不等于测方向，需要双方具备相应能力 |
| UWB / Nearby Interaction | 在支持的设备组合中测距或测方向 | iPhone 12 mini 的 UWB 不会让普通 Windows 蓝牙适配器成为 UWB 对端 |

RSSI 不能唯一推出方向是基于单个标量测量的工程判断。Bluetooth SIG 将方向测量与测距分别定义，不能把自动发现或近距离提示包装成自动屏幕布局。[Bluetooth SIG：Direction Finding](https://www.bluetooth.com/learn-about-bluetooth/feature-enhancements/direction-finding/)、[Channel Sounding](https://www.bluetooth.com/learn-about-bluetooth/feature-enhancements/channel-sounding/)、[BLE primer](https://www.bluetooth.com/bluetooth-le-primer/)

Apple 官方规格确认 iPhone 12 mini 具备 UWB。Windows 若要成为相应对端仍需兼容硬件与协议；即使测得天线方向，也还需要确定天线与显示器的关系、设备朝向和屏幕映射。当前代码没有自动左右检测。[Apple：iPhone 12 mini 规格](https://support.apple.com/en-in/111877)、[Nearby Interaction 配件](https://developer.apple.com/nearby-interaction/)

额外硬件、声学、视觉标记和相关研究的证据保留在 [Windows 相对方位调查](WINDOWS_RELATIVE_POSITIONING.md)。这些研究不会自动改变当前无配置产品目标，也不作为这一轮实现的前置操作。

## 主动发送与接收语义

最终拖送行为只能由用户的明确操作触发。悬停、广播更新、候选出现和信号增强不触发发送；拖动过程中不能因 RSSI 变化静默更换目标。取消与释放在非目标区域不能产生文字发送。这些是后续交互的行为约束，本轮不规定或新增前端布局。

现有 `FeedbackWidget` 使用鼠标穿透并跟随鼠标，不能假设它天然是系统拖放源。后续接入时需区分输入意图、传输会话与反馈展示，避免为了传送而抢占常规桌面鼠标。Qt 本机拖放接口只能交换本机 MIME 数据，跨设备交付仍需本项目协议。[Qt：Drag and Drop](https://doc.qt.io/qt-6/dnd.html)

接收动画表示“收到文字”，应用级 ACK 表示“对端程序已接收”；它们不等于已写剪贴板，也不等于第三方应用已粘贴。接收正文不得被自动再次广播，重复消息只能确认一次业务接收，不能重复播放动画。远程鼠标、按键注入和自动投放到任意远端编辑器不在当前范围。[Microsoft：SendInput 限制](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)

## 消息与生命周期边界

保留的协议实验使用 UTF-8 纯文本，当前上限 4096 字节，具有随机消息 ID、有效期、确认、重试及有界去重缓存。AES-GCM 实验采用成熟加密库，但目前仍基于预先提供的共享密钥，不能据此声称完成了零配置配对。实验 LAN 回环和 Qt central 生命周期测试只验证各自模块。

正文超限应明确拒绝，不静默截断；展示摘要不能代替发送原文。日志不应记录正文或秘密，输入文本不执行为命令，也不触发链接预览。退出时停止扫描、广播与未完成会话；蓝牙不可用时保留现有本机剪贴板功能。

## 分阶段验证

已完成单机原生广播/扫描实验及最终冻结包的真实启动、自动广播/扫描和正常退出，203 项自动化测试通过。exe 归档确认含 6 个 WinRT 投影模块和运行时，打包误收第三方 ICU 的启动问题也已修复。源码正常开发安装 `requirements.txt` 即可，`requirements-transfer.txt` 仅供内部协议实验。

下一步用两台 Windows 的真实适配器验收互相发现、自身过滤、重复广播、TTL 过期、地址变化、权限/硬件失败路径和程序退出。双机验证尚未进行，不能由模拟后端、单机原生状态或成功打包推导端到端可用。

之后完成认证、密钥建立、多对端消歧及 Windows BLE 文字接收外围端，再验证消息送达、重试、重复、断连和退出。最后接入主动拖送和接收动画，完成两端实际体验验收。当前尚未达到跨设备端到端完成状态。

iPhone 配套接收端留作后续工作：需要实现原生 Core Bluetooth 服务、协议、前台接收动画和复制行为，并完成 macOS/Xcode 构建签名及 12 mini 真机验证。iOS 后台 BLE 限制和跨 App 展示边界仍适用；当前没有可安装的手机接收 App。[Apple：Core Bluetooth 后台行为](https://developer.apple.com/library/archive/documentation/NetworkingInternetWeb/Conceptual/CoreBluetooth_concepts/CoreBluetoothBackgroundProcessingForIOSApps/PerformingTasksWhileYourAppIsInTheBackground.html)、[Apple DTS：后台执行限制](https://developer.apple.com/forums/thread/685525)
