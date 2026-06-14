# C++ 混合重构计划

> 状态：规划中，暂不执行  
> 创建时间：2026-06-15

## 背景

当前 Dose Ctrl+C 全部使用 Python + PySide6 实现。对于核心高频模块，C++ 能带来明显收益，但需要权衡开发成本与部署复杂度。

## 收益分析

| 模块 | 当前瓶颈 | C++ 收益 | 优先级 |
|------|---------|---------|-------|
| 图片像素化/缩放 | QImage.scaled 频繁调用 | ★★★★★ 极大减少内存拷贝与延迟 | **高** |
| 剪贴板 MIME 解析 | 多次 MIME 查询、base64 解码 | ★★★★ 减少 GIL 竞争，加速解码 | **高** |
| 弹簧物理动画 | 每帧计算，Python 函数调用开销 | ★★★ 数值计算快但帧率已够 | 中 |
| 全局热键监听 | keyboard 库后台线程 | ★★ 替换成本高但更稳定 | 低 |
| 系统托盘 | PySide6 QSystemTrayIcon | ★ 无明显瓶颈 | 无 |

## 推荐方案：pybind11 混合扩展

### 架构

```
dose-ctrlc/
├── cpp_core/                    # C++ 源码
│   ├── CMakeLists.txt
│   ├── src/
│   │   ├── image_processor.cpp   # 像素化、缩放、base64 解码
│   │   ├── clipboard_parser.cpp  # MIME 解析、HTML <img> 提取
│   │   └── spring_physics.cpp    # 弹簧缓动计算
│   └── include/
│       ├── image_processor.h
│       ├── clipboard_parser.h
│       └── spring_physics.h
├── binding/                      # pybind11 绑定
│   └── core_bindings.cpp
├── core/
│   ├── clipboard_monitor.py      # 保留，调用 C++ 加速函数
│   └── mouse_tracker.py
└── ui/
    └── feedback_widget.py        # 保留，QPainter 调用 C++ 预处理数据
```

### C++ 核心模块设计

#### 1. ImageProcessor

```cpp
// image_processor.h
#pragma once
#include <QImage>
#include <vector>
#include <string>

class ImageProcessor {
public:
    // 像素化：将 QImage 缩放到 block 像素块再放大回来
    static QImage pixelate(const QImage& src, int blockSize);

    // 快速缩放（双线性，替代 Qt 的 SmoothTransformation）
    static QImage fastScale(const QImage& src, int targetSize);

    // base64 解码为 QImage
    static QImage fromBase64(const std::string& b64Data);

    // data URI 解码
    static QImage fromDataUri(const std::string& uri);

    // HTTP 下载 + 解码（异步，回调）
    using ImageCallback = std::function<void(QImage)>;
    static void fetchHttpImage(const std::string& url,
                                int timeoutMs,
                                int maxBytes,
                                ImageCallback cb);
};
```

#### 2. ClipboardParser

```cpp
// clipboard_parser.h
#pragma once
#include <QImage>
#include <QString>
#include <QList>
#include <QUrl>
#include <vector>
#include <string>

struct ClipboardPayload {
    std::string text;
    std::vector<QImage> images;
    int imageCount = 0;
};

class ClipboardParser {
public:
    // 从 QMimeData 提取完整负载
    static ClipboardPayload extract(const QMimeData* mimeData);

    // HTML img src 提取
    static std::string extractImgSrc(const std::string& html);

    // 文件路径规范化
    static std::string normalizePath(const std::string& text);
};
```

#### 3. SpringPhysics

```cpp
// spring_physics.h
#pragma once

class SpringPhysics {
public:
    SpringPhysics(double stiffness, double damping);

    double step(double dt);       // 推进 dt，返回当前值
    double value() const;         // 当前值
    void   setTarget(double target);
    void   reset(double initialValue);

private:
    double stiffness_, damping_;
    double value_, velocity_, target_;
};
```

### 构建流程

```bash
# 前提：安装 VS Build Tools 2022 + CMake + Python dev headers

# 1. 构建 C++ 扩展
cd dose-ctrlc/cpp_core
mkdir build && cd build
cmake .. -G "Visual Studio 17 2022" -A x64 ^
    -DPython_ROOT="C:/Python312" ^
    -Dpybind11_DIR="C:/Python312/Lib/site-packages/pybind11/share/cmake/pybind11"
cmake --build . --config Release

# 产物：_dose_ctrlc_core.pyd (Release/)

# 2. 拷贝 .pyd 到项目根
cp Release/_dose_ctrlc_core.pyd ../../

# 3. Python 端使用
# from _dose_ctrlc_core import ImageProcessor, ClipboardParser
```

### PyInstaller 打包适配

```spec
# DoesCtrlCWork.spec 关键变更
a = Analysis(
    ['main.py'],
    datas=[('config.py', '.'), ('_dose_ctrlc_core.pyd', '.')],
    binaries=[('_dose_ctrlc_core.pyd', '.')],
    ...
)
```

注意事项：
- `.pyd` 文件必须与打包用的 Python 版本/架构一致
- 运行时需要匹配的 VC++ Runtime（`vcruntime140.dll` 等），PyInstaller 通常自动收集
- CI 环境需要固定 Python 版本 + 编译工具链版本

### CMakeLists.txt 模板

```cmake
cmake_minimum_required(VERSION 3.16)
project(dose_ctrlc_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(pybind11 REQUIRED)
find_package(Qt6 REQUIRED COMPONENTS Core Gui)

pybind11_add_module(_dose_ctrlc_core
    binding/core_bindings.cpp
    src/image_processor.cpp
    src/clipboard_parser.cpp
    src/spring_physics.cpp
)

target_link_libraries(_dose_ctrlc_core PRIVATE Qt6::Core Qt6::Gui)
target_include_directories(_dose_ctrlc_core PRIVATE include)
```

## 全 C++ Qt 方案（远期备选）

如果未来决定全量迁移到 C++ Qt：

- **框架**：Qt 6 + CMake
- **部署**：`windeployqt` + NSIS 安装器
- **优势**：单进程、无 GIL、启动更快、无 PyInstaller 坑
- **代价**：开发周期长、跨版本编译维护成本高

## 实施路线

| 阶段 | 内容 | 预计时间 |
|------|------|---------|
| Phase 1 | 抽取 ImageProcessor 为 C++ 扩展 | 2-3 天 |
| Phase 2 | ClipboardParser C++ 化 | 2 天 |
| Phase 3 | SpringPhysics C++ 化（可选） | 1 天 |
| Phase 4 | CI 自动编译 .pyd + 集成测试 | 1-2 天 |
| Phase 5 | PyInstaller 打包验证 | 1 天 |

## 风险

1. **版本耦合**：.pyd 与 Python 版本强绑定，发布需多版本编译
2. **VC++ Runtime**：用户机器可能缺少对应 Runtime，需在安装器中包含
3. **调试复杂度**：C++ 段崩溃时 Python 端无有效 traceback
4. **CI 成本**：需维护 Windows + macOS（如需）编译环境