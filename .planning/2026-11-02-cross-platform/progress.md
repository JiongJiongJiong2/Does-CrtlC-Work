# 本轮进度

2026-11-02：读取 README、CURRENT_PROJECT_FACTS 和历史计划/日志，审查 git 状态与提交记录。并行安排核心逻辑和历史/Windows 耦合点只读审查。开始核实 Qt、Apple 与 Linux 官方平台边界。未修改产品代码。

执行既有 Windows 离屏回归：81/81 通过。对照官方文档发现 PySide6 iOS 部署能力已有新变化，建议将“系统权限边界”和“框架能否部署”分开，避免旧知识误导。历史架构和事件风险分别由子任务独立核查。

完成：新增 docs/CROSS_PLATFORM_REVIEW.md 并接入文档索引。四项隔离缺陷复现保存为 audit_repro.py / audit_repro.log，退出码 0。核对报告与源码、现有依赖版本及输出；git diff --check 通过（仅既有换行配置提示 LF 将转 CRLF）。Git 状态只含分析目录、新报告和文档索引修改。未进行构建、真实桌面/手机/BLE 验收、提交或推送。

2026-11-03 追加授权实施：完成会话关联、旧retry失效、UI会话过滤、GUI命令bridge、修饰导航键、应用级预览服务、默认禁用远程请求/公网固定IP与重定向拒绝、资源预算、日志轮转、实例锁、版本源和构建依赖。首次完整测试113项中的原有120ms帧率测试在繁忙环境失败（7帧/要求9帧）；改为精确定时器配置+有界等待进展+停止语义后，新增退出轮询用例，完整114/114通过，2.530秒。此更改不宣称实际帧率提升。

旧audit_repro.py是修复前缺陷证据，断言预期缺陷存在；不再用作修复后的通过标准。新的tests/test_clipboard_sessions.py、test_app_sessions.py、test_image_preview.py承担回归。构建使用隔离build/reliability与packaging-artifacts/reliability，未覆盖旧dist。

最终补充MIME来源组选择和去重，普通文本URL不再触发请求，新增3项回归。修复源码完整117项通过。依赖构建成功且归档有QtNetwork/TLS；最后MIME补丁经过源码测试，安装包不作为发布附件（需重新打包和真机验收）。准备提交/推送修复到master，再切扩展分支。

修复已提交edc3f26。第一次push因自动审批认为目标归属未核实而拒绝；使用已连接GitHub核实当前用户ID与repo owner ID相同且具有admin/push权限，原origin已重命名为JiongJiongJiong2/Does-CrtlC-Work。携此证据再次审批放行，push成功，远端master SHA确认为edc3f2666087660258759ba59dac2f5a26bd8bf2。随后建立feature/device-transfer分支。

用户追加要求专门研究Windows相对位置/屏幕方位与隔墙Wi-Fi项目，已创建wireless_positioning子agent。同时开始LAN协议/显式接收与边缘拖放UI实现；AES-GCM每peer密钥仅内存，默认不扫描/监听、不自动写接收文本到剪贴板。BLE将作为实验适配器单独标注，未声称真机可用。

产品方向更正：用户明确不要新前端及任何手填信息，要求两台电脑打开蓝牙并运行 exe 后自动发现、匹配。已撤下未提交的手工配置/边缘投放窗口及对应截图，移除主入口快捷键和导入。LAN/AES-GCM/Qt BLE central仅保留内部实验；正常启动改为Windows原生自动发现与15秒后台重试，不读写或传送剪贴板正文。

单机实测：adapter支持LE/peripheral。初次创建服务返回RADIO_NOT_AVAILABLE；用户随后明确已打开蓝牙。继续发现IsConnectable=False不能实际广播，ServiceData虽仅7字节仍与系统UUID广告竞争容量。最终改用legacy SERVICE_UUID广告（connectable+discoverable均True），ca13仅公开只读version+进程随机身份。Watcher识别本应用UUID，以蓝牙地址6字节为临时发现key；不将其描述为可信设备身份。原生广播/扫描已真实启动，6秒后正常清理，其他本应用设备观测数0，尚无双机互通证据。

代码审查另修复WinRT RSSI=-127旧离线事件刷新TTL、事件循环从非托盘路径结束时未清理线程的问题。原生初始化瞬间ABORTED/SUCCESS使用有界启动容忍，持续错误仍中止并后台重试。完整203项回归通过，compileall通过。生产依赖包含有Windows平台标记的PyWinRT，spec使用官方hook收集6张投影表及runtime.pyd，首次冻结构建成功并核实归档内容，正在对最终源码重新构建及启动退出验证。

最终冻结验收发现并修复构建环境PATH误收Poppler ICU的问题：错误icuuc.dll缺少QtCore所需全部20个无后缀函数。两个独立代理核对PE符号，spec排除误收icuuc.dll及其孤立icudt78.dll，使用Windows系统ICU。重建后的exe为32,606,204字节，SHA256 43781f6a9e84ffce7fb993ca6edf372eeb1fd9db6f1e6734753cac7883fc573b。实际运行--smoke-test：正常创建应用并启动本机BLE广播/扫描，10秒后退出码0；归档含6张WinRT表和runtime，不含错误ICU。用户原有Desktop/A旧版进程未改动。本阶段首个自动发现增量完成，未实现双机文字互传、自动认证或iPhone接收端；这些在开发状态中明确保留为后续工作。
