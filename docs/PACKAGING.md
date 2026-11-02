# Windows 打包瘦身指南

> 2026-11-03 更新：v2.3.1 的可取消预览服务使用 QtNetwork，spec 已恢复 QtNetwork 与 TLS 插件。下文的 7 月体积表及 v3 裁剪是历史实验，不能继续照此排除网络运行时。构建使用 `.venv`、`requirements-build.txt` 和 `build.bat`；版本从 `app_version.py` 生成。

## 结论

当前 `dist/DoesCtrlCWork.exe` 是 45.73 MiB 的旧 PyInstaller onefile 产物（2026-06-17）。体积主要来自 Python 运行时与 PySide6/Qt，不是业务 Python 代码。它甚至仍带有已经移除的 `pyperclip` 构建痕迹，因此必须先从当前代码重建基线，不能把旧 exe 当作发布候选。

当前应用实际使用 `PySide6.QtCore`、`PySide6.QtGui`、`PySide6.QtWidgets` 和 `PySide6.QtNetwork`；不使用 QML、Qt Quick、PDF、SVG、Virtual Keyboard 或 Qt OpenGL API。

> `build.bat` 和 README 均使用受版本控制的 `DoesCtrlCWork.spec`，并生成唯一的 `DoesCtrlCWork.exe`。请不要手工创建临时 spec，否则裁剪结果无法复现。

## 当前归档的主要体积来源

下表是 exe 内压缩后大小；实际运行时会解压成更大的临时目录。

| 组件 | 归档内大小 | 是否为核心需求 |
|---|---:|---|
| `PySide6/opengl32sw.dll` | 7.64 MiB | 候选排除，需验证 Qt Widgets 的图形回退 |
| `Qt6Gui.dll` | 4.06 MiB | 必需 |
| `Qt6Core.dll` | 3.53 MiB | 必需 |
| `Qt6Quick.dll` | 2.78 MiB | 不需要 |
| `python314.dll` | 2.60 MiB | 必需 |
| `Qt6Pdf.dll` | 2.35 MiB | 不需要 |
| `Qt6Qml*.dll` | 2.55 MiB | 不需要 |
| `Qt6Widgets.dll` | 2.58 MiB | 必需 |
| `Qt6Network.dll` / `QtNetwork.pyd` | 1.11 MiB | 历史体积；现为必需 |
| `Qt6OpenGL.dll` | 0.38 MiB | 不需要 Qt OpenGL API |
| Qt 翻译、TLS、非 Windows 平台和多余图像插件 | 分散 | 大多不需要，逐组验证 |

仅 Qt Qml/Quick/Pdf/VirtualKeyboard/OpenGL、软件 OpenGL 和其关联内容就有约 16 MiB 的归档内空间可作为首轮实验目标。实际收益取决于动态依赖，不能承诺精确数字；本项目的第一轮实验已达到约 26 MiB，而不是期待 PySide6 GUI 变成几 MiB。

## 已执行的实验结果（2026-07-13）

| 构建 | 文件大小 | 相对当前代码基线 | 自动验证 |
|---|---:|---:|---|
| 未裁剪基线（PyInstaller 6.21.0） | 45.74 MiB | — | 构建成功；不含已移除的 pyperclip |
| v1：翻译、未使用模块与低风险插件 | 34.27 MiB | -11.48 MiB / -25.1% | 归档检查、15 项离屏测试、3 秒启动通过 |
| v2：v1 + `opengl32sw.dll` | **26.98 MiB** | **-18.77 MiB / -41.0%** | 归档检查、3 秒启动通过 |
| v3：v2 + `Qt6Network.dll` / `QtNetwork.pyd` | **25.91 MiB** | **-19.84 MiB / -43.4%** | 归档检查、15 项离屏测试、4 秒启动通过 |

当时的 `DoesCtrlCWork.spec` 固化了 v3 规则；现已恢复 QtNetwork/TLS，需重新测量体积。当前构建仍需在真实桌面完成复制文本、图片、多图、Holding、托盘和高 DPI 手动验收。

## 你需要做什么

### 1. 固定一份可复现的基线构建

不要使用全局开发环境，也不要复用旧 `build/`。在新的虚拟环境中安装当前依赖和同一版本的 PyInstaller，然后构建一次未裁剪基线，记录 exe 大小与测试结果。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-build.txt
.\.venv\Scripts\python -m PyInstaller --noconfirm --clean DoesCtrlCWork.spec
```

将输出的大小、Python/PySide6/PyInstaller 版本写入发布记录。当前开发机为 Python 3.14.4、PySide6 6.11.1、PyInstaller 6.20.0；旧包没有使用 UPX（系统 PATH 中没有 `upx`）。

### 2. 从低风险项开始逐组排除

在 `DoesCtrlCWork.spec` 中建立明确的裁剪列表，**每次只新增一组**，然后重新构建与验收。建议顺序：

1. Qt 翻译：程序没有安装 `QTranslator`，可先排除全部翻译资源。
2. 明确不用的模块：QML、Quick、Pdf、VirtualKeyboard、Svg、Qt OpenGL API。
3. 插件：保留 Windows 的 `qwindows` 平台插件与 TLS；只考虑移除确认不用的插件。
4. `opengl32sw.dll`：可能承担 Qt 的动态回退路径，必须单独验证。QtNetwork 现在被直接使用，不可排除。

不要以删除 site-packages 中的 DLL 作为方案；这会破坏开发环境，也不能保证构建可复现。应通过 spec 的收集结果或项目内自定义 PyInstaller hook 排除，使规则进入 Git。

### 3. 每个候选包的验收

在干净 Windows 用户环境（最好虚拟机）验收：

- 启动、退出、托盘图标和高 DPI；
- Ctrl+C 文本、相同文本再次复制、中文/emoji、空复制；
- 本地图片、网页 JPEG/PNG、data URI、多图及网络图片；
- Ctrl+V、静默模式和 Holding 模式；
- 无控制台错误、无 `Qt platform plugin` 错误，启动时间不倒退。

只要一组失败，恢复这一组，再拆成更小的项。PyInstaller 官方也建议先验证 onedir，再做 onefile；onefile 会在每次启动时解压到临时目录，体积不会因此显著变小，启动反而略慢。

### 4. 再考虑替代构建器，而不是重写语言

如果精简 PyInstaller 后仍不满意，再做 `pyside6-deploy`（Nuitka）的独立对比包。它能根据项目使用的 Qt 模块和插件进行部署，但它是**构建实验**，不是保证更小的替代品；保留大小、冷启动和完整功能矩阵后再选择。

## 不建议的做法

- 不为减小 exe 把业务代码改成 C++；PySide6/Qt 和 Python runtime 仍会被携带，收益很低。
- 不只比较单文件的大小；要同时比较解压后的总大小、冷启动、内存和功能。
- 不一次删除所有 Qt 插件；图片解码和平台插件会在运行时按需加载，必须分组测试。

## 依据

- [PyInstaller：onefile 与 onedir 的工作方式](https://www.pyinstaller.org/en/stable/operating-mode.html)
- [PyInstaller：spec 文件](https://pyinstaller.org/en/stable/spec-files.html)
- [Qt for Python：pyside6-deploy](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html)
