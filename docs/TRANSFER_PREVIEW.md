# 附近设备自动发现：开发状态

更新日期：2026-11-03。当前工作位于 `feature/device-transfer`；稳定分支 `master` 保留已推送的剪贴板可靠性修复。

产品目标是两台 Windows 电脑开启蓝牙并运行 exe 后，工具自动发现、完成可信匹配，随后支持主动拖送文字，并在接收端播放原有反馈动画。用户不需要填写 IP、端口或密钥。本轮先实现自动发现的后台基础，不设计新前端；先前的手工配置面板与边缘目标 UI 已撤下。

## 当前入口

源码开发环境安装常规依赖后正常启动：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

普通启动会尝试启动 Windows 原生 BLE 广播与扫描，无需 `--transfer` 或额外面板。开发排查时可使用 `python main.py --no-nearby` 停用这项后台发现。BLE 不可用时记录具体原因，本机剪贴板反馈继续工作。exe 已成功构建，归档检查确认包含 6 个 WinRT 投影模块及运行时；最终冻结包真实启动、自动广播/扫描及 10 秒后正常退出均已通过。历史发布 exe 不因此自动具备新功能。`requirements-transfer.txt` 仅供内部加密传输实验，正常运行附近发现无需额外安装它。

## 已实现的范围

`core/windows_nearby.py` 使用 Windows 原生 `GattServiceProvider` 广播 128-bit 服务 UUID，并用 `BluetoothLEAdvertisementWatcher` 接收广播。当前 Windows legacy 广播不附加自定义 ServiceData。它避开了 Qt 在 Windows 上不能承担 BLE peripheral 的限制，但仍要求本机适配器支持相应 BLE 角色；可连接的发现服务也不等于已实现文字接收端。[Qt 角色限制](https://doc.qt.io/qt-6/qlowenergycontroller.html#Role-enum)、[Microsoft：GATT 广播参数](https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.genericattributeprofile.gattserviceprovideradvertisingparameters)

`core/nearby_peers.py` 分别管理本进程随机身份和附近设备的临时注册表。Watcher 识别约定服务 UUID，也兼容外部对端的 AD `0x21`；发现事件统一用收到的 6 字节 Bluetooth 地址作为临时 ID，由 `observe_identity()` 更新去重和 TTL。地址变化可能形成新记录，旧记录自然过期，不能据此推断稳定设备身份或已配对。RSSI 采用有限时间窗口内的多个样本，只给出粗略近远提示，不推导左、右或屏幕位置。只有一个对端时可标记候选；多个对端时不会把最强信号自动当成目标。

广播是发现信息，不是配对认证。当前没有零配置密钥交换、可信设备绑定、Windows BLE 文字接收外围端，也没有接通发现到双端文字发送、确认和动画的完整链路。发现候选不会自动读写剪贴板、发送文字或控制鼠标。普通广播接收及本地自动化测试不能证明两台物理电脑已经互相发现或成功传文。

## 当前广播与身份格式

发现服务 UUID 为 `b7d0ca10-4d11-4e7d-901c-6e66b55f4800`。本机开启蓝牙后的原生实验发现：此前附带 23 字节 AD `0x21` payload 的 ServiceData 方案无法完整播出，`IsConnectable=False` 的方案也没有正常发出服务广播。当前改为 legacy 广播仅公布服务 UUID，并设置 `IsConnectable=True`、`IsDiscoverable=True`；这一组合在本机原生实验中进入完整 `STARTED` 状态。该结果针对本机硬件，不是全部 Windows 适配器的兼容性保证。

服务内另有公开 READ-only characteristic `b7d0ca13-4d11-4e7d-901c-6e66b55f4800`，静态值为版本 `1` 加 6 字节本进程随机身份，供未来建立连接后读取。它没有文字 Write/Notify 能力。扫描阶段尚未读取这一值，所以注册表中的地址临时 ID 与真实进程随机身份必须区分；两者都不是信任凭证。

`encode_advertisement()` / `decode_advertisement()` 保留为内部兼容格式：完整 AD `0x21` payload 为 16 字节服务 UUID、版本 `1` 和 6 字节进程身份，共 23 字节。UUID 采用 BLE 整体反转 16 字节的线序，而非 GUID 混合字节序。当前 Windows 后端不广播此 payload；其字节数理论上落入 legacy 预算，不能替代 Windows 广播调度及硬件实测。[Microsoft：ServiceData 仅在有空间时添加](https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.genericattributeprofile.gattserviceprovideradvertisingparameters.servicedata)、[Chromium：WinRT 原始服务数据解析](https://chromium.googlesource.com/chromium/src/+/master/device/bluetooth/bluetooth_adapter_winrt.cc)

## 保留的内部实验

`core/transfer_protocol.py`、`core/lan_transfer.py` 和 `core/ble_transfer.py` 暂保留为协议、LAN 回环及 Qt BLE central 实验代码。它们已有的手工密钥、地址或对端参数属于内部测试工具，不是当前产品使用流程，也不要求用户配置。它们不证明新的自动发现与可信匹配已经接通；普通启动的原生发现后端不会自动调用这些实验发送接口。

现阶段没有可安装的 iPhone 接收 App。iPhone 12 mini 不能仅凭开启蓝牙就充当本项目的文字接收端；移动端配套程序、协议互通、前台动画和 iOS 构建分发仍是后续工作。

## 下一步验收

单机原生实验、最终冻结包启动/广播/扫描/退出及 203 项自动化测试已通过；两台物理电脑互相发现尚未测试。测试包为 `packaging-artifacts/nearby-preview/DoesCtrlCWork.exe`，32,606,204 字节，仅供当前发现阶段验收。接下来确认两端适配器都支持广播与扫描，再用该包验证互相发现、自身过滤、断开超时、重新出现及正常退出。硬件不支持、权限拒绝、蓝牙关闭与依赖缺失都应明确报告，不能显示成已配对。

随后实现无需手工输入秘密的认证与密钥建立，明确多设备环境中的目标消歧，再实现 Windows 外围端文字接收、受限消息、重试、确认和去重。完成这些后，才进入用户主动拖送与接收动画的端到端验证。自动发现、可信匹配、文本送达和左右方位是不同的验收项。
