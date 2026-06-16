"""
剪贴板监听器 - 监听 Ctrl+C / Ctrl+V，并支持文本与图片复制负载
v3: 混合架构 — Worker 提取 raw bytes，主线程构造 QImage
"""

from PySide6.QtCore import QObject, Signal, QTimer, QThread
from PySide6.QtGui import QGuiApplication, QImage
import os, re, base64
from urllib.request import urlopen, Request
import keyboard, pyperclip
from config import MAX_TEXT_LENGTH, CLIPBOARD_CHECK, IMAGE_STACK


class _ImageDataWorker(QThread):
    """后台线程：只做网络下载和纯数据提取，不操作 QImage"""
    raw_images_ready = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._http_urls = []
        self._data_uris = []
        self._file_paths = []

    def set_tasks(self, http_urls, data_uris, file_paths):
        self._http_urls = http_urls
        self._data_uris = data_uris
        self._file_paths = file_paths

    def run(self):
        raw_list = []
        mx = IMAGE_STACK.get('max_display', 3)
        for p in self._file_paths[:mx]:
            d = self._read_file(p)
            if d: raw_list.append(d)
        for u in self._data_uris[:mx - len(raw_list)]:
            d = self._decode_data_uri(u)
            if d: raw_list.append(d)
        for u in self._http_urls[:mx - len(raw_list)]:
            d = self._download(u)
            if d: raw_list.append(d)
        self.raw_images_ready.emit(raw_list)

    def _read_file(self, path):
        try:
            if not os.path.exists(path): return None
            with open(path, 'rb') as f: return f.read()
        except: return None

    def _decode_data_uri(self, uri):
        try:
            if ";base64," not in uri: return None
            return base64.b64decode(uri.split(";base64,", 1)[1], validate=False)
        except: return None

    def _download(self, url):
        try:
            req = Request(url, headers={"User-Agent": "DoseCtrlC/1.0"})
            with urlopen(req, timeout=0.8) as resp:
                ct = (resp.headers.get("Content-Type") or "").lower()
                if "image" not in ct: return None
                data = resp.read(2*1024*1024+1)
                return data if len(data) <= 2*1024*1024 else None
        except: return None


class ClipboardMonitor(QObject):
    copy_success = Signal(str)
    copy_rich = Signal(str, object, int)
    copy_failed = Signal()
    paste_detected = Signal()
    images_updated = Signal(object, int)
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
        self._ctrl_c_triggered.connect(self._handle_ctrl_c)
        self._ctrl_v_triggered.connect(self._handle_ctrl_v)
        self._image_worker = None
        self._worker_already_have = 0

    def start_monitoring(self):
        if not self._is_monitoring:
            self._is_monitoring = True
            try: self._last_clipboard_text = pyperclip.paste() or ""
            except: self._last_clipboard_text = ""
            self._last_clipboard_fingerprint = self._get_fp()
            keyboard.add_hotkey('ctrl+c', lambda: self._ctrl_c_triggered.emit(), suppress=False)
            keyboard.add_hotkey('ctrl+v', lambda: self._ctrl_v_triggered.emit(), suppress=False)

    def stop_monitoring(self):
        if self._is_monitoring:
            self._is_monitoring = False
            keyboard.unhook_all_hotkeys()
            if self._image_worker and self._image_worker.isRunning():
                self._image_worker.quit()
                self._image_worker.wait(1000)

    def _handle_ctrl_c(self):
        self._check_attempt = 0
        self._check_copy_result()

    def _handle_ctrl_v(self):
        self.paste_detected.emit()

    def _check_copy_result(self):
        try:
            cb = QGuiApplication.clipboard()
            md = cb.mimeData()
            if not md:
                self._retry_sample(); return

            text = (md.text() or "").replace('\r', '') if md.hasText() else ""
            fp = self._get_fp()
            has_text = bool(text)
            has_image = md.hasImage()
            has_urls = md.hasUrls()
            has_html = md.hasHtml()

            if has_text or has_image or has_urls or has_html:
                if fp != self._last_clipboard_fingerprint:
                    self._last_clipboard_fingerprint = fp
                    self._last_clipboard_text = text or ""

                    images, http_urls, data_uris, file_paths = [], [], [], []

                    # 1) 直接位图（主线程安全）
                    if has_image:
                        qimg = cb.image()
                        if isinstance(qimg, QImage) and not qimg.isNull():
                            images.append(self._safe_copy(qimg))

                    # 2) URL 列表中的本地文件
                    if has_urls:
                        for u in md.urls():
                            lp = u.toLocalFile()
                            if lp and self._is_img_file(lp):
                                file_paths.append(lp)

                    # 3) HTML 中的图片 src
                    if has_html:
                        src = self._extract_src(md.html() or "")
                        if src:
                            if src.startswith("data:image/"): data_uris.append(src)
                            elif src.startswith(("http://","https://")): http_urls.append(src)

                    # 4) 纯文本中的图片路径/URL
                    if not images and not file_paths and not data_uris and not http_urls and text:
                        mp = self._norm_path(text)
                        if mp: file_paths.append(mp)
                        else:
                            s = text.strip()
                            if s.startswith("data:image/"): data_uris.append(s)
                            elif s.startswith(("http://","https://")): http_urls.append(s)

                    est = len(images) + len(file_paths) + len(data_uris) + len(http_urls)
                    dt = self._trunc(text) if has_text else ""
                    if not dt and est > 0:
                        dt = "Copied Image" if est <= 1 else f"Copied {est} Images"

                    self.copy_success.emit(dt)
                    self.copy_rich.emit(dt, images, est)

                    if file_paths or data_uris or http_urls:
                        self._start_worker(http_urls, data_uris, file_paths, images)
                    return

            self._retry_sample()
        except:
            self._retry_sample()

    def _start_worker(self, http_urls, data_uris, file_paths, existing_images):
        if self._image_worker and self._image_worker.isRunning():
            self._image_worker.quit()
            self._image_worker.wait(500)
        self._image_worker = _ImageDataWorker(self)
        self._image_worker.set_tasks(http_urls, data_uris, file_paths)
        self._worker_existing_images = existing_images  # 保存快速路径已有的图片
        self._image_worker.raw_images_ready.connect(self._on_raw_ready)
        self._image_worker.start()

    def _on_raw_ready(self, raw_list):
        """主线程回调：bytes → QImage，合并快速路径图片"""
        new_images = []
        for data in raw_list:
            img = QImage()
            if img.loadFromData(data):
                new_images.append(self._safe_copy(img))
        # 合并：快速路径图片 + Worker 新提取的图片
        all_images = self._worker_existing_images + new_images
        if all_images:
            self.images_updated.emit(all_images, len(all_images))

    def _retry_sample(self):
        delays = CLIPBOARD_CHECK.get('retry_delays', [40, 120, 260])
        if self._check_attempt < len(delays):
            self._retry_timer.start(delays[self._check_attempt])
            self._check_attempt += 1
        else:
            self.copy_failed.emit()

    def _get_fp(self):
        try:
            cb = QGuiApplication.clipboard()
            md = cb.mimeData()
            if not md: return ("", 0, "", "")
            fmts = tuple(sorted(md.formats())) if md.formats() else ()
            txt = (md.text() or "")[:200] if md.hasText() else ""
            has_img = md.hasImage()
            urls = ""
            if md.hasUrls():
                urls = "|".join(u.toString() for u in md.urls()[:5])
            return (txt, int(has_img), urls, fmts)
        except:
            return ("", 0, "", "")

    def _safe_copy(self, qimg):
        try:
            return qimg.copy() if not qimg.isNull() else None
        except:
            return None

    def _trunc(self, text):
        if not text:
            return ""
        if len(text) <= MAX_TEXT_LENGTH:
            return text
        return text[:MAX_TEXT_LENGTH - 1] + "…"

    def _is_img_file(self, path):
        exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg', '.ico', '.tiff', '.tif'}
        _, ext = os.path.splitext(path.lower())
        return ext in exts

    def _extract_src(self, html):
        if not html:
            return None
        m = re.search(r'<img[^>]+src\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
        return m.group(1) if m else None

    def _norm_path(self, text):
        s = text.strip().strip('"').strip("'")
        if not s:
            return None
        # Windows 路径
        if re.match(r'^[A-Za-z]:[/\\]', s) and self._is_img_file(s):
            return s.replace('/', os.sep)
        # UNC 路径
        if s.startswith('\\\\') and self._is_img_file(s):
            return s
        # Unix 路径
        if s.startswith('/') and self._is_img_file(s):
            return s
        # file:// URI
        if s.startswith('file://'):
            from urllib.parse import unquote as _uq
            p = _uq(s[7:])
            if self._is_img_file(p):
                return p
        return None
