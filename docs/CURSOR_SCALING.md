# 鼠标尺寸自适应反馈方案

## 目标

当 Windows 辅助功能或第三方主题使用较大鼠标指针时，复制反馈适度增大并避开指针；普通指针下保持现有视觉、尺寸和动画手感不变。

核心约束：内容最多放大到 1.50 倍，不能与极端鼠标尺寸线性无限增长。

## 尺寸来源

Windows 每次创建反馈时读取一次当前全局 `HCURSOR`：

1. `GetCursorInfo` 取得当前 cursor handle。
2. `GetIconInfo` 取得 color/mask bitmap 与 hotspot。
3. `GetObject` 读取 bitmap 宽高；黑白 cursor 的 mask 高度需要除以 2。
4. 释放 `GetIconInfo` 返回的 bitmap handle。
5. 用鼠标所在 `QScreen.devicePixelRatio()` 将物理像素换算为 Qt 设备无关像素。
6. 读取 Windows 用户设置的 `HKCU\Control Panel\Cursors\CursorBaseSize`；当它大于当前 cursor 资源尺寸时，以它作为辅助功能显示尺寸并同比例放大 hotspot。

官方依据：

- <https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getcursorinfo>
- <https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-geticoninfo>
- <https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-iconinfo>
- <https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-getobject>
- <https://doc.qt.io/qt-6/highdpi.html>
- <https://learn.microsoft.com/en-us/uwp/api/windows.ui.viewmanagement.uisettings.cursorsize>

## 比例与偏移

| Cursor 最大边（DIP） | UI 比例 |
|---:|---:|
| `<= 40` | 1.00 |
| `41–56` | 1.15 |
| `57–72` | 1.30 |
| `> 72` | 1.50（上限） |

偏移不直接等于 UI 比例。默认 32 DIP 鼠标保留原 16 DIP 偏移；超过默认尺寸时，偏移移动到 hotspot 至右/下边缘之外并留出间隙，最多 160 DIP。UI 内容仍最多 1.50 倍，位置避让与内容缩放独立限制；接口失败或非 Windows 平台统一回退到比例 1.00 和原 16px 偏移。

## 防错位策略

所有组件继续使用当前逻辑坐标；`FeedbackWidget.paintEvent` 在入口统一缩放 QPainter。窗口尺寸、鼠标锚点和屏幕边界使用同一个比例换算。

不要分别修改 ContentBox、ImageRenderer、StackLayer、DOT 常量和动画属性，否则会形成多套坐标系。任何组件内部的 transform 必须与外层 scale 组合，不能覆盖它。

一次反馈只读取一次 cursor metrics，动画期间固定比例。光标从箭头变成 I-beam 或手形时不会让正在显示的反馈跳变。

本版使用 cursor bitmap canvas，而不扫描每个透明像素的真实可见边界。少数带大量透明边距的第三方 cursor 可能被高估，但 1.50 内容上限和 160 DIP 偏移上限会限制影响；为这一边缘情况增加逐像素分析不符合当前小项目的复杂度目标。

## 屏幕边缘停靠

反馈窗口带有用于动画的透明画布，不能以整个 QWidget 的 500×180 最小尺寸直接做边界 clamp；否则短文本在底边会提前约一整块透明高度停住。

- 底边：按可见文本框/图片的实际 bottom 计算。到达可用工作区底部后，可见内容底部保留 12 DIP 安全距离，透明尾部允许越过屏幕；纵向停靠后仍继续跟随鼠标的横向移动。
- 右边：当正常向右布局的可见 right 会越过安全距离时，切换为镜像空间布局。黄点与两段黄线固定在右边，内容框、渐隐背景、图片和图片堆叠延伸到左边；文字不做几何镜像，仍以正常方向阅读。
- 安全距离按 UI 缩放倍率换算；多屏时始终以鼠标所在 `QScreen.availableGeometry()` 为准。

### Windows 任务栏边界

固定任务栏继续由 `QScreen.availableGeometry()` 排除。自动隐藏任务栏不一定持续占用 work area，因此反馈接近底边时使用公开的 `ABM_GETAUTOHIDEBAREX` 获取当前显示器底边 appbar，再读取它的当前矩形：只剩激活细条时使用屏幕底边；任务栏滑入后使用其上沿，并继续保留 12 DIP 内容间距。

该查询只在反馈可见且接近底边时执行，不注册 appbar、不修改任务栏或注册表。若 Windows API 失败则回退 Qt work area。鼠标位置跟随以活动期 8ms timer 运行，绘制动画仍保持 16ms；反馈结束后两者均停止各自不再需要的工作。

## 验收

- 默认 32px cursor 的输出与现有版本一致。
- 48/64/96/128px cursor 分别落入预期档位，内容最大不超过 1.50；大于 32 DIP 时反馈锚点移到鼠标右下边缘外。
- 文本框、圆点、图片和多图堆叠保持相对位置。
- 100/125/150/200% DPI 与双屏不同缩放下不重复放大。
- 靠近屏幕四边时可见反馈内容不超出 available geometry；底边允许透明画布尾部越界以消除提前停住。
- 底边停靠后可见内容保持 12 DIP 间距并继续横向跟随；右边停靠后黄点/黄线在右、内容与渐隐向左，不出现第二条左侧黄线。
- 含图片的反馈在底边停靠时，主图和多图堆叠位于内容框上方；离开底边后恢复内容框下方的常规图片布局。
- 非 Windows 或 Win32 调用失败时无异常并保持原尺寸。
