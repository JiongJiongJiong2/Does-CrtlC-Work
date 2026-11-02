"""Offline checks for preview limits, generation isolation and safe shutdown."""

import base64
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QUrl, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtNetwork import QHostAddress, QHostInfo, QNetworkReply, QNetworkRequest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from config import PREVIEW_LIMITS
from core.image_preview import (PreviewService, _Budget, _RemoteFetch,
                                _decode_data_uri, _decode_source, _read_file,
                                is_public_address, pinned_request, remote_url)


def png_bytes(width=20, height=10, color='red'):
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(QColor(color))
    array = QByteArray()
    buffer = QBuffer(array)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, 'PNG')
    return bytes(array)


class Reply(QObject):
    readyRead = Signal()
    finished = Signal()

    def __init__(self, payload=b'', status=200, content_type=b'image/png'):
        super().__init__()
        self.payload, self.status, self.content_type = payload, status, content_type
        self.running = True
        self.aborted = False

    def setReadBufferSize(self, size):
        self.buffer_size = size

    def header(self, header):
        return len(self.payload)

    def rawHeader(self, header):
        return self.content_type

    def attribute(self, name):
        return self.status

    def read(self, size):
        data, self.payload = self.payload[:size], self.payload[size:]
        return data

    def error(self):
        return QNetworkReply.NoError

    def isRunning(self):
        return self.running

    def abort(self):
        self.aborted, self.running = True, False
        self.finished.emit()

    def complete(self):
        self.running = False
        self.finished.emit()


class Manager:
    def __init__(self, reply):
        self.reply = reply
        self.requests = []

    def get(self, request):
        self.requests.append(request)
        return self.reply


class ImagePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_until(self, condition, timeout=2000):
        deadline = time.monotonic() + timeout / 1000
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(5)
        self.assertTrue(condition())

    def test_byte_budget_applies_to_files_raw_and_data_uris(self):
        with patch.dict(PREVIEW_LIMITS, max_image_bytes=16, max_total_bytes=24):
            budget = _Budget()
            self.assertTrue(budget.reserve_bytes(16))
            self.assertFalse(budget.reserve_bytes(9))
            self.assertFalse(_decode_data_uri('data:image/png;base64,' + base64.b64encode(b'x' * 17).decode()))
            with tempfile.TemporaryDirectory() as directory:
                path = os.path.join(directory, 'image.png')
                with open(path, 'wb') as target:
                    target.write(b'x' * 17)
                self.assertIsNone(_read_file(path))
            self.assertIsNone(_read_file(r'\\server\share\image.png'))

    def test_decode_checks_dimensions_and_returns_bounded_thumbnail(self):
        raw = png_bytes(1200, 800)
        image = _decode_source('raw', raw, threading.Event(), _Budget())
        self.assertFalse(image.isNull())
        self.assertLessEqual(max(image.width(), image.height()), PREVIEW_LIMITS['thumbnail_edge'])
        with patch.dict(PREVIEW_LIMITS, max_image_pixels=100):
            self.assertIsNone(_decode_source('raw', raw, threading.Event(), _Budget()))

    def test_raw_image_and_qimage_have_the_same_aggregate_pixel_budget(self):
        budget = _Budget()
        with patch.dict(PREVIEW_LIMITS, max_total_pixels=250):
            self.assertIsNotNone(_decode_source('raw', png_bytes(), threading.Event(), budget))
            image = QImage(20, 10, QImage.Format_ARGB32)
            image.fill(QColor('red'))
            self.assertIsNone(_decode_source('image', image, threading.Event(), budget))

    def test_private_and_credentialed_remote_targets_are_rejected(self):
        for address in ('127.0.0.1', '192.168.1.2', '169.254.169.254', '::1',
                        '::ffff:127.0.0.1', '224.0.0.1', 'fd00::1'):
            self.assertFalse(is_public_address(address), address)
        self.assertTrue(is_public_address('1.1.1.1'))
        for url in ('file:///tmp/a.png', 'https://u:p@example.com/a.png',
                    'https://example.com:8443/a.png'):
            self.assertIsNone(remote_url(url))

    def test_pinned_request_preserves_host_and_tls_name_without_redirects(self):
        request = pinned_request(QUrl('https://images.example.com/a.png?x=1'), '1.1.1.1')
        self.assertEqual(request.url().host(), '1.1.1.1')
        self.assertEqual(bytes(request.rawHeader('Host')), b'images.example.com')
        self.assertEqual(request.peerVerifyName(), 'images.example.com')
        self.assertEqual(request.attribute(QNetworkRequest.RedirectPolicyAttribute),
                         QNetworkRequest.ManualRedirectPolicy)

    def test_remote_redirect_never_starts_another_request(self):
        reply = Reply(b'private redirect', status=302)
        manager = Manager(reply)
        fetch = _RemoteFetch(manager, 'https://1.1.1.1/image.png')
        received = []
        fetch.finished.connect(received.append)
        fetch.start()
        reply.complete()
        self.assertEqual(received, [None])
        self.assertEqual(len(manager.requests), 1)

    def test_dns_answers_are_checked_before_connecting_and_lookup_is_cancellable(self):
        manager = Manager(Reply())
        fetch = _RemoteFetch(manager, 'https://example.com/image.png')
        info = QHostInfo()
        info.setAddresses([QHostAddress('1.1.1.1'), QHostAddress('127.0.0.1')])
        received = []
        fetch.finished.connect(received.append)
        fetch._resolved(info)
        self.assertEqual(received, [None])
        self.assertFalse(manager.requests)
        fetch = _RemoteFetch(manager, 'https://example.com/image.png')
        with patch('core.image_preview.QHostInfo.lookupHost', return_value=99), \
                patch('core.image_preview.QHostInfo.abortHostLookup') as abort:
            fetch.start()
            fetch.cancel()
            abort.assert_called_once_with(99)

    def test_remote_deadline_and_explicit_cancel_abort_pending_reply(self):
        for cancel in (False, True):
            reply = Reply()
            fetch = _RemoteFetch(Manager(reply), 'https://1.1.1.1/image.png')
            received = []
            fetch.finished.connect(received.append)
            with patch.dict(PREVIEW_LIMITS, remote_deadline_ms=20):
                fetch.start()
                if cancel:
                    fetch.cancel()
                self.wait_until(lambda: bool(received))
            self.assertEqual(received, [None])
            self.assertTrue(reply.aborted)

    def test_remote_response_size_is_bounded(self):
        reply = Reply(b'x' * 17)
        fetch = _RemoteFetch(Manager(reply), 'https://1.1.1.1/image.png')
        received = []
        fetch.finished.connect(received.append)
        with patch.dict(PREVIEW_LIMITS, max_image_bytes=16):
            fetch.start()
            reply.readyRead.emit()
        self.assertEqual(received, [None])
        self.assertTrue(reply.aborted)

    def test_remote_preview_is_disabled_by_default(self):
        service = PreviewService()
        try:
            with patch('core.image_preview._RemoteFetch', side_effect=AssertionError('network')):
                service.submit(1, ['https://example.com/a.png'], [], [], [], 4, 1)
                self.assertEqual(len(service._running), 0)
                self.assertEqual(len(service._queue), 0)
        finally:
            self.assertTrue(service.shutdown())

    def test_latest_request_cancels_old_queue_with_global_concurrency_limit(self):
        service = PreviewService()
        gate, lock = threading.Event(), threading.Lock()
        calls, active, peak, worker_threads, received = [], [0], [0], [], []
        service.images_ready.connect(lambda *args: received.append(args))

        def decode(kind, value, cancelled, budget):
            with lock:
                calls.append(value)
                active[0] += 1
                peak[0] = max(peak[0], active[0])
                worker_threads.append(threading.get_ident())
            gate.wait(2)
            with lock:
                active[0] -= 1
            if cancelled.is_set():
                return None
            image = QImage(1, 1, QImage.Format_ARGB32)
            image.fill(QColor('red' if value == b'new1' else 'blue'))
            return image

        try:
            with patch('core.image_preview._decode_source', side_effect=decode):
                service.submit(1, [], [], [], [b'old1', b'old2', b'old3', b'old4'], 4, 4)
                self.wait_until(lambda: len(calls) == 3)
                service.submit(2, [], [], [], [b'new1', b'new2'], 4, 2)
                gate.set()
                self.wait_until(lambda: bool(received))
            self.assertLessEqual(peak[0], 3)
            self.assertNotIn(b'old4', calls)
            self.assertEqual([value[0] for value in received], [2])
            self.assertEqual([image.pixelColor(0, 0).name() for image in received[0][1]],
                             ['#ff0000', '#0000ff'])
            self.assertNotIn(threading.get_ident(), worker_threads)
        finally:
            gate.set()
            self.assertTrue(service.shutdown())

    def test_shutdown_reports_local_work_and_can_be_retried_without_new_jobs(self):
        service = PreviewService()
        gate, started = threading.Event(), threading.Event()

        def decode(*args):
            started.set()
            gate.wait(2)
            return None

        try:
            with patch('core.image_preview._decode_source', side_effect=decode):
                service.submit(1, [], [], [], [b'raw'], 1, 1)
                self.wait_until(started.is_set)
                self.assertFalse(service.shutdown(wait_ms=1))
                service.submit(2, [], [], [], [b'new'], 1, 1)
                self.assertFalse(service._queue)
                gate.set()
                self.assertTrue(service.shutdown(wait_ms=1000))
        finally:
            gate.set()
            service.shutdown()


if __name__ == '__main__':
    unittest.main()
