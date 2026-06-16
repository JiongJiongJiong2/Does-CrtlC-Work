"""
剪贴板监听器 - 监听 Ctrl+C / Ctrl+V，并支持文本与图片复制负载
修复：keyboard 库在后台线程回调，需通过 Qt Signal 桥接到主线程
增强：多次采样检测 + 同内容复制成功 + 多图支持
v2: 异步图片提取 + 修复同内容缓存问题 + 修复多图提取被跳过
"""

from PySide6.QtCore import QObject, Signal, QTimer, QThread
from PySide6.QtGui import QGuiApplication, QImage
import os
import re
import base64
from urllib.parse import unquote
from urllib.request import urlopen, Request
import keyboard
import pyperclip

from config import MAX_TEXT_LENGTH, CLIPBOARD_CHECK, IMAGE_STACK


class _ImageExtractWorker(QThread):
    """后台线程：异步提取剪贴板中的图片，避免主线程卡顿"""
    images_ready = Signal(list)  # list[QImage]

    def __init__(self, parent=None):
        super().__init__(parent)

    def set_mime_data_snapshot(self, text, has_image, has_urls,
                                has_html, html_content, urls_list,
                                image_data_ref=None):
        self._text = text
        self._has_image = has_image
        self._has_urls = has_urls
        self._has_html = has_html
        self._html_content = html_content
        self._urls_list = urls_list
        self._image_data_ref = image_data_ref

    def run(self):
        images = []
        max_display = IMAGE_STACK.get('max_display', 3)

        # 1) 直接位图（主线程已提取的 QImage）
        if self._has_image and self._image_data_ref is not None:
            qimg = self._image_data_ref
            if isinstance(qimg, QImage) and not qimg.isNull():
                images.append(self._safe_copy_image(qimg))

        # 2) URL 列表 - Bug 4 修复：不再受 not images 限制
        if self._has_urls and len(images) < max_display:
            remaining = max_display - len(images)
            for url_str in self._urls_list[:remaining]:
                img = self._try_load_image_from_path(url_str)
                if img is not None:
                    images.append(img)

        # 3) HTML 内容 - Bug 4 修复：不再受 not images 限制
        if self._has_html and len(images) < max_display:
            img, _ = self._try_extract_image_from_html(self._html_content)
            if img is not None:
                images.append(img)

        # 4) 纯文本路径 / data URI / http URL
        if not images and self._text:
            maybe_path = self._normalize_possible_path_text(self._text)
            if maybe_path:
                img = self._try_load_image_from_path(maybe_path)
                if img is not None:
                    images.append(img)
            else:
                img, _ = self._try_extract_image_from_text(self._text)
                if img is not None:
                    images.append(img)

        self.images_ready.emit(images)

    def _safe_copy_image(self, qimg):
        max_dim = 512
        w, h = qimg.width(), qimg.height()
        if w > max_dim or h > max_dim:
            qimg = qimg.scaled(max_dim, max_dim,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.FastTransformation)
        return qimg.copy()

    def _try_load_image_from_path(self, path):
        try:
            img = QImage(path)
            if not img.isNull():
                return self._safe_copy_image(img)
        except Exception:
            pass
        return None

    def _normalize_possible_path_text(self, text):
        raw = text.strip().strip('"').strip("'")
        if not raw:
            return ""
        if raw.startswith("file:///"):
            raw = unquote(raw[8:])
            raw = raw.replace("/", os.sep)
        if os.path.exists(raw) and self._is_image_file(raw):
            return raw
        return ""

    def _is_image_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        return ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff", ".ico"}

    def _try_extract_image_from_html(self, html):
        if not html:
            return None, ""
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
        if not m:
            return None, ""
        src = m.group(1).strip()
        return self._load_image_from_src(src)

    def _try_extract_image_from_text(self, text):
        if not text:
            return None, ""
        src = text.strip()
        if src.startswith("data:image/") or src.startswith("http://") or src.startswith("https://"):
            return self._load_image_from_src(src)
        return None, ""

    def _load_image_from_src(self, src):
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

    def _load_image_from_data_uri(self, src):
        try:
            if ";base64," not in src:
                return None
            b64 = src.split(";base64,", 1)[1]
            data = base64.b64decode(b64, validate=False)
            img = QImage()
            if img.loadFromData(data):
                return self._safe_copy_image(img)
        except Exception:
            pass
        return None

    def _load_image_from_http(self, url):
        try:
            req = Request(url, headers={"User-Agent": "DoseCtrlC/1.0"})
            with urlopen(req, timeout=0.8) as resp:
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "image" not in ctype:
                    return None
                max_bytes = 2 * 1024 * 1024
                data = resp.read(max_bytes + 1)
                if len(data) > max_bytes:
                    return None
                img = QImage()
                if img.loadFromData(data):
                    return self._safe_copy_image(img)
        except Exception:
            pass
        return None


class ClipboardMonitor(QObject):
    """剪贴板监听器 - 监听全局 Ctrl+C 操作"""

    # 公开信号
    copy_success = Signal(str)
    copy_rich = Signal(str, object, int)
    copy_failed = Signal()
    paste_detected = Signal()
    images_updated = Signal(object, int)  # 异步图片补发

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

        self._image_worker = None
        self._pending_text = ""

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
            if self._image_worker and self._image_worker.isRunning():
                self._image_worker.quit()
                self._image_worker.wait()

    def _on_ctrl_c_detected(self):
        self._ctrl_c_triggered.emit()

    def _on_ctrl_v_detected(self):
        self._ctrl_v_triggered.emit()

    def _handle_ctrl_c_on_main_thread(self):
        self._check_attempt = 0
        self._check_copy_result()

    def _handle_ctrl_v_on_main_thread(self):
        self.paste_detected.emit()

    def _check_copy_result(self):
        """检查复制结果（多次采样策略 + 异步图片提取）
        Bug 2 修复：same_content 时用当前 text 而非缓存
        Bug 3 修复：图片提取移到 Worker 线程，主线程快速响应
        """
        try:
            clipboard = QGuiApplication.clipboard()
            mime_data = clipboard.mimeData()
            if not mime_data:
                self._retry_sample()
                return

            # 主线程快速提取文本
            text = ""
            if mime_data.hasText():
                text = (mime_data.text() or "").replace('\r', '')

            # 快速获取指纹
            current_fp = self._get_clipboard_fingerprint()
            has_text = bool(text)
            has_image = mime_data.hasImage()
            has_urls = mime_data.hasUrls()
            has_html = mime_data.hasHtml()

            if has_text or has_image or has_urls or has_html:
                is_new_content = current_fp != self._last_clipboard_fingerprint

                if is_new_content:
                    # 新内容：立即发出信号
                    self._last_clipboard_fingerprint = current_fp
                    self._last_clipboard_text = text or ""

                    display_text = self._truncate_text(text) if has_text else ""
                    # Bug 2 修复：预估 image_count 让 UI 预留图片区域
                    estimated_image_count = 0
                    if has_image:
                        estimated_image_count = 1
                    if has_urls:
                        # 估算 URL 中的图片数量
                        for u in mime_data.urls():
                            local_path = u.toLocalFile()
                            if local_path and self._is_image_file(local_path):
                                estimated_image_count += 1
                    if not display_text and (has_image or has_urls or estimated_image_count > 0):
                        display_text = "Copied Image" if estimated_image_count <= 1 else f"Copied {estimated_image_count} Images"

                    # 发出信号（带预估 image_count）
                    self.copy_success.emit(display_text)
                    self.copy_rich.emit(display_text, [], estimated_image_count)

                    # 准备异步图片提取
                    self._start_image_extraction(mime_data, text, has_image,
                                                  has_urls, has_html)
                    return
                else:
                    # 内容未变：same_content 模式下跳过，继续采样等待新内容
                    # 不发出信号，让采样继续
                    pass

            self._retry_sample()

        except Exception:
            self._retry_sample()

    def _retry_sample(self):
        """继续采样或判定失败"""
        self._check_attempt += 1
        delays = CLIPBOARD_CHECK.get('retry_delays', [40, 120, 260])
        if self._check_attempt < len(delays):
            self._retry_timer.start(delays[self._check_attempt])
        else:
            self.copy_failed.emit()

    def _start_image_extraction(self, mime_data, text, has_image, has_urls, has_html):
        """启动异步图片提取 Worker"""
        # 清理上一个 worker
        if self._image_worker and self._image_worker.isRunning():
            self._image_worker.quit()
            self._image_worker.wait(500)

        self._pending_text = text

        # 主线程快速获取位图引用和 URL 列表
        image_data_ref = None
        if has_image:
            qimg = QGuiApplication.clipboard().image()
            if isinstance(qimg, QImage) and not qimg.isNull():
                image_data_ref = qimg

        urls_list = []
        if has_urls:
            for u in mime_data.urls():
                local_path = u.toLocalFile()
                if local_path and self._is_image_file(local_path):
                    urls_list.append(local_path)

        html_content = ""
        if has_html:
            html_content = mime_data.html() or ""

        worker = _ImageExtractWorker(self)
        worker.set_mime_data_snapshot(
            text=text,
            has_image=has_image,
            has_urls=bool(urls_list),
            has_html=has_html,
            html_content=html_content,
            urls_list=urls_list,
            image_data_ref=image_data_ref
        )
        worker.images_ready.connect(self._on_images_ready)
        self._image_worker = worker
        worker.start()

    def _on_images_ready(self, images):
        """Worker 完成图片提取后的回调"""
        if images:
            image_count = len(images)
            self.images_updated.emit(images, image_count)

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

    def _is_image_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        return ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff", ".ico"}

    def _truncate_text(self, text):
        clean_text = text.replace('\n', ' ').replace('\r', ' ')
        if len(clean_text) > MAX_TEXT_LENGTH:
            return clean_text[:MAX_TEXT_LENGTH] + '...'
        return clean_text

    def get_clipboard_text(self):
        try:
            return pyperclip.paste() or ""
        except Exception:
            return ""
