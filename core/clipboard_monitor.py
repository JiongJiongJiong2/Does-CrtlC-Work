"""事件驱动的系统剪贴板监听与富媒体提取。"""

import ctypes
import logging
import os
import re
import sys
import time

import keyboard
from PySide6.QtCore import QObject, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication, QImage

from config import CLIPBOARD_CHECK, IMAGE_STACK, MAX_TEXT_LENGTH, PREVIEW_LIMITS
from core.image_preview import PreviewService, _ImageDataWorker

logger = logging.getLogger(__name__)


class ClipboardMonitor(QObject):
    """以系统剪贴板变更为事实源，Ctrl+C 仅作为确认意图。"""

    copy_success = Signal(str)
    copy_rich = Signal(str, object, int)
    copy_session = Signal(int, str, object, int)
    copy_failed = Signal()
    paste_detected = Signal()
    images_updated = Signal(object, int)
    images_for_session = Signal(int, object, int)
    _ctrl_c_triggered = Signal(float, object, int)
    _ctrl_v_triggered = Signal(int, float)

    def __init__(self, parent=None, remote_previews=False):
        super().__init__(parent)
        self._clipboard = None
        self._is_monitoring = False
        self._last_sequence = 0
        self._fallback_sequence = 0
        self._pending_copy_sequence = None
        self._event_retry_attempt = 0
        self._pending_event_session = None
        self._image_request_id = 0
        self._last_copy_event = None
        self._last_matched_event_id = 0
        self._last_paste_at = float('-inf')
        self._hotkey_handles = []
        self._lifecycle_generation = 0
        self._preview_service = None
        self._remote_previews = bool(remote_previews)

        self._confirmation_timer = QTimer(self)
        self._confirmation_timer.setSingleShot(True)
        self._confirmation_timer.timeout.connect(self._on_confirmation_timeout)
        self._event_retry_timer = QTimer(self)
        self._event_retry_timer.setSingleShot(True)
        self._event_retry_timer.timeout.connect(self._process_clipboard_event)
        self._ctrl_c_triggered.connect(self._handle_ctrl_c, Qt.QueuedConnection)
        self._ctrl_v_triggered.connect(self._handle_ctrl_v, Qt.QueuedConnection)

    def start_monitoring(self):
        if self._is_monitoring:
            return
        self._clipboard = QGuiApplication.clipboard()
        self._last_sequence = self._get_clipboard_sequence()
        self._clipboard.dataChanged.connect(self._on_clipboard_changed)
        self._lifecycle_generation += 1
        self._is_monitoring = True
        generation = self._lifecycle_generation
        for shortcut, callback in (
                ('ctrl+c', lambda: self._capture_copy_intent(generation)),
                ('ctrl+v', lambda: self._capture_paste_intent(generation))):
            try:
                self._hotkey_handles.append(
                    keyboard.add_hotkey(shortcut, callback, suppress=False))
            except Exception as error:
                logger.warning('global shortcut unavailable shortcut=%s error=%s; '
                               'clipboard monitoring remains active', shortcut,
                               type(error).__name__)

    def _capture_copy_intent(self, generation=None):
        # The keyboard library invokes callbacks off the GUI thread. Capture
        # evidence here, before Qt delivery can be reordered with dataChanged.
        self._ctrl_c_triggered.emit(time.monotonic(), self._get_clipboard_sequence(),
                                    self._lifecycle_generation if generation is None else generation)

    def _capture_paste_intent(self, generation=None):
        self._ctrl_v_triggered.emit(
            self._lifecycle_generation if generation is None else generation, time.monotonic())

    def stop_monitoring(self):
        self._is_monitoring = False
        self._lifecycle_generation += 1
        for handle in self._hotkey_handles:
            try:
                keyboard.remove_hotkey(handle)
            except Exception as error:
                logger.warning('shortcut cleanup failed error=%s', type(error).__name__)
        self._hotkey_handles.clear()
        if self._clipboard:
            try:
                self._clipboard.dataChanged.disconnect(self._on_clipboard_changed)
            except (RuntimeError, TypeError):
                pass
        self._clipboard = None
        self._clear_pending_copy()
        self._event_retry_timer.stop()
        self._pending_event_session = None
        self._last_copy_event = None
        self._invalidate_image_session()
        return self.shutdown_preview()

    def shutdown_preview(self, wait_ms=1000):
        """May be retried while the event loop drains a cancelled image decode."""
        return (self._preview_service.shutdown(wait_ms=wait_ms)
                if self._preview_service else True)

    @Slot(float, object, int)
    def _handle_ctrl_c(self, captured_at=None, sequence=None, generation=None):
        """Associate intent with events, including events delivered before intent."""
        if (not self._is_monitoring or
                (generation is not None and generation != self._lifecycle_generation)):
            return
        now = time.monotonic()
        captured_at = now if captured_at is None else captured_at
        if captured_at <= self._last_paste_at:
            return
        sequence = self._get_clipboard_sequence() if sequence is None else sequence
        timeout_ms = CLIPBOARD_CHECK.get('confirmation_timeout', 700)
        if self._last_copy_event is not None:
            event_id, event_sequence, event_at = self._last_copy_event
            # keyboard itself also dispatches asynchronously. A recent,
            # unclaimed event with the captured sequence is sufficient evidence
            # to avoid reporting an already observed copy as a failure.
            after_capture = event_at >= captured_at
            same_recent_sequence = ((not sequence or sequence == event_sequence) and
                                    0 <= captured_at - event_at <= timeout_ms / 1000)
            if (event_id > self._last_matched_event_id and
                    (after_capture or same_recent_sequence)):
                self._last_matched_event_id = event_id
                self._clear_pending_copy()
                return
        self._pending_copy_sequence = sequence or self._last_sequence
        elapsed_ms = max(0, int((now - captured_at) * 1000))
        self._confirmation_timer.start(max(1, timeout_ms - elapsed_ms))

    @Slot(int, float)
    def _handle_ctrl_v(self, generation=None, captured_at=None):
        if (not self._is_monitoring or
                (generation is not None and generation != self._lifecycle_generation)):
            return
        self._last_paste_at = time.monotonic() if captured_at is None else captured_at
        self._last_copy_event = None
        self._clear_pending_copy()
        self._event_retry_timer.stop()
        self._pending_event_session = None
        self._invalidate_image_session()
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
        self._event_retry_timer.stop()
        self._invalidate_image_session()
        self._pending_event_session = self._image_request_id
        self._event_sequence = sequence
        self._event_received_at = time.monotonic()
        self._event_retry_attempt = 0
        self._process_clipboard_event()

    def _process_clipboard_event(self, session_id=None):
        session_id = self._pending_event_session if session_id is None else session_id
        if (not self._is_monitoring or session_id is None or
                session_id != self._pending_event_session or
                session_id != self._image_request_id):
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
            self._pending_event_session = None
            return

        self._event_retry_timer.stop()
        self._pending_event_session = None
        self._last_copy_event = (session_id, self._event_sequence, self._event_received_at)
        if self._pending_copy_sequence is not None:
            self._last_matched_event_id = session_id
        self._clear_pending_copy()
        self._emit_snapshot(snapshot)

    def _on_confirmation_timeout(self):
        if self._is_monitoring and self._pending_copy_sequence is not None:
            self._clear_pending_copy()
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
            text = ((mime_data.text() or '')[:MAX_TEXT_LENGTH + 1]
                    .replace('\r\n', '\n').replace('\r', '\n')) if mime_data.hasText() else ''
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
                    copied = self._safe_copy(image)
                    if copied is not None:
                        images.append(copied)
                else:
                    image = mime_data.imageData()
                    if isinstance(image, QImage) and not image.isNull():
                        copied = self._safe_copy(image)
                        if copied is not None:
                            images.append(copied)
            if not images:
                raw_image_bytes = self._read_raw_image_mime(mime_data)
            # MIME formats are alternative representations of the same copy,
            # not extra images. Select exactly one source group in priority
            # order: bitmap/raw bytes, local file list, then HTML image sources.
            if not (images or raw_image_bytes) and has_urls:
                for url in mime_data.urls():
                    local_path = url.toLocalFile()
                    if (local_path and self._is_img_file(local_path) and
                            local_path not in file_paths):
                        file_paths.append(local_path)
            if not (images or raw_image_bytes or file_paths) and has_html:
                for source in dict.fromkeys(self._extract_all_srcs(mime_data.html() or '')):
                    if source.startswith('data:image/'):
                        data_uris.append(source)
                    elif source.startswith(('http://', 'https://')):
                        http_urls.append(source)
            if not (images or raw_image_bytes or file_paths or data_uris or http_urls) and text:
                path = self._norm_path(text)
                if path:
                    file_paths.append(path)
                elif text.strip().startswith('data:image/'):
                    data_uris.append(text.strip())

            # Within HTML, distinct src values represent distinct images;
            # enabling remote preview retains HTTP and data sources together.
            if not self._remote_previews:
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
        request_id = self._image_request_id
        if not self._remote_previews:
            image_count -= len(http_urls)
            http_urls = []
        # UI gets a bounded placeholder immediately. Decode and downscale even
        # existing clipboard QImages in the preview service, outside the GUI.
        self.copy_session.emit(request_id, display_text, [], image_count)
        self.copy_success.emit(display_text)
        self.copy_rich.emit(display_text, [], image_count)
        if (not self._is_monitoring or request_id != self._image_request_id or
                not (images or raw_image_bytes or file_paths or data_uris or http_urls)):
            return
        self._start_worker(request_id, http_urls, data_uris, file_paths,
                           raw_image_bytes, IMAGE_STACK.get('max_preload', 4),
                           image_count, images=images)

    def _start_worker(self, request_id, http_urls, data_uris, file_paths,
                      raw_image_bytes, max_images, image_count, images=None):
        if not self._is_monitoring or request_id != self._image_request_id:
            return
        if self._preview_service is None:
            self._preview_service = PreviewService.instance()
            self._preview_service.set_remote_enabled(self._remote_previews)
            self._preview_service.images_ready.connect(
                self._on_images_ready, Qt.QueuedConnection)
        self._preview_service.submit(request_id, http_urls, data_uris, file_paths,
                                     raw_image_bytes, max_images, image_count,
                                     images=images)

    def _on_raw_ready(self, request_id, raw_list, image_count):
        """Compatibility entry point; byte decoding still belongs to the service."""
        if not self._is_monitoring or request_id != self._image_request_id:
            return
        self._start_worker(request_id, [], [], [], raw_list,
                           IMAGE_STACK.get('max_preload', 4), image_count)

    @Slot(int, object, int)
    def _on_images_ready(self, request_id, images, image_count):
        if not self._is_monitoring or request_id != self._image_request_id:
            return
        if images:
            self.images_for_session.emit(request_id, images, image_count)
            self.images_updated.emit(images, image_count)

    def _cancel_image_workers(self):
        if self._preview_service is not None:
            self._preview_service.cancel_all()

    def _invalidate_image_session(self):
        self._image_request_id += 1
        self._cancel_image_workers()

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
        max_size = PREVIEW_LIMITS['max_image_bytes']
        preferred_formats = (
            'image/png', 'image/jpeg', 'image/jpg', 'image/webp',
            'image/gif', 'image/bmp', 'image/tiff',
        )
        try:
            formats = {str(value).lower() for value in mime_data.formats()}
            for mime_type in preferred_formats:
                if mime_type not in formats:
                    continue
                raw = mime_data.data(mime_type)
                if 0 < raw.size() <= max_size:
                    logger.info('clipboard raw image MIME selected type=%s bytes=%s', mime_type, raw.size())
                    return [bytes(raw)]
                logger.warning('clipboard raw image MIME rejected type=%s bytes=%s limit=%s',
                               mime_type, raw.size(), max_size)
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
            if (image.isNull() or
                    image.width() * image.height() > PREVIEW_LIMITS['max_image_pixels'] or
                    image.sizeInBytes() > PREVIEW_LIMITS['decoder_allocation_mb'] * 1024 * 1024):
                return None
            # QImage is implicitly shared: retain its backing storage without a
            # full-resolution deep copy on the GUI thread. Worker makes preview.
            return QImage(image)
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
