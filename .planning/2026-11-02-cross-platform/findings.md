# 调查记录

仓库实际根目录是 dose-ctrlc，HEAD 为 5f4e11d。开始时工作树干净。主体为 Python/PySide6/keyboard，原有文档已记录截至 2026-08-14 的事实；最后提交为文档更新。

历史已经从轮询迁移为剪贴板事件、pending copy intent 和有界确认；动画时钟、文本视口、图片本地优先和 Windows 托盘已多轮改进。现有事实文件列出 81 个测试，但其审查没有运行测试，不能沿用为本轮通过结论。

旧事实源建议先可靠性和发布工程；本轮用户新目标增加跨平台，不能把旧的 Windows 优先产品路线当成用户当前限制。

本轮运行 `.venv/Scripts/python.exe -m unittest discover -s tests -v`，QT_QPA_PLATFORM=offscreen，81 项通过，2.481 秒。日志保存在本目录 unittest.log；不代表系统权限、原生桌面或 iPhone 验收。

官方核实：Qt 当前 6.12 在线文档已提供 pyside6-ios-deploy，不能断言 PySide6 完全不能部署 iOS；但要求完整 Xcode、iOS 专用 wheels，桌面依赖不能直接沿用。Qt QClipboard 文档注明 macOS 的其他应用变更仅在本应用激活时检测，常驻工具需专门适配。keyboard 上游说明 macOS 支持实验性、Linux 原始设备读取需要 root、拦截仅 Windows 支持。PyInstaller 不交叉编译；GitHub Actions 提供三个桌面系统 runner。

参考：
- https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-ios-deploy.html
- https://doc.qt.io/qt-6/qclipboard.html#dataChanged
- https://github.com/boppreh/keyboard
- https://pyinstaller.org/en/stable/
- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html
- https://developer.apple.com/library/archive/documentation/NetworkingInternetWeb/Conceptual/CoreBluetooth_concepts/CoreBluetoothBackgroundProcessingForIOSApps/PerformingTasksWhileYourAppIsInTheBackground.html

独立核心审查使用假 clipboard/QCoreApplication 复现：事件早于 Ctrl+C handler 时会先成功后失败；旧快照重试没有取消导致新内容重复发出；图片回包缺少 UI 会话归属；QImage.copy 后 cacheKey 改变，现有去重不可靠。正在收集逐行证据。

复现证据已完成并保存；主报告包含逐项源码位置与修复建议。BLE 使用前台明确连接/收发作为未来第一步；Windows peripheral 支持需检查硬件。iPhone12 mini 具备 Bluetooth 5.0，可作为真机但需核对实际 iOS 部署目标。Apple 当前后台约束与 Qt Wayland 窗口定位限制均已通过官方资料核实。所有平台功能仍是建议，未做设备实测。

追加开发调查：Qt QLowEnergyController 在 Windows 不支持 peripheral，不能直接用同一个Qt BLE服务连接两台Windows。计划先让桌面双方用显式启用的LAN，BLE central适配器连接实现约定GATT的手机前台服务；不把普通蓝牙RSSI当成左右定位。设计依据存入 docs/DEVICE_TRANSFER_DESIGN.md（研究文档）。

修复依赖构建成功，当前验证产物45,025,394 bytes，归档确认Qt6Network、QtNetwork.pyd与qschannel/其他TLS插件存在。没有以历史25.91MiB承诺新包体积；未做冻结包公网TLS/真机UI验收。最后MIME来源去重补丁将再次经过源码测试；构建产物不作为发布附件。
