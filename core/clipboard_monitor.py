"""事件驱动的系统剪贴板监听与富媒体提取。"""

import base64
import ctypes
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import keyboard
from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QImage

from config import CLIPBOARD_CHECK, IMAGE_STACK, MAX_TEXT_LENGTH

logger = logging.getLogger(__name__)


class _ImageDataWorker(QThread):
    """只提取 bytes 的可取消 worker，结果保持源任务顺序。"""

    raw_images_ready = Signal(int, list)

    def __init__(self, request_id: int, max_images: int, parent=None):
        super().__init__(parent)
        self._request_id = request_id
        self._max_images = max_images
        self._http_urls = []
        self._data_uris = []
        self._file_paths = []
        self._raw_image_bytes = []
        self._cancelled = Event()

    def set_tasks(self, http_urls, data_uris, file_paths, raw_image_bytes=None):
        self._http_urls = list(http_urls)
        self._data_uris = list(data_uris)
        self._file_paths = list(file_paths)
        self._raw_image_bytes = list(raw_image_bytes or [])

    def cancel(self):
        self._cancelled.set()

    def run(self):
        if self._max_images <= 0:
            return
        logger.info('clipboard image worker started request=%s raw=%s files=%s data_uris=%s http_urls=%s',
                    self._request_id, len(self._raw_image_bytes), len(self._file_paths),
                    len(self._data_uris), len(self._http_urls))
        raw_list = list(self._raw_image_bytes[:self._max_images])
        if self._cancelled.is_set():
            return
        if len(raw_list) >= self._max_images:
            self._emit_if_current(raw_list)
            return
        for path in self._file_paths[:self._max_images]:
            if self._cancelled.is_set():
                return
            data = self._read_file(path)
            if data:
                raw_list.append(data)

        remaining = self._max_images - len(raw_list)
        if remaining <= 0:
            self._emit_if_current(raw_list)
            return

        tasks = [('data', uri) for uri in self._data_uris[:remaining]]
        tasks.extend(('http', url) for url in self._http_urls[:remaining - len(tasks)])
        if not tasks:
            self._emit_if_current(raw_list)
            return

        ordered_results = [None] * len(tasks)
        with ThreadPoolExecutor(max_workers=min(len(tasks), 3)) as pool:
            futures = {
                pool.submit(self._decode_data_uri if kind == 'data' else self._download, value): index
                for index, (kind, value) in enumerate(tasks)
            }
            for future in as_completed(futures):
                if self._cancelled.is_set():
                    return
                try:
                    ordered_results[futures[future]] = future.result()
                except Exception as error:
                    logger.warning('clipboard image worker task failed request=%s error=%s: %s',
                                   self._request_id, type(error).__name__, error)
                    continue

        raw_list.extend(data for data in ordered_results if data)
        self._emit_if_current(raw_list[:self._max_images])

    def _emit_if_current(self, raw_list):
        if not self._cancelled.is_set():
            self.raw_images_ready.emit(self._request_id, raw_list)

    @staticmethod
    def _read_file(path):
        try:
            with open(path, 'rb') as file:
                return file.read()
        except OSError as error:
            logger.warning('clipboard image file read failed name=%s error=%s: %s',
                           os.path.basename(path), type(error).__name__, error)
            return None

    @staticmethod
    def _decode_data_uri(uri):
        try:
            if ';base64,' not in uri:
                return None
            return base64.b64decode(uri.split(';base64,', 1)[1], validate=False)
        except Exception as error:
            logger.warning('clipboard image data URI decode failed error=%s: %s',
                           type(error).__name__, error)
            return None

    @staticmethod
    def _download(url):
        host = urlsplit(url).netloc or '<unknown>'
        timeout = CLIPBOARD_CHECK.get('image_download_timeout', 3.0)
        attempts = max(1, int(CLIPBOARD_CHECK.get('image_download_attempts', 2)))
        retry_delay = max(0.0, CLIPBOARD_CHECK.get('image_download_retry_delay', 0.15))
        max_bytes = CLIPBOARD_CHECK.get('image_download_max_bytes', 2 * 1024 * 1024)
        for attempt in range(1, attempts + 1):
            try:
                logger.info('clipboard image download attempt=%s/%s host=%s timeout=%ss',
                            attempt, attempts, host, timeout)
                request = Request(url, headers={'User-Agent': 'DoseCtrlC/1.0'})
                with urlopen(request, timeout=timeout) as response:
                    content_type = (response.headers.get('Content-Type') or '').lower()
                    if 'image' not in content_type:
                        logger.warning('clipboard image download rejected host=%s content_type=%s',
                                       host, content_type or '<missing>')
                        return None
                    data = response.read(max_bytes + 1)
                    if len(data) > max_bytes:
                        logger.warning('clipboard image download rejected host=%s size=%s reason=too_large',
                                       host, len(data))
                        return None
                    logger.info('clipboard image download succeeded host=%s bytes=%s', host, len(data))
                    return data
            except Exception as error:
                logger.warning('clipboard image download failed attempt=%s/%s host=%s error=%s: %s',
                               attempt, attempts, host, type(error).__name__, error)
                if attempt < attempts and retry_delay:
                    time.sleep(retry_delay)
        return None


class ClipboardMonitor(QObject):
    """以系统剪贴板变更为事实源，Ctrl+C 仅作为确认意图。"""

    copy_success = Signal(str)
    copy_rich = Signal(str, object, int)
    copy_failed = Signal()
    paste_detected = Signal()
    images_updated = Signal(object, int)
    _ctrl_c_triggered = Signal()
    _ctrl_v_triggered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clipboard = None
        self._is_monitoring = False
        self._last_sequence = 0
        self._fallback_sequence = 0
        self._pending_copy_sequence = None
        self._pending_copy_id = 0
        self._event_retry_attempt = 0
        self._pending_event_sequence = 0
        self._image_request_id = 0
        self._image_workers = set()

        self._confirmation_timer = QTimer(self)
        self._confirmation_timer.setSingleShot(True)
        self._confirmation_timer.timeout.connect(self._on_confirmation_timeout)
        self._event_retry_timer = QTimer(self)
        self._event_retry_timer.setSingleShot(True)
        self._event_retry_timer.timeout.connect(self._process_clipboard_event)
        self._ctrl_c_triggered.connect(self._handle_ctrl_c)
        self._ctrl_v_triggered.connect(self._handle_ctrl_v)

    def start_monitoring(self):
        if self._is_monitoring:
            return
        self._clipboard = QGuiApplication.clipboard()
        self._last_sequence = self._get_clipboard_sequence()
        self._clipboard.dataChanged.connect(self._on_clipboard_changed)
        self._is_monitoring = True
        keyboard.add_hotkey('ctrl+c', lambda: self._ctrl_c_triggered.emit(), suppress=False)
        keyboard.add_hotkey('ctrl+v', lambda: self._ctrl_v_triggered.emit(), suppress=False)

    def stop_monitoring(self):
        if not self._is_monitoring:
            return
        self._is_monitoring = False
        keyboard.unhook_all_hotkeys()
        if self._clipboard:
            try:
                self._clipboard.dataChanged.disconnect(self._on_clipboard_changed)
            except (RuntimeError, TypeError):
                pass
        self._clipboard = None
        self._confirmation_timer.stop()
        self._event_retry_timer.stop()
        self._pending_copy_sequence = None
        self._cancel_image_workers()

    def _handle_ctrl_c(self):
        """记录 Ctrl+C 前的序列号；不再主动轮询剪贴板。"""
        if not self._is_monitoring:
            return
        self._pending_copy_id += 1
        self._pending_copy_sequence = self._get_clipboard_sequence() or self._last_sequence
        self._confirmation_timer.start(CLIPBOARD_CHECK.get('confirmation_timeout', 700))

    def _handle_ctrl_v(self):
        self.paste_detected.emit()

    def _on_clipboard_changed(self):
        if not self._is_monitoring:
            return
        sequence = self._get_clipboard_sequence()
        if sequence:
            if sequence == self._last_sequence:
                return
            self._last_sequence = sequence
        else:
            self._fallback_sequence += 1
            sequence = self._fallback_sequence
        self._pending_event_sequence = sequence
        self._event_retry_attempt = 0
        self._process_clipboard_event()

    def _process_clipboard_event(self):
        if not self._is_monitoring:
            return
        snapshot = self._read_clipboard_snapshot()
        if snapshot is None:
            delays = CLIPBOARD_CHECK.get('event_retry_delays', [40, 120])
            if self._event_retry_attempt < len(delays):
                self._event_retry_timer.start(delays[self._event_retry_attempt])
                self._event_retry_attempt += 1
                return
            if self._pending_copy_sequence is not None:
                self._clear_pending_copy()
                self.copy_failed.emit()
            return

        self._clear_pending_copy()
        self._emit_snapshot(snapshot)

    def _on_confirmation_timeout(self):
        if self._pending_copy_sequence is not None:
            self._pending_copy_sequence = None
            self.copy_failed.emit()

    def _clear_pending_copy(self):
        self._pending_copy_sequence = None
        self._confirmation_timer.stop()

    def _read_clipboard_snapshot(self):
        clipboard = self._clipboard or QGuiApplication.clipboard()
        try:
            mime_data = clipboard.mimeData()
            if not mime_data:
                return None
            text = (mime_data.text() or '').replace('\r\n', '\n').replace('\r', '\n') if mime_data.hasText() else ''
            has_image = mime_data.hasImage()
            has_urls = mime_data.hasUrls()
            has_html = mime_data.hasHtml()
            has_raw_image_mime = self._has_raw_image_mime(mime_data)
            logger.info('clipboard snapshot formats=%s image=%s urls=%s html=%s raw_image_mime=%s',
                        ','.join(str(value) for value in mime_data.formats()), has_image,
                        has_urls, has_html, has_raw_image_mime)
            if not (text or has_image or has_urls or has_html or has_raw_image_mime):
                return None

            images, raw_image_bytes = [], []
            http_urls, data_uris, file_paths = [], [], []
            if has_image:
                image = clipboard.image()
                if isinstance(image, QImage) and not image.isNull():
                    images.append(self._safe_copy(image))
                else:
                    image = mime_data.imageData()
                    if isinstance(image, QImage) and not image.isNull():
                        images.append(self._safe_copy(image))
            if not images:
                raw_image_bytes = self._read_raw_image_mime(mime_data)
            if has_urls:
                for url in mime_data.urls():
                    local_path = url.toLocalFile()
                    if local_path and self._is_img_file(local_path):
                        file_paths.append(local_path)
            if has_html:
                for source in self._extract_all_srcs(mime_data.html() or ''):
                    if source.startswith('data:image/'):
                        data_uris.append(source)
                    elif source.startswith(('http://', 'https://')):
                        http_urls.append(source)
            if not images and not file_paths and not data_uris and not http_urls and text:
                path = self._norm_path(text)
                if path:
                    file_paths.append(path)
                elif text.strip().startswith('data:image/'):
                    data_uris.append(text.strip())
                elif text.strip().startswith(('http://', 'https://')):
                    http_urls.append(text.strip())

            # Browser clipboard formats often contain both a local image
            # representation and a remote HTML URL. Prefer the local snapshot:
            # the URL may require cookies/referer or expire before downloading.
            if images or raw_image_bytes or file_paths or data_uris:
                http_urls = []
            image_count = (len(images) + len(raw_image_bytes) + len(file_paths) +
                           len(data_uris) + len(http_urls))
            logger.info('clipboard image sources qimage=%s raw=%s files=%s data_uris=%s http_urls=%s',
                        len(images), len(raw_image_bytes), len(file_paths), len(data_uris), len(http_urls))
            display_text = self._trunc(text) if text else ''
            if not display_text and image_count:
                display_text = 'Copied Image' if image_count == 1 else f'Copied {image_count} Images'
            return (display_text, images, image_count, http_urls, data_uris,
                    file_paths, raw_image_bytes)
        except Exception as error:
            logger.exception('clipboard snapshot failed error=%s: %s', type(error).__name__, error)
            return None

    def _emit_snapshot(self, snapshot):
        (display_text, images, image_count, http_urls, data_uris, file_paths,
         raw_image_bytes) = snapshot
        self.copy_success.emit(display_text)
        self.copy_rich.emit(display_text, images, image_count)
        self._image_request_id += 1
        request_id = self._image_request_id
        self._cancel_image_workers()
        if not (raw_image_bytes or file_paths or data_uris or http_urls):
            return
        remaining = max(0, IMAGE_STACK.get('max_preload', 4) - len(images))
        if remaining:
            self._start_worker(request_id, http_urls, data_uris, file_paths,
                               raw_image_bytes, remaining, image_count)

    def _start_worker(self, request_id, http_urls, data_uris, file_paths,
                      raw_image_bytes, max_images, image_count):
        worker = _ImageDataWorker(request_id, max_images, self)
        worker.set_tasks(http_urls, data_uris, file_paths, raw_image_bytes)
        self._image_workers.add(worker)
        worker.raw_images_ready.connect(
            lambda worker_id, raw_list, total=image_count: self._on_raw_ready(worker_id, raw_list, total))
        worker.finished.connect(lambda current=worker: self._on_worker_finished(current))
        worker.start()

    def _on_raw_ready(self, request_id, raw_list, image_count):
        if request_id != self._image_request_id:
            return
        images = []
        for data in raw_list:
            image = QImage()
            if image.loadFromData(data):
                images.append(self._safe_copy(image))
            else:
                logger.warning('clipboard image decode failed request=%s bytes=%s', request_id, len(data))
        if images:
            logger.info('clipboard image decode succeeded request=%s images=%s expected=%s',
                        request_id, len(images), image_count)
            self.images_updated.emit(images, image_count)
        elif raw_list:
            logger.warning('clipboard image decode produced no usable images request=%s', request_id)

    def _on_worker_finished(self, worker):
        self._image_workers.discard(worker)
        worker.deleteLater()

    def _cancel_image_workers(self):
        for worker in tuple(self._image_workers):
            worker.cancel()

    @staticmethod
    def _has_raw_image_mime(mime_data):
        preferred_formats = {
            'image/png', 'image/jpeg', 'image/jpg', 'image/webp',
            'image/gif', 'image/bmp', 'image/tiff',
        }
        try:
            return bool({str(value).lower() for value in mime_data.formats()} & preferred_formats)
        except (RuntimeError, TypeError, ValueError):
            return False

    @staticmethod
    def _read_raw_image_mime(mime_data):
        """Copy browser-provided image bytes while the clipboard owns them."""
        max_size = CLIPBOARD_CHECK.get('raw_image_max_bytes', 16 * 1024 * 1024)
        preferred_formats = (
            'image/png', 'image/jpeg', 'image/jpg', 'image/webp',
            'image/gif', 'image/bmp', 'image/tiff',
        )
        try:
            formats = {str(value).lower() for value in mime_data.formats()}
            for mime_type in preferred_formats:
                if mime_type not in formats:
                    continue
                raw = bytes(mime_data.data(mime_type))
                if 0 < len(raw) <= max_size:
                    logger.info('clipboard raw image MIME selected type=%s bytes=%s', mime_type, len(raw))
                    return [raw]
                logger.warning('clipboard raw image MIME rejected type=%s bytes=%s limit=%s',
                               mime_type, len(raw), max_size)
        except (RuntimeError, TypeError, ValueError) as error:
            logger.warning('clipboard raw image MIME read failed error=%s: %s',
                           type(error).__name__, error)
        return []

    @staticmethod
    def _get_clipboard_sequence():
        if not sys.platform.startswith('win'):
            return 0
        try:
            return int(ctypes.windll.user32.GetClipboardSequenceNumber())
        except (AttributeError, OSError):
            return 0

    @staticmethod
    def _safe_copy(image):
        try:
            return image.copy() if not image.isNull() else None
        except RuntimeError:
            return None

    @staticmethod
    def _trunc(text):
        # This is a UI preview cap, not a mutation of the real clipboard.
        return text if len(text) <= MAX_TEXT_LENGTH else text[:MAX_TEXT_LENGTH - 1] + '…'

    @staticmethod
    def _is_img_file(path):
        _, extension = os.path.splitext(path.lower())
        return extension in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg',
                             '.ico', '.tiff', '.tif'}

    @staticmethod
    def _extract_all_srcs(html):
        return re.findall(r'<img[^>]+src\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE) if html else []

    def _norm_path(self, text):
        value = text.strip().strip('"').strip("'")
        if re.match(r'^[A-Za-z]:[/\\]', value) and self._is_img_file(value):
            return value.replace('/', os.sep)
        if value.startswith('\\\\') and self._is_img_file(value):
            return value
        if value.startswith('/') and self._is_img_file(value):
            return value
        if value.startswith('file://'):
            from urllib.parse import unquote
            path = unquote(value[7:])
            if self._is_img_file(path):
                return path
        return None
