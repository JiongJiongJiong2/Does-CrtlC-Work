"""
剪贴板监听器 - 监听 Ctrl+C / Ctrl+V，并支持文本与图片复制负载
修复：keyboard 库在后台线程回调，需通过 Qt Signal 桥接到主线程
增强：多次采样检测 + 同内容复制成功 + 多图支持
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

from config import MAX_TEXT_LENGTH, CLIPBOARD_CHECK


class ClipboardMonitor(QObject):
    """剪贴板监听器 - 监听全局 Ctrl+C 操作"""

    # 公开信号
    copy_success = Signal(str)                         # 兼容旧逻辑
    copy_rich = Signal(str, object, int)               # 文本 + 图片列表(list[QImage]) + 图片数量
    copy_failed = Signal()
    paste_detected = Signal()

    # 内部信号
    _ctrl_c_triggered = Signal()
    _ctrl_v_triggered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_clipboard_text = ""
        self._last_clipboard_fingerprint = ("", 0, "", "")
        self._is_monitoring = False
        self._check_attempt = 0

        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._check_copy_result)

        self._ctrl_c_triggered.connect(self._handle_ctrl_c_on_main_thread)
        self._ctrl_v_triggered.connect(self._handle_ctrl_v_on_main_thread)

    def start_monitoring(self):
        if not self._is_monitoring:
            self._is_monitoring = True
            try:
                self._last_clipboard_text = pyperclip.paste() or ""
            except Exception:
                self._last_clipboard_text = ""
            self._last_clipboard_fingerprint = self._get_clipboard_fingerprint()
            keyboard.add_hotkey('ctrl+c', self._on_ctrl_c_detected, suppress=False)
            keyboard.add_hotkey('ctrl+v', self._on_ctrl_v_detected, suppress=False)

    def stop_monitoring(self):
        if self._is_monitoring:
            self._is_monitoring = False
            keyboard.unhook_all_hotkeys()

    def _on_ctrl_c_detected(self):
        self._ctrl_c_triggered.emit()

    def _on_ctrl_v_detected(self):
        self._ctrl_v_triggered.emit()

    def _handle_ctrl_c_on_main_thread(self):
        """启动多次采样检测"""
        self._check_attempt = 0
        self._check_copy_result()

    def _handle_ctrl_v_on_main_thread(self):
        self.paste_detected.emit()

    def _check_copy_result(self):
        """检查复制结果（多次采样策略）"""
        try:
            text, images = self._extract_clipboard_payload()
            has_text = bool(text)
            has_image = bool(images)
            current_fp = self._get_clipboard_fingerprint()

            if has_text or has_image:
                is_new_content = current_fp != self._last_clipboard_fingerprint
                same_ok = CLIPBOARD_CHECK.get('same_content_as_success', True)

                if is_new_content or same_ok:
                    self._last_clipboard_fingerprint = current_fp
                    self._last_clipboard_text = text or ""

                    display_text = self._truncate_text(text) if has_text else ""
                    image_count = len(images)
                    if not display_text and has_image:
                        display_text = f"Copied {image_count} Images" if image_count > 1 else "Copied Image"

                    self.copy_success.emit(display_text)
                    self.copy_rich.emit(display_text, images, image_count)
                    return

            # 继续采样
            self._check_attempt += 1
            delays = CLIPBOARD_CHECK.get('retry_delays', [40, 120, 260])
            if self._check_attempt < len(delays):
                self._retry_timer.start(delays[self._check_attempt])
            else:
                self.copy_failed.emit()

        except Exception:
            self._check_attempt += 1
            delays = CLIPBOARD_CHECK.get('retry_delays', [40, 120, 260])
            if self._check_attempt < len(delays):
                self._retry_timer.start(delays[self._check_attempt])
            else:
                self.copy_failed.emit()

    def _extract_clipboard_payload(self):
        """提取剪贴板负载（text + images 列表）"""
        clipboard = QGuiApplication.clipboard()
        mime_data = clipboard.mimeData()

        text = ""
        images = []

        if mime_data and mime_data.hasText():
            text = (mime_data.text() or "").replace('\r', '')

        # 1) 直接位图
        if mime_data and mime_data.hasImage():
            qimg = clipboard.image()
            if isinstance(qimg, QImage) and not qimg.isNull():
                images.append(qimg.copy())

        # 2) URL 列表（支持多文件图片）
        if mime_data and mime_data.hasUrls():
            image_urls = [u for u in mime_data.urls()
                          if self._is_image_file(u.toLocalFile() or u.toString())]
            if image_urls and not images:
                for url in image_urls:
                    local_path = url.toLocalFile()
                    if local_path:
                        img = self._try_load_image_from_path(local_path)
                        if img is not None:
                            images.append(img)
                if images and not text:
                    names = [os.path.basename(u.toLocalFile()) for u in image_urls if u.toLocalFile()]
                    if len(names) == 1:
                        text = f"Copied {names[0]}"
                    elif len(names) > 1:
                        text = f"Copied {len(names)} files"

        # 3) HTML 内容
        if not images and mime_data and mime_data.hasHtml():
            img, html_label = self._try_extract_image_from_html(mime_data.html())
            if img is not None:
                images.append(img)
                if not text:
                    text = html_label or "Copied Web Image"

        # 4) 纯文本路径 / data URI / http URL
        if not images and text:
            maybe_path = self._normalize_possible_path_text(text)
            if maybe_path:
                img = self._try_load_image_from_path(maybe_path)
                if img is not None:
                    images.append(img)
                    text = f"Copied {os.path.basename(maybe_path)}"
            else:
                img, txt_label = self._try_extract_image_from_text(text)
                if img is not None:
                    images.append(img)
                    text = txt_label or "Copied Web Image"

        return text, images

    def _get_clipboard_fingerprint(self):
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
        for url in urls:
            local_path = url.toLocalFile()
            if local_path and self._is_image_file(local_path):
                return local_path
        return ""

    def _normalize_possible_path_text(self, text: str) -> str:
        raw = text.strip().strip('"').strip("'")
        if not raw:
            return ""
        if raw.startswith("file:///"):
            raw = unquote(raw[8:])
            raw = raw.replace("/", os.sep)
        if os.path.exists(raw) and self._is_image_file(raw):
            return raw
        return ""

    def _is_image_file(self, path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff", ".ico"}

    def _try_load_image_from_path(self, path: str):
        try:
            img = QImage(path)
            if not img.isNull():
                return img
        except Exception:
            pass
        return None

    def _try_extract_image_from_html(self, html: str):
        if not html:
            return None, ""
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
        if not m:
            return None, ""
        src = m.group(1).strip()
        return self._load_image_from_src(src)

    def _try_extract_image_from_text(self, text: str):
        if not text:
            return None, ""
        src = text.strip()
        if src.startswith("data:image/") or src.startswith("http://") or src.startswith("https://"):
            return self._load_image_from_src(src)
        return None, ""

    def _load_image_from_src(self, src: str):
        """从 data URI / http(s) URL 加载 QImage"""
        if src.startswith("data:image/"):
            image = self._load_image_from_data_uri(src)
            if image is not None:
                return image, "Copied Web Image"
            return None, ""
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
