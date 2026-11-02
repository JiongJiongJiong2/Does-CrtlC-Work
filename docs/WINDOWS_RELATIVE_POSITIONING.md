# 两台 Windows 电脑与屏幕相对方位：可行性调查

调查日期：2026-11-03。本文核对官方接口、原始论文和开源仓库，未运行真实无线电、声学或摄像头实验；文中的 PoC 门槛是研究建议，不是已实现的性能。

**产品边界已更新：两台 Windows 开启蓝牙、运行 exe 后自动发现，最终完成可信匹配和主动文字拖送；不要求手填 IP、端口、密钥，不在本轮新增前端设计。** 当前原生 GATT 广播和 Watcher 只实现发现基础；单一候选不是认证或配对成功，也尚未实现 Windows BLE 文字接收外围端、零配置密钥交换和跨设备动画链路。现状以 [设备传送设计](DEVICE_TRANSFER_DESIGN.md) 和 [开发状态](TRANSFER_PREVIEW.md) 为准。

下文保留相对方位研究的证据。早期“先手动排列设备”的产品建议已被最新要求替代；视觉标记、声学及额外硬件 PoC 只作可选研究，不是当前用户使用步骤，也不表示工具将要求配置屏幕布局。

**研究结论：普通 Windows 电脑现成的蓝牙/Wi-Fi 接口适合发现设备、通信和粗略接近判断，不能据此可靠还原另一块屏幕在左边还是右边、朝向哪里。** 自动发现不等于自动左右检测；后者仍需要额外测量信息、硬件或标定。本文后续对手机拍屏幕标记、声学和无线电配件的比较保留这一独立研究边界。

## 先明确到底要测什么

| 所需信息 | 能解决的问题 | 为什么其他测量不能直接代替 |
|---|---|---|
| 设备身份与在线状态 | 这是不是已配对的另一台电脑，能不能发送 | 信号最强的设备未必是目标设备；同一网络也不代表相邻 |
| 两个传感器之间的距离 | 对方是否接近、是否移动 | 单个距离对应一个圆/球面，左右两边可能等距 |
| 相对方位角/方向向量 | 对方相对本机传感器在哪个方向 | 需要方向测量或有已知几何关系的多次测距 |
| 两块屏幕的相对姿态 | 哪一侧边缘应该对接、屏幕是否旋转 | 无线电通常测天线位置，不直接测屏幕平面和朝向 |
| 显示器与设备的绑定、物理偏移 | 台式机在桌下、两块外接屏如何区分 | 知道机箱位置不能推出显示器位置；笔记本开合角也会变化 |
| 应用中的边缘与落点 | 从 A 屏右边离开，在 B 屏哪里出现 | 还需分辨率、DPI、屏幕 ID 和逻辑坐标映射 |

这里的不可唯一推断属于几何判断：如果观测在镜像摆放后不变，就没有足够依据区分左右。机器学习可能学习特定房间的相关性，但不能凭空消除这种歧义。

Windows `DISPLAYCONFIG_SOURCE_MODE.position` 提供的是本机桌面坐标中的位置，不是显示器的实测物理位置，也不会报告另一台电脑的屏幕布局。因此双方交换屏幕尺寸和逻辑布局很有用，但“读取 Windows 显示设置”不能替代跨设备定位。[Microsoft：DISPLAYCONFIG_SOURCE_MODE](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-displayconfig_source_mode)

## 三档可选路线

| 档位与方法 | 实际能得到什么 | 精度依据与限制 | 对本项目的建议 |
|---|---|---|---|
| 无新增硬件：手动排列屏幕 | 明确的左右、上下、边缘连接关系 | 用户指定；移动设备后需要更新 | 第一版产品默认方案 |
| 无新增硬件：BLE/Wi-Fi RSSI | 信号强度、接近趋势 | 没有适用于任意两台电脑的厘米/角度精度保证；人体遮挡、天线朝向、反射都会混入结果 | 可辅助显示“附近”，不据此自动换目标 |
| 无新增硬件：现有手机摄像头 + 屏幕标记 | 屏幕身份、共同视角下的左右；校准后可求相对姿态 | 依赖相机内参、标记实际尺寸、可见性；本项目尚无实测精度 | 自动校准的首选 PoC |
| 无新增硬件：扬声器与麦克风 | 双向声学飞行时间、距离 | BeepBeep 在论文的两款手机上报告约 1–2 cm、超过 10 m 范围；不能外推为 Windows 保证，也不直接给方位 | 有研究价值的次选 PoC |
| 少量配件：支持测角的 UWB/BLE 阵列或固定锚点 | 距离、方向，组合后可定位 | 精度须按具体芯片、阵列、遮挡条件和安装几何验收；单天线测距标签不等于测角器 | 无摄像头方案的后续验证 |
| 少量配件：ESP32 CSI 节点 | 真实无线信道幅度/相位变化 | 获取 CSI 不等于获得屏幕位置；仍需几何模型、校准或训练 | 适合无线感知实验，不作为第一版依赖 |
| 研究项目：PC CSI、AoA/ToF 联合估计、环境扰动建模 | 条件满足时估计路径、运动或位置 | 特定网卡/固件、阵列标定、多径分离、跨房间泛化均可能成为主要工作 | 独立研究分支，不能承诺通用安装即用 |

声学精度来自原始作者公布的实验，视觉方法来自 OpenCV 的几何接口；表内其他项目没有借用厂商宣传数值作为本项目验收结果。[Microsoft Research：BeepBeep](https://www.microsoft.com/en-us/research/publication/beepbeep-a-high-accuracy-acoustic-ranging-system-using-cots-mobile-devices/)、[OpenCV：ArUco 检测与姿态估计](https://docs.opencv.org/4.11.0/d5/dae/tutorial_aruco_detection.html)

## Windows 常用接口究竟能读到什么

**蓝牙 RSSI。** WinRT 的 `BluetoothLEAdvertisementWatcher` 接收事件有设备地址、广播载荷、时间戳和 `RawSignalStrengthInDBm`，还可能有发送功率字段。这些接口不提供通用的到达角或原始阵列 IQ 数据。扫描别人的广播不要求本机发射，但两台电脑互相测各自广播时，还要确认对端能够运行广播角色并绑定应用身份。BLE peripheral 能力依赖硬件；本项目使用的 Qt 后端又有单独限制，不能把 WinRT 能力等同于 `QLowEnergyController` 在 Windows 上支持 peripheral。[Microsoft：广播事件字段](https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.advertisement.bluetoothleadvertisementreceivedeventargs?view=winrt-26100)、[Microsoft：蓝牙开发 FAQ](https://learn.microsoft.com/en-us/windows/apps/develop/devices-sensors/bluetooth-dev-faq)、[Qt：QLowEnergyController](https://doc.qt.io/qt-6/qlowenergycontroller.html)

**Wi-Fi RSSI。** `WLAN_BSS_ENTRY` 有 AP/对等站标识、`lRssi`、链路质量、频率等。当两台电脑都连到同一路由器时，扫描通常得到各自到 AP 的信号，不会自动得到两台电脑之间的距离或方向。普通网络 ping 混入协议栈、排队与调度延迟，不能当无线电传播时间测量。[Microsoft：WLAN_BSS_ENTRY](https://learn.microsoft.com/en-us/windows/win32/api/wlanapi/ns-wlanapi-wlan_bss_entry)

**CSI 与 RTT/FTM。** CSI 保留更细的子载波信道信息；FTM 在支持硬件上做精确时间测量。它们都不是把 RSSI 多采几次便能获得的数据。Android 官方 RTT 文档给出“对三个及以上接入点测距后，定位通常为 1–2 m”的示例，要求 RTT 能力；这不是两台普通 Windows 电脑现成可用的结果。本轮未核实到能在任意 Windows WLAN 适配器通用调用 CSI/FTM 的桌面接口，实际落地必须先拿到具体厂商 SDK、驱动能力和真数据样本。微软文档站中的 Android 绑定也不能当作 Windows 原生支持证明。[Android：Wi-Fi RTT](https://developer.android.com/develop/connectivity/wifi/wifi-rtt)

PicoScenes 明确要求真实硬件上的 Ubuntu 22.04 系列系统，文档还列出内核及 Secure Boot 条件；它支持 Windows 上解析文件的 MATLAB 工具箱，并不意味着 Windows 原生网卡可以采集 CSI。它的硬件表包含 AX200/AX210 等指定设备，不能由型号相同就推导出 Windows 驱动也开放相同数据。[PicoScenes：安装要求](https://ps.zpj.io/manual/installation.html)、[支持硬件](https://ps.zpj.io/manual/hardware.html)

Nexmon CSI 针对特定 Broadcom/Cypress 芯片和固件，例如 Raspberry Pi 的 bcm43455c0、Nexus 手机芯片及 Asus RT-AC86U，安装路线涉及对应固件环境；它不是通用 Windows CSI 驱动。Espressif 的 ESP-CSI 则用 ESP32 节点获取 CSI，Windows 可以作为串口/网络数据处理端，但采集器仍是额外的 ESP32。[Nexmon CSI 原始仓库](https://github.com/seemoo-lab/nexmon_csi)、[Espressif ESP-CSI 原始仓库](https://github.com/espressif/esp-csi)

**方向测量与更精确测距。** Bluetooth Direction Finding 的 AoA 在接收端使用天线阵列，AoD 在发射端使用阵列；还需要支持的信号和控制器。Channel Sounding 使用多频相位测距和 RTT，重点是距离。蓝牙版本号、MIMO 天线数量或“有两个天线”均不足以证明应用能读取相干测角数据；必须查具体控制器、固件、驱动和 SDK。一个精确的距离仍不能直接选择左/右屏幕边缘。[Bluetooth SIG：Direction Finding](https://www.bluetooth.com/learn-about-bluetooth/feature-enhancements/direction-finding/)、[Channel Sounding](https://www.bluetooth.com/learn-about-bluetooth/feature-enhancements/channel-sounding/)

**UWB。** 需要区分测距与测角配置。例如 Qorvo DWM3001C 官方说明支持双向测距/TDoA，不能仅凭这点把两个模块当成完整相对姿态系统。几何上，多锚点可以约束位置，阵列可以测方向，而屏幕朝向通常仍需刚性安装的多个参考点或额外姿态来源。用户的 iPhone 12 mini 有 UWB；要与 Windows 配合，PC 侧仍需兼容配件和接口。Apple Nearby Interaction 配件协议要求支持的 UWB 芯片，不会让普通蓝牙电脑自动成为 UWB 对端。[Qorvo：DWM3001C](https://www.qorvo.com/products/p/DWM3001C)、[Apple：12 mini 规格](https://support.apple.com/en-in/111877)、[Apple：Nearby Interaction](https://developer.apple.com/nearby-interaction/)

## 电磁轻微扰动、声音和姿态传感器

用户设想的“电磁轻微扰动”有真实物理基础：设备和人体移动会改变多径传播，CSI 可以观测其中一部分变化。但是“环境发生变化”“某个人在移动”“某台电脑在本机右边”和“该电脑外接屏幕朝向本机”是不同推断任务。没有主动标识、传感器几何和校准，家具、人体、开盖角度与目标移动可能产生混淆。Nexmon 的真实示例展示了晃动发送器时 CSI 变化；这能支持变化感知，不能单独证明完整定位能力。[Nexmon CSI 示例](https://github.com/seemoo-lab/nexmon_csi#example)

磁力计/IMU 也可作为辅助，但普通台式机及不少笔记本没有这些传感器。Windows 的方向传感器文档明确要求设备支持，返回的是设备旋转；它不会直接返回另一台电脑的位置。屏幕与底座的开合角、外接显示器的姿态仍需额外标定。把加速度积分成相对位置会累积误差；把周围磁场变化直接归因于对面电脑，也缺乏唯一性。[Microsoft：Orientation Sensor](https://learn.microsoft.com/en-us/windows/apps/develop/devices-sensors/use-the-orientation-sensor)

声学值得单独做小实验。BeepBeep 用双方发声、同时录下自身与对方声音、交换录音内采样间隔，减少时钟同步和软件调度误差。Windows PoC 应先用可听测试声确认链路，验证后再试高频；不能假定所有扬声器/麦克风都能传递接近超声频段，也不能假定音频增强没有修改波形。单一扬声器/麦克风测距不足以求方位；测角需要已知基线和真正独立的采集通道，笔记本麦克风阵列经驱动波束成形后的单声道不能直接当原始阵列数据。[BeepBeep 原始研究](https://www.microsoft.com/en-us/research/publication/beepbeep-a-high-accuracy-acoustic-ranging-system-using-cots-mobile-devices/)

## 电磁传感器实际选项

补充调查：2026-11-03。**有能感知电磁信号的硬件，也确实有能测方向的现成开发套件。** 电脑的 Wi-Fi/蓝牙接收器本身就在接收射频电磁波，问题在于普通应用通常只拿到解码后的数据和信号强度。若增加支持相位/时间测量的接收器与天线阵列，就能获得方向或距离；若改用主动磁信标，则可以建立另一种近距离跟踪系统。下面是三条具体路线，不是全市场最低价排名，也不构成立即购买建议。价格是核查当天的官方美元标价，未计运费、税费或完整实验所需的其他器材。

| 代表路线 | 最小实验布置与能测的量 | Windows 接入 | 成本、体积与关键限制 |
|---|---|---|---|
| Qorvo QM33120WDK1：UWB 测距/测角 | 一套包含 AoA 与非 AoA 两个节点，分别放在 A、B 旁；可试两节点距离和 AoA 支持的角度分量，无需先铺满房间锚点 | USB、厂商 SDK 的 CLI/UCI，官方支持说明提供 Windows Qorvo One 和 Python 会话脚本 | 官方商店整套 **$499**；开发套件是两套 nRF52840 板加天线子板，不是两个迷你 USB 棒。不能把一个角度分量当成完整屏幕姿态 |
| Silicon Labs BG22-PK6022A：BLE AoA | A 侧一个阵列定位器，B 侧一个发送 CTE 的标签；得到 B 相对阵列的方向。要房间坐标可增加已标定的定位器 | 官方主机例程支持 Windows COM/TCP，角度经 MQTT 输出，应用可独立订阅 | 阵列套件 MSRP **$299**，阵列 **160 × 160 mm**；另需标签。BG22-EK4108A 官方价 **$16**，支持 direction finding，可作为标签候选，须先验证所选 SDK 例程 |
| 主动磁信标：低频线圈 + 磁传感/接收线圈 | A 侧已知位置、方向与激励时序的线圈，B 侧三轴传感器；先验证能否分离自己的磁场。完整姿态需多轴/多线圈与校准，不能仅凭一块磁力计完成 | 简单原型可由 MCU 读 I²C/SPI 后经 USB 串口给 Windows；研究系统有 USB/DAQ 路线 | Adafruit LIS3MDL 板 **$12.50**、**25.7 × 17.8 × 4.6 mm**，但只是传感板价格；线圈、驱动、MCU、供电与标定未计入。完整系统费用需按设计核算，接收器小不代表发射器小 |

UWB 套件组成与能力来自 [Qorvo 产品页](https://www.qorvo.com/products/ek/QM33120WDK1)，价格来自 [官方商店](https://store.qorvo.com/products/detail/qm33120wdk1-qorvo/716316/)，Windows/CLI/UCI 入口来自 [Qorvo 工程师说明](https://forum.qorvo.com/t/characteristics-of-development-kit-qm33120wdk1/15815)。BLE 阵列与标签的规格/价格来自 [BG22-PK6022A](https://www.silabs.com/development-tools/wireless/bluetooth/bgm22-pro-kit)、[BG22-EK4108A](https://www.silabs.com/development-tools/wireless/bluetooth/bg22-explorer-kit)；主机接口来自 [单定位器例程](https://docs.silabs.com/rtl-lib/11.1.2/rtl-lib-app-development/03-single-locator-sample-application)。磁传感板规格与价格来自 [Adafruit 官方页面](https://www.adafruit.com/product/4479)。

**UWB 更适合同时验证距离和方向。** 选型时必须确认实际装配的是 AoA/PDoA 硬件和天线，不要为了便宜改买两个只支持单天线测距的标签，再期待软件自动增加方向能力。单天线测距方案可以通过已知位置的多个锚点约束坐标，但会增加安装、供电和几何标定。QM33120WDK1 的主机演示只是入口；仍需验证两个节点分别接在两台电脑时的角色配置与数据输出，并核实有效角度范围、前后歧义及遮挡行为。本轮未下载运行 SDK，没有承诺具体角度精度。

**BLE AoA 更直接对应“对方在左还是右”。** A 侧固定阵列，B 侧标签发出带身份的 CTE，阵列比较不同天线接收的相位；Windows 程序读角度结果即可，不必修改本机蓝牙驱动。它不要求两台电脑都装同样大小的阵列：只要 A 判断 B 的方向，一个阵列加一个标签就能开始。若要求两端都直接测方向，需要再设计对称部署。一个定位器给出的方向不等于精确位置，多个定位器才可通过几何约束解算位置。[Silicon Labs：架构、标签与定位器要求](https://docs.silabs.com/rtl-lib/11.1.2/rtl-lib-app-development/01-introduction)

**磁力计与 GHz 无线接收器是不同东西。** LIS3MDL 是测三轴磁场的传感器，通常用来测地磁、磁铁和较慢变化的磁场；其输出速率最高为特定模式下的 1000 Hz，不能直接读取 2.4/5 GHz Wi-Fi 波形。I²C/SPI 的通信速率也不是传感器的射频接收带宽。增加这种板子可以观察局部磁变化，却不会把它变成 Wi-Fi 测向仪；磁场向量的方向也不总是指向磁体位置。[ST：LIS3MDL 数据手册](https://www.st.com/resource/en/datasheet/lis3mdl.pdf)

磁路线可以比“猜电脑自然泄漏的电磁扰动”更有控制性：让目标主动按已知时序激励线圈，再从背景中提取同一时序的响应。简单原型只能先证明检测与区分；单线圈、单测点存在位置/朝向歧义，磁偶极近场随距离迅速衰减，电脑钢件、磁铁和电源也会改变背景。完整跟踪必须验证多轴激励、相位/极性、初始位置与环境变化，不能用固定桌面的磁场指纹宣称任意两台设备的相对姿态。

这条路线有可参考的真实开源研究。**Aura** 用三个主动发射线圈和三轴接收线圈恢复相对六自由度姿态；论文在手臂可及范围报告位置中位误差 5.5 mm、角度 0.8°。它使用约 100 kHz 激励、专用接收与解调电路，不能用 LIS3MDL 直接替代；其中一个发射线圈约 20 × 7.5 cm，说明原型仍有尺寸成本。论文数据不能外推为桌面两电脑的结果。[Aura 原始论文](https://www.ericwhitmire.com/pdfs/aura.pdf)

[Aura 原始仓库](https://github.com/ubicomplab/Aura) 实际包含发射/接收固件、PCB 和处理代码，可作为设计起点；本轮没有完成构建复现。另一例 [Anser EMT 原始仓库](https://github.com/BioDesignUCCAdmin/AnserEMT) 明确要求已组装的发射线圈、放大器、支持的 DAQ 和 MATLAB，文档使用 Windows 设备管理器确认连接。这说明电磁跟踪能由 Windows 驱动，但“开源”不代表只买一颗小传感器就获得完整定位器。

**USB SDR 也能感知电磁信号，但普通两个接收棒不自动构成测角仪。** 测相位差需要共同时间/频率参考、相位校准和已知天线间距。KrakenSDR 是实际可用的五通道相干例子，官方解释了为什么把多个独立 RTL-SDR 插到同一电脑仍不相干。[KrakenRF：工作原理](https://www.krakenrf.com/about-krakensdr)

KrakenSDR 当前官方标价 **$749**，不含天线；标准范围 **24–1766 MHz**，因此不能直接用来接收 2.4/5 GHz Wi-Fi。其相干采集软件面向 Linux/Raspberry Pi，Windows 作为结果消费者还需另外接入。若目标是 Wi-Fi 频段，须另选覆盖该频段的相干多通道 SDR，并验证同步、带宽与驱动；这比 BLE/UWB 套件更像射频研究平台，不是当前最小验证组合。[KrakenSDR 官方规格与价格](https://www.krakenrf.com/product-page/krakensdr)

**最小验证建议：先只验证“左右”，不要一次做完整姿态。** 如果能借到上述 BLE AoA 或 UWB AoA 套件，把定位器刚性放在 A 屏顶部，约定其左右轴与屏幕一致；将目标标签固定在 B 屏顶部，以 0.5、1、2 m 和左/中/右多个角度记录身份、原始角度、质量指标及时间。重复左右交换、旋转 B 屏、人体遮挡和移动金属物体。左右判断在这些变化下稳定之后，再接入边缘菜单；角度无效或接近分类边界时返回未知。旋转 B 屏但保持标签位置不变，通常不会给出足够信息恢复 B 的朝向，这应单独测试和标定。

若先研究最低物料成本的磁方案，则从一个低频主动信标加一个三轴传感板开始，只测试“能否在实际桌面距离下稳定检测自己的编码磁场”，并记录信标关闭时的假响应。没有足够信噪比或换位置就完全失效时停止定位承诺，先解决硬件问题；不要直接训练左右分类掩盖问题。无论哪条路线，传感器都应绑定到**具体显示器**，不是只绑到桌下的主机；屏幕移动、配件拆装后重新校准。

## “隔墙 Wi-Fi GitHub”候选核查

用户没有给具体链接，目前不能确定指的是哪个项目。以下是相关候选或研究来源，不能混为一个已经实现了屏幕定位的项目。

**RuView（ruvnet/RuView）。** 核查固定版本 `5728b90949e60e3f908d996997d453147c1794e0`。README 的无硬件 Docker 快速启动使用模拟数据；真实 CSI 路线要求 ESP32/研究网卡，普通电脑 RSSI 路线只有粗粒度感知。双模态演示说明摄像头提供人体姿态真值，因此有骨架演示画面并不能证明“单靠普通电脑 Wi-Fi 已准确测到人体/设备”。[固定版本 README](https://github.com/ruvnet/RuView/blob/5728b90949e60e3f908d996997d453147c1794e0/README.md)

该版本文档与代码还有值得注意的不同步：README 称一个运行路径仍是 `confidence=0` stub；实际 `inference.rs` 已有权重加载和网络前向计算，缺权重才回退，不能据旧描述把整个项目判为“只有模拟”。同时，其输出明确标记为 `normalized-image`、`metric: false`，并不提供厘米制屏幕坐标。是否可重现必须分别验证输入来源、权重、推理路径、指标与目标任务。当前更适合参考采集/处理结构，不适合直接将人体模型接到拖送边缘判断。[固定版本推理源码](https://github.com/ruvnet/RuView/blob/5728b90949e60e3f908d996997d453147c1794e0/v2/crates/cog-pose-estimation/src/inference.rs)

**DensePose From WiFi。** 原论文处理人体表面与关键点，使用同步 CSI/视频数据和视觉伪标签训练；不是两台 PC 的六自由度相对定位。其换布局测试中，人框 AP 从 43.5 降为 27.3，说明环境泛化是实际问题。论文引用的 Detectron2/DensePose 链接是视觉教师模型来源，不应当误认成任意 Windows 网卡即插即用的 Wi-Fi 驱动/完整实现。[原始论文，尤其 4.1、4.7 节](https://arxiv.org/html/2301.00250v1)

**MIT RF-Pose。** 官方项目确实研究无线电穿墙人体姿态，使用视觉模型提供跨模态监督；对象仍是人体，不能从项目名称中的 Wi-Fi 频段推导出任意消费级 Windows 网卡可运行。本轮确认了官方项目说明，未完成其硬件复现审计，也未确认它就是用户提到的 GitHub 项目。[MIT RF-Pose 官方项目](https://rfpose.csail.mit.edu/)

这些研究能启发“利用多径作为信息”“把数据质量和不确定性显式化”，但 DoseCtrlC 所需的屏幕身份、方向和边缘映射必须重新定义数据与评价目标。

## 推荐先做的三个 PoC 与停止条件

**先做可用交互。** 在两台电脑配对后，让用户摆放屏幕卡片，并给每块实际显示器独立 ID。局域网或蓝牙只负责发现与文本交付，位置配置决定边缘。移动设备后让用户重新确认；设备在线状态不能自动修正空间布局。这样可以先检验拖动、边缘菜单、释放、接收确认与动画是否自然。

**自动校准首选：手机拍屏幕标记。** 两屏各显示带唯一身份的 ArUco/ChArUco 标记，用户用现有 iPhone 的同一摄像头同时拍到两屏。第一步只做共同画面中的相对排列建议并让用户确认；这是图像方位，不宣称已恢复完整三维几何。要进一步求姿态，需校准镜头内参、知道标记实际物理尺寸，估计两屏到同一相机的变换，再计算 `T_A_B = inverse(T_camera_A) * T_camera_B`。尺寸可由用户量取；不能只凭未经验证的显示器尺寸元数据。两块笔记本自带摄像头通常都朝用户，不能假定彼此看得见。[OpenCV：标记姿态估计](https://docs.opencv.org/4.11.0/d5/dae/tutorial_aruco_detection.html)

建议测试至少 30 种布置，包含左右交换、不同高度、屏幕旋转、手机旋转、遮挡和反光；报告识别成功率、错误方向率与拒绝判断率，分别记录，不能用大量拒绝掩盖错误。初始目标可定为有效识别帧中方向正确率至少 95%，但该小样本门槛只是继续开发的信号，不是上线可靠性证明。平面标记的歧义、标记过小、遮挡或重投影误差过大时必须返回未知。如果换手机姿势就经常翻转方向，停止自动应用，只保留手动确认。姿态解算应增加多标记/多视角一致性检查；单帧低误差并非正确解保证。[OpenCV：ArUco FAQ 中的姿态歧义](https://docs.opencv.org/4.7.0/d1/dcb/tutorial_aruco_faq.html)

**声学并行小实验。** 在两台电脑之间以尺量出 0.3、0.6、1、2 m 等距离，双方自录测试声并交换采样间隔；分别测安静、有人移动、不同音量及启用/关闭音频增强条件。先验证近远排序和测距稳定性，可暂以中位绝对误差小于 10 cm、95 分位小于 25 cm 作为桌面短距实验目标。若回声峰选择不稳定、换音频设备就有无法校准的偏差，停止自动测距路线；若拿不到独立阵列通道，不继续声称能声学测方向。这里没有借用手机论文结果充当笔记本实测。

**无线电实验的入口门槛。** 记录双方具体网卡/蓝牙型号、驱动版本和传感器能力。先证明拿到对端已标识发射产生的真实 RSSI/CSI/IQ/FTM 样本，再讨论算法；明确模拟输入、回放文件和现场采集。若只有 RSSI，就把实验限定为接近提示。如果选择 CSI，先在新房间、换摆放和人体遮挡条件下重测；只在训练时那张桌子有效的左右分类不能作为通用定位。若目标需要额外阵列/配件，另行选型验证 Windows 数据接口，不在主开发机上直接替换研究驱动。

## 与 DoseCtrlC 后续逻辑的接口

建议将方位估计做成独立的 `RelativePlacementProvider`：返回源/目标设备及屏幕 ID、可选的方向或边缘建议、观测来源、质量指标、校准版本、时间和有效状态。手动布局、摄像头标定、未来 UWB 都可实现同一接口；未知字段保持未知。未校准的模型分数不得包装成真实概率或厘米精度。

传输会话在释放鼠标时锁定目标和内容；异步测量不得在拖拽中途静默切换目标。已确认布局失效时显示重新校准，接收动画用接收端屏幕的归一化边缘坐标映射。自动方位是交互辅助，不负责身份认证，也不能代替传输确认。

实验只针对自己的已授权设备；摄像头/麦克风在显式校准期间开启，默认仅保留标记位置、采样间隔和质量统计，不保存房间视频或谈话。CSI/声学结果同样可能反映周围人的活动，因此应避免把周围环境感知数据作为日常剪贴板功能的默认持续采集内容。

本轮没有修改产品代码，没有安装驱动、购买硬件或运行真实感知实验。最快下一步是验证两屏视觉校准；若用户更关注纯无线电研究，再用明确的硬件组合建立独立 PoC。
