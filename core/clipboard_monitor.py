"""
剪贴板监听器 - 监听 Ctrl+C / Ctrl+V，并支持文本与图片复制负载
修复：keyboard 库在后台线程回调，需通过 Qt Signal 桥接到主线程
"""

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QGuiApplication, QImage
import os
import re
import base64
from urllib.parse import unquote
from urllib.request import urlopen, Request
import keyboard
import pyperclip

from config import MAX_TEXT_LENGTH


class ClipboardMonitor(QObject):
    """剪贴板监听器 - 监听全局 Ctrl+C 操作"""

    # 公开信号
    copy_success = Signal(str)           # 兼容旧逻辑：复制成功，携带展示文本
    copy_rich = Signal(str, object)      # 新逻辑：复制成功，携带文本 + 图片(QImage|None)
    copy_failed = Signal()               # 复制失败（无选中内容）
    paste_detected = Signal()            # 检测到粘贴

    # 内部信号 - 用于从 keyboard 后台线程安全地通知 Qt 主线程
    _ctrl_c_triggered = Signal()
    _ctrl_v_triggered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_clipboard_text = ""
        self._last_clipboard_fingerprint = ("", 0)
        self._is_monitoring = False

        # 延迟检查定时器（在主线程中创建和使用）
        self._check_timer = QTimer(self)
        self._check_timer.setSingleShot(True)
        self._check_timer.timeout.connect(self._check_copy_result)

        # 连接内部信号到主线程处理槽
        self._ctrl_c_triggered.connect(self._handle_ctrl_c_on_main_thread)
        self._ctrl_v_triggered.connect(self._handle_ctrl_v_on_main_thread)

    def start_monitoring(self):
        """开始监听剪贴板"""
        if not self._is_monitoring:
            self._is_monitoring = True

            # 保存当前剪贴板内容
            try:
                self._last_clipboard_text = pyperclip.paste() or ""
            except Exception:
                self._last_clipboard_text = ""

            self._last_clipboard_fingerprint = self._get_clipboard_fingerprint()

            # 使用 add_hotkey 注册快捷键
            # 回调会在 keyboard 的后台线程中执行，只发 Signal 不操作 QTimer
            keyboard.add_hotkey('ctrl+c', self._on_ctrl_c_detected, suppress=False)
            keyboard.add_hotkey('ctrl+v', self._on_ctrl_v_detected, suppress=False)

    def stop_monitoring(self):
        """停止监听"""
        if self._is_monitoring:
            self._is_monitoring = False
            keyboard.unhook_all_hotkeys()

    # ---- keyboard 后台线程回调（仅发 Signal，不操作任何 QTimer/QObject）----

    def _on_ctrl_c_detected(self):
        """Ctrl+C 被按下 - 在 keyboard 后台线程中调用"""
        self._ctrl_c_triggered.emit()

    def _on_ctrl_v_detected(self):
        """Ctrl+V 被按下 - 在 keyboard 后台线程中调用"""
        self._ctrl_v_triggered.emit()

    # ---- Qt 主线程处理（安全操作 QTimer 和其他 QObject）----

    def _handle_ctrl_c_on_main_thread(self):
        """在 Qt 主线程中处理 Ctrl+C"""
        # 延迟检查复制结果（等待系统完成复制操作）
        self._check_timer.start(50)

    def _handle_ctrl_v_on_main_thread(self):
        """在 Qt 主线程中处理 Ctrl+V"""
        self.paste_detected.emit()

    def _check_copy_result(self):
        """检查复制结果（文本/图片）"""
        try:
            text, image = self._extract_clipboard_payload()
            has_text = bool(text)
            has_image = image is not None

            current_fp = self._get_clipboard_fingerprint()

            # 必须有内容且与上次不同，才判定复制成功
            if (has_text or has_image) and current_fp != self._last_clipboard_fingerprint:
                self._last_clipboard_fingerprint = current_fp
                self._last_clipboard_text = text or ""

                display_text = self._truncate_text(text) if has_text else ""
                if not display_text and has_image:
                    display_text = "Copied Image"

                self.copy_success.emit(display_text)
                self.copy_rich.emit(display_text, image)
            else:
                self.copy_failed.emit()

        except Exception:
            self.copy_failed.emit()

    def _extract_clipboard_payload(self):
        """提取剪贴板负载（text + image）"""
        clipboard = QGuiApplication.clipboard()
        mime_data = clipboard.mimeData()

        text = ""
        image = None

        if mime_data and mime_data.hasText():
            text = (mime_data.text() or "").replace('\r', '')

        # 1) 直接位图（最优先）
        if mime_data and mime_data.hasImage():
            qimg = clipboard.image()
            if isinstance(qimg, QImage) and not qimg.isNull():
                image = qimg.copy()

        # 2) URL 列表（资源管理器常见：text/uri-list）
        if image is None and mime_data and mime_data.hasUrls():
            image_path = self._extract_first_image_from_urls(mime_data.urls())
            if image_path:
                image = self._try_load_image_from_path(image_path)
                if image is not None and not text:
                    text = f"Copied {os.path.basename(image_path)}"

        # 3) HTML 内容（网页复制常见：<img src=...>）
        if image is None and mime_data and mime_data.hasHtml():
            image, html_label = self._try_extract_image_from_html(mime_data.html())
            if image is not None and not text:
                text = html_label or "Copied Web Image"

        # 4) 纯文本路径 / file:/// 路径（某些软件会这样复制）
        if image is None and text:
            maybe_path = self._normalize_possible_path_text(text)
            if maybe_path:
                image = self._try_load_image_from_path(maybe_path)
                if image is not None:
                    text = f"Copied {os.path.basename(maybe_path)}"
            else:
                # 纯文本里也可能是 http(s) 图片地址或 data URI
                image, txt_label = self._try_extract_image_from_text(text)
                if image is not None:
                    text = txt_label or "Copied Web Image"

        return text, image

    def _get_clipboard_fingerprint(self):
        """获取剪贴板内容指纹，用于判断是否变化"""
        clipboard = QGuiApplication.clipboard()
        mime_data = clipboard.mimeData()

        text = ""
        image_key = 0
        url_signature = ""
        html_signature = ""

        if mime_data and mime_data.hasText():
            text = mime_data.text() or ""

        if mime_data and mime_data.hasImage():
            qimg = clipboard.image()
            if isinstance(qimg, QImage) and not qimg.isNull():
                image_key = int(qimg.cacheKey())

        if mime_data and mime_data.hasUrls():
            url_signature = "|".join([u.toString() for u in mime_data.urls()])

        if mime_data and mime_data.hasHtml():
            html_signature = (mime_data.html() or "")[:1024]

        return text, image_key, url_signature, html_signature

    def _extract_first_image_from_urls(self, urls):
        """从 URL 列表里提取第一个本地图片路径"""
        for url in urls:
            local_path = url.toLocalFile()
            if local_path and self._is_image_file(local_path):
                return local_path
        return ""

    def _normalize_possible_path_text(self, text: str) -> str:
        """把文本中的 file URI / 路径转换为本地路径"""
        raw = text.strip().strip('"').strip("'")
        if not raw:
            return ""

        if raw.startswith("file:///"):
            # file:///C:/xx/yy.png -> C:/xx/yy.png
            raw = unquote(raw[8:])
            raw = raw.replace("/", os.sep)

        if os.path.exists(raw) and self._is_image_file(raw):
            return raw

        return ""

    def _is_image_file(self, path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff", ".ico"}

    def _try_load_image_from_path(self, path: str):
        """从本地路径加载 QImage"""
        try:
            img = QImage(path)
            if not img.isNull():
                return img
        except Exception:
            pass
        return None

    def _try_extract_image_from_html(self, html: str):
        """从 HTML 里提取 img src 并尝试加载"""
        if not html:
            return None, ""

        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
        if not m:
            return None, ""

        src = m.group(1).strip()
        return self._load_image_from_src(src)

    def _try_extract_image_from_text(self, text: str):
        """从纯文本里识别 data URI 或 http(s) 图片地址"""
        if not text:
            return None, ""

        src = text.strip()
        if src.startswith("data:image/") or src.startswith("http://") or src.startswith("https://"):
            return self._load_image_from_src(src)

        return None, ""

    def _load_image_from_src(self, src: str):
        """从 data URI / http(s) URL 加载 QImage"""
        # data:image/...;base64,xxxx
        if src.startswith("data:image/"):
            image = self._load_image_from_data_uri(src)
            if image is not None:
                return image, "Copied Web Image"
            return None, ""

        # 远程图片 URL
        if src.startswith("http://") or src.startswith("https://"):
            image = self._load_image_from_http(src)
            if image is not None:
                label = src.split("/")[-1].split("?")[0].strip() or "Web Image"
                return image, f"Copied {label}"
            return None, ""

        return None, ""

    def _load_image_from_data_uri(self, src: str):
        try:
            if ";base64," not in src:
                return None
            b64 = src.split(";base64,", 1)[1]
            data = base64.b64decode(b64, validate=False)
            img = QImage()
            if img.loadFromData(data):
                return img
        except Exception:
            pass
        return None

    def _load_image_from_http(self, url: str):
        """下载远程图片并转 QImage（带超时和大小限制）"""
        try:
            req = Request(url, headers={"User-Agent": "DoseCtrlC/1.0"})
            with urlopen(req, timeout=1.2) as resp:
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "image" not in ctype:
                    return None

                max_bytes = 3 * 1024 * 1024
                data = resp.read(max_bytes + 1)
                if len(data) > max_bytes:
                    return None

                img = QImage()
                if img.loadFromData(data):
                    return img
        except Exception:
            pass
        return None

    def _truncate_text(self, text: str) -> str:
        """截断文本用于显示"""
        clean_text = text.replace('\n', ' ').replace('\r', ' ')
        if len(clean_text) > MAX_TEXT_LENGTH:
            return clean_text[:MAX_TEXT_LENGTH] + '...'
        return clean_text

    def get_clipboard_text(self) -> str:
        """获取当前剪贴板文本"""
        try:
            return pyperclip.paste() or ""
        except Exception:
            return ""