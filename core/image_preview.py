"""Bounded clipboard previews: one scheduler, cancellable network, worker decoding."""

import base64
import ipaddress
import logging
import os
import stat
from collections import deque
from threading import Event, Lock

from PySide6.QtCore import (QBuffer, QByteArray, QCoreApplication, QIODevice,
                            QObject, QRunnable, QSize, QThreadPool, QTimer,
                            Qt, QUrl, Signal, Slot, SLOT)
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtNetwork import (QHostInfo, QNetworkAccessManager, QNetworkProxy,
                               QNetworkReply, QNetworkRequest)

from config import PREVIEW_LIMITS

logger = logging.getLogger(__name__)


def is_public_address(value):
    """Never allow loopback, private, link-local, multicast or mapped private IPs."""
    try:
        address = ipaddress.ip_address(str(value))
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return address.is_global and not address.is_multicast
    except ValueError:
        return False


def remote_url(value):
    url = QUrl(value)
    if (len(value) > 4096 or not url.isValid() or url.scheme() not in ('http', 'https')
            or not url.host() or url.userName() or url.password()
            or url.port(-1) not in (-1, 80 if url.scheme() == 'http' else 443)):
        return None
    url.setFragment('')
    return url


def pinned_request(url, address):
    """Connect to the vetted IP while retaining HTTP Host and TLS peer validation."""
    if not is_public_address(address):
        raise ValueError('preview address must be public')
    target = QUrl(url)
    target.setHost(address)
    request = QNetworkRequest(target)
    request.setPeerVerifyName(url.host())
    request.setRawHeader(b'Host', url.authority(QUrl.FullyEncoded).encode('ascii'))
    request.setRawHeader(b'User-Agent', b'DoseCtrlC-Preview')
    request.setAttribute(QNetworkRequest.RedirectPolicyAttribute,
                         QNetworkRequest.ManualRedirectPolicy)
    request.setAttribute(QNetworkRequest.CookieLoadControlAttribute, QNetworkRequest.Manual)
    request.setAttribute(QNetworkRequest.CookieSaveControlAttribute, QNetworkRequest.Manual)
    request.setAttribute(QNetworkRequest.AuthenticationReuseAttribute, QNetworkRequest.Manual)
    return request


class _RemoteFetch(QObject):
    finished = Signal(object)

    def __init__(self, manager, value, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._url = remote_url(value)
        self._reply = None
        self._lookup = None
        self._ended = False
        self._data = bytearray()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._finish(None))

    def start(self):
        if self._url is None:
            self._finish(None)
            return
        self._timer.start(PREVIEW_LIMITS['remote_deadline_ms'])
        host = self._url.host()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            self._lookup = QHostInfo.lookupHost(host, self, SLOT('_resolved(QHostInfo)'))
        else:
            if is_public_address(host):
                self._request(host)
            else:
                self._finish(None)

    @Slot(QHostInfo)
    def _resolved(self, info):
        self._lookup = None
        if self._ended:
            return
        addresses = [address.toString() for address in info.addresses()]
        if info.error() != QHostInfo.NoError or not addresses or not all(
                is_public_address(address) for address in addresses):
            self._finish(None)
            return
        addresses.sort(key=lambda address: ':' in address)
        self._request(addresses[0])

    def _request(self, address):
        self._reply = self._manager.get(pinned_request(self._url, address))
        self._reply.setReadBufferSize(65536)
        self._reply.readyRead.connect(self._read_available)
        self._reply.finished.connect(self._network_finished)

    def _read_available(self):
        if self._ended or self._reply is None:
            return
        limit = PREVIEW_LIMITS['max_image_bytes']
        length = self._reply.header(QNetworkRequest.ContentLengthHeader)
        if length is not None and int(length) > limit:
            self._finish(None)
            return
        self._data.extend(bytes(self._reply.read(limit - len(self._data) + 1)))
        if len(self._data) > limit:
            self._finish(None)

    def _network_finished(self):
        if self._ended:
            return
        self._read_available()
        if self._ended:
            return
        status = self._reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        content_type = bytes(self._reply.rawHeader('Content-Type')).lower()
        # Every redirect is refused, including public-to-private and HTTPS downgrades.
        ok = (self._reply.error() == QNetworkReply.NoError and status == 200
              and content_type.startswith(b'image/'))
        self._finish(bytes(self._data) if ok else None)

    def cancel(self):
        self._finish(None)

    def _finish(self, data):
        if self._ended:
            return
        self._ended = True
        self._timer.stop()
        if self._lookup is not None:
            QHostInfo.abortHostLookup(self._lookup)
            self._lookup = None
        if self._reply is not None:
            if self._reply.isRunning():
                self._reply.abort()
            self._reply.deleteLater()
            self._reply = None
        self._data.clear()
        self.finished.emit(data)


class _Budget:
    def __init__(self):
        self._lock = Lock()
        self._bytes = 0
        self._pixels = 0

    def reserve_bytes(self, count):
        with self._lock:
            if count <= 0 or count > PREVIEW_LIMITS['max_image_bytes'] or (
                    self._bytes + count > PREVIEW_LIMITS['max_total_bytes']):
                return False
            self._bytes += count
            return True

    def reserve_pixels(self, count):
        with self._lock:
            if count <= 0 or count > PREVIEW_LIMITS['max_image_pixels'] or (
                    self._pixels + count > PREVIEW_LIMITS['max_total_pixels']):
                return False
            self._pixels += count
            return True


def _read_file(path):
    # A clipboard preview must not open named pipes, devices or network shares.
    path = os.fspath(path)
    if path.startswith(('\\\\', '//')):
        return None
    path = os.path.realpath(path)
    if path.startswith(('\\\\', '//')):
        return None
    if os.name == 'nt':
        import ctypes
        drive = os.path.splitdrive(os.path.abspath(path))[0] + '\\'
        if ctypes.windll.kernel32.GetDriveTypeW(drive) != 3:  # fixed local drive
            return None
    try:
        info = os.stat(path)
        limit = PREVIEW_LIMITS['max_image_bytes']
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            return None
        with open(path, 'rb') as source:
            # Recheck the opened object too (the path may change after stat).
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                return None
            data = source.read(limit + 1)
        return data if 0 < len(data) <= limit else None
    except (OSError, ValueError):
        return None


def _decode_data_uri(uri):
    limit = PREVIEW_LIMITS['max_image_bytes']
    if len(uri) > ((limit + 2) // 3) * 4 + 128:
        return None
    header, separator, payload = uri.partition(',')
    if not separator or not header.startswith('data:image/') or not header.endswith(';base64'):
        return None
    try:
        data = base64.b64decode(payload, validate=True)
        return data if 0 < len(data) <= limit else None
    except (ValueError, base64.binascii.Error):
        return None


def _decode_source(kind, value, cancelled, budget):
    if cancelled.is_set():
        return None
    edge = PREVIEW_LIMITS['thumbnail_edge']
    if kind == 'image':
        if (not isinstance(value, QImage) or value.isNull()
                or value.sizeInBytes() > PREVIEW_LIMITS['decoder_allocation_mb'] * 1024 * 1024
                or not budget.reserve_pixels(value.width() * value.height())):
            return None
        image = value.scaled(edge, edge, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    else:
        data = (_read_file(value) if kind == 'file' else
                _decode_data_uri(value) if kind == 'data' else value)
        if cancelled.is_set() or not data or not budget.reserve_bytes(len(data)):
            return None
        buffer = QBuffer()
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.ReadOnly)
        reader = QImageReader(buffer)
        reader.setAutoTransform(True)
        size = reader.size()
        if not size.isValid() or not budget.reserve_pixels(size.width() * size.height()):
            return None
        reader.setScaledSize(size.scaled(QSize(edge, edge), Qt.KeepAspectRatio))
        image = reader.read()
        if image.isNull() or cancelled.is_set():
            return None
        if image.width() > edge or image.height() > edge:
            image = image.scaled(edge, edge, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return None if cancelled.is_set() else image


class _TaskSignals(QObject):
    done = Signal(int, object)


class _DecodeTask(QRunnable):
    def __init__(self, job_id, kind, value, cancelled, budget):
        super().__init__()
        self.signals = _TaskSignals()
        self.job_id = job_id
        self.kind, self.value = kind, value
        self.cancelled, self.budget = cancelled, budget

    def run(self):
        image = None
        try:
            image = _decode_source(self.kind, self.value, self.cancelled, self.budget)
        except Exception:
            logger.exception('clipboard preview decode failed')
        finally:
            self.signals.done.emit(self.job_id, image)


class PreviewService(QObject):
    """Application-owned latest-request scheduler; never creates a pool per copy."""
    images_ready = Signal(int, object, int)

    @classmethod
    def instance(cls):
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError('PreviewService needs a Qt application')
        service = getattr(app, '_dose_preview_service', None)
        if service is not None and service._closing and service._pool.waitForDone(0):
            service.deleteLater()
            service = None
        if service is None:
            service = cls(app)
            app._dose_preview_service = service
        return service

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(PREVIEW_LIMITS['max_concurrent'])
        self._pool.setExpiryTimeout(1000)
        self._network = QNetworkAccessManager(self)
        self._network.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        self._remote_enabled = False
        self._closing = False
        self._cancelling = False
        self._queue = deque()
        self._running = {}
        self._job_sequence = 0
        self._generation = 0
        self._request_id = None
        self._results = []
        self._outstanding = 0
        self._image_count = 0
        self._cancelled = Event()
        self._budget = _Budget()
        # This is also a guard for codecs that do not support scaled decoding.
        QImageReader.setAllocationLimit(PREVIEW_LIMITS['decoder_allocation_mb'])

    def set_remote_enabled(self, enabled):
        self._remote_enabled = bool(enabled)
        if not self._remote_enabled:
            self.cancel_all()

    def submit(self, request_id, http_urls, data_uris, file_paths, raw_image_bytes,
               max_images, image_count, images=None):
        if self._closing:
            return
        self.cancel_all()
        self._request_id = request_id
        self._image_count = image_count
        self._cancelled = Event()
        self._budget = _Budget()
        limit = max(0, min(int(max_images), PREVIEW_LIMITS['max_images']))
        sources = []
        for kind, values in (('image', images or []), ('raw', raw_image_bytes),
                             ('file', file_paths), ('data', data_uris),
                             ('http', http_urls if self._remote_enabled else [])):
            for value in values:
                if len(sources) >= limit:
                    break
                sources.append((kind, value))
        self._results = [None] * len(sources)
        self._outstanding = len(sources)
        for index, (kind, value) in enumerate(sources):
            self._job_sequence += 1
            self._queue.append((self._job_sequence, self._generation, index, kind,
                                value, self._cancelled, self._budget))
        self._pump()

    def cancel_all(self):
        self._cancelling = True
        self._generation += 1
        self._cancelled.set()
        self._queue.clear()
        self._results = []
        self._outstanding = 0
        for job, worker in tuple(self._running.values()):
            job[5].set()
            if isinstance(worker, _RemoteFetch):
                worker.cancel()
        self._cancelling = False

    def _pump(self):
        if self._closing or self._cancelling:
            return
        while self._queue and len(self._running) < PREVIEW_LIMITS['max_concurrent']:
            job = self._queue.popleft()
            job_id, generation, index, kind, value, cancelled, budget = job
            if kind == 'http':
                worker = _RemoteFetch(self._network, value, self)
                self._running[job_id] = (job, worker)
                worker.finished.connect(lambda data, key=job_id: self._remote_done(key, data))
                worker.start()
            else:
                self._start_decode(job)

    def _start_decode(self, job):
        job_id, generation, index, kind, value, cancelled, budget = job
        worker = _DecodeTask(job_id, kind, value, cancelled, budget)
        worker.signals.done.connect(self._decoded, Qt.QueuedConnection)
        self._running[job_id] = (job, worker)
        self._pool.start(worker)

    def _remote_done(self, job_id, data):
        entry = self._running.pop(job_id, None)
        if entry is None:
            return
        job, worker = entry
        worker.deleteLater()
        if data and job[1] == self._generation and not self._closing:
            self._start_decode((*job[:3], 'raw', data, *job[5:]))
        else:
            self._complete_job(job, None)
        self._pump()

    @Slot(int, object)
    def _decoded(self, job_id, image):
        entry = self._running.pop(job_id, None)
        if entry is not None:
            self._complete_job(entry[0], image)
        self._pump()

    def _complete_job(self, job, image):
        if job[1] != self._generation or self._closing:
            return
        self._results[job[2]] = image
        self._outstanding -= 1
        if self._outstanding == 0:
            images = [value for value in self._results if value is not None]
            self._results = []
            if images:
                self.images_ready.emit(self._request_id, images, self._image_count)

    def shutdown(self, wait_ms=1000):
        """Abort networking immediately; caller keeps Qt alive if local work remains.

        Local filesystem/codec calls are cooperative, not forcibly interrupted.
        Returning False means the owner must retry before destroying QApplication.
        """
        self._closing = True
        self.cancel_all()
        return self._pool.waitForDone(max(0, int(wait_ms)))


class _ImageDataWorker(QObject):
    """Legacy synchronous local-byte adapter; production uses PreviewService.

    Kept for integrations that imported the old helper. It cannot fetch URLs or
    create private thread pools; every source has the same byte/count budget.
    """
    raw_images_ready = Signal(int, list)

    def __init__(self, request_id, max_images, parent=None):
        super().__init__(parent)
        self._request_id = request_id
        self._max_images = min(max(0, max_images), PREVIEW_LIMITS['max_images'])
        self._cancelled = Event()
        self._sources = []

    def set_tasks(self, http_urls, data_uris, file_paths, raw_image_bytes=None):
        self._sources = ([('raw', value) for value in (raw_image_bytes or [])]
                         + [('file', value) for value in file_paths]
                         + [('data', value) for value in data_uris])[:self._max_images]

    def cancel(self):
        self._cancelled.set()

    def run(self):
        budget, result = _Budget(), []
        for kind, value in self._sources:
            if self._cancelled.is_set():
                return
            data = (_read_file(value) if kind == 'file' else
                    _decode_data_uri(value) if kind == 'data' else value)
            if data and budget.reserve_bytes(len(data)):
                result.append(data)
        if not self._cancelled.is_set():
            self.raw_images_ready.emit(self._request_id, result)

    _read_file = staticmethod(_read_file)
    _decode_data_uri = staticmethod(_decode_data_uri)
