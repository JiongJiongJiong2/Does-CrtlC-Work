"""Isolated reproductions of four current clipboard/session defects.

Run from any directory with the project's .venv Python. This is an audit
artifact, not a desired-behavior regression suite: its assertions confirm the
current defects and should stop passing after those defects are repaired.

No QApplication, real clipboard, keyboard hook, network request, worker thread,
or interactive window is created. QCoreApplication only supports local timers;
all clipboard snapshots and sequence numbers are fake. Guard patches reject
accidental clipboard, keyboard-hook, or network access.
"""

from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QBuffer, QCoreApplication, QIODevice
from PySide6.QtGui import QColor, QImage

import core.clipboard_monitor as clipboard_module
from core.clipboard_monitor import ClipboardMonitor
from main import ClipboardFXApp
from ui.feedback_widget import FeedbackType


def forbidden(*args, **kwargs):
    raise AssertionError("Real clipboard, keyboard-hook, and network access is forbidden")


def snapshot(text):
    return (text, [], 0, [], [], [], [])


def event_before_intent():
    monitor = ClipboardMonitor()
    monitor._is_monitoring = True
    monitor._get_clipboard_sequence = lambda: 101
    monitor._read_clipboard_snapshot = lambda: snapshot("copied")
    events = []
    monitor.copy_rich.connect(lambda *args: events.append("copy_confirmed"))
    monitor.copy_failed.connect(lambda: events.append("copy_failed"))
    try:
        monitor._on_clipboard_changed()
        monitor._handle_ctrl_c()
        assert monitor._confirmation_timer.isActive()
        # Advance directly to the timeout callback without wall-clock waiting.
        monitor._on_confirmation_timeout()
        assert events == ["copy_confirmed", "copy_failed"], events
        print("EVENT_THEN_INTENT", events)
    finally:
        monitor._confirmation_timer.stop()
        monitor._event_retry_timer.stop()


def stale_retry_after_new_event():
    monitor = ClipboardMonitor()
    monitor._is_monitoring = True
    sequence = [201]
    monitor._get_clipboard_sequence = lambda: sequence[0]
    snapshots = [None, snapshot("new"), snapshot("new")]
    monitor._read_clipboard_snapshot = lambda: snapshots.pop(0)
    events = []
    monitor.copy_rich.connect(lambda text, *args: events.append(text))
    try:
        monitor._on_clipboard_changed()
        assert monitor._event_retry_timer.isActive()
        sequence[0] = 202
        monitor._on_clipboard_changed()
        retry_active = monitor._event_retry_timer.isActive()
        assert retry_active, "Expected the obsolete retry timer to remain armed"
        print("RETRY_STILL_ACTIVE_AFTER_NEW_SUCCESS", retry_active)
        # Deliver the already scheduled retry without running a GUI event loop.
        monitor._process_clipboard_event()
        assert events == ["new", "new"], events
        print("NEW_EVENT_AND_OLD_RETRY", events)
    finally:
        monitor._confirmation_timer.stop()
        monitor._event_retry_timer.stop()


def late_image_after_paste():
    # Build a tiny valid PNG entirely in memory, avoiding decode-error paths.
    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    buffer = QBuffer()
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    png = bytes(buffer.data())
    buffer.close()

    received = []
    paste_widget = SimpleNamespace(
        _active=True,
        _feedback_type=FeedbackType.PASTE,
        update_images=lambda images, count: received.append((len(images), count)),
    )
    controller = SimpleNamespace(_current_widget=paste_widget)
    monitor = ClipboardMonitor()
    monitor._image_request_id = 77
    monitor.images_updated.connect(
        lambda images, count: ClipboardFXApp._on_images_updated(controller, images, count)
    )
    # Paste replaces the feedback window without advancing the copy request ID.
    monitor._on_raw_ready(77, [png], 1)
    assert received == [(1, 1)], received
    assert paste_widget._feedback_type == FeedbackType.PASTE
    print("LATE_COPY_IMAGE_ROUTED_TO_PASTE_WIDGET", received)


def copy_cache_key_deduplication():
    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    first_copy = image.copy()
    known_keys = {first_copy.cacheKey()}
    second_copy = image.copy()
    # Mirrors FeedbackWidget._append_images: compare the freshly copied key.
    is_duplicate = second_copy.cacheKey() in known_keys
    assert not is_duplicate, "Expected fresh copy keys to defeat current deduplication"
    assert first_copy == second_copy, "Pixel content should still be identical"
    print("IDENTICAL_PIXELS", first_copy == second_copy)
    print("COPY_BASED_DEDUP_MATCH", is_duplicate)


def main():
    app = QCoreApplication.instance() or QCoreApplication([])
    with ExitStack() as guards:
        guards.enter_context(patch.object(
            clipboard_module, "QGuiApplication", SimpleNamespace(clipboard=forbidden)
        ))
        guards.enter_context(patch.object(clipboard_module, "urlopen", forbidden))
        guards.enter_context(patch("urllib.request.urlopen", forbidden))
        guards.enter_context(patch("socket.create_connection", forbidden))
        for function in ("add_hotkey", "hook", "hook_key", "unhook_all_hotkeys"):
            guards.enter_context(patch("keyboard." + function, forbidden))
        event_before_intent()
        stale_retry_after_new_event()
        late_image_after_paste()
        copy_cache_key_deduplication()
    assert app is not None
    print("AUDIT_RESULT: all 4 current defects reproduced in isolation")


if __name__ == "__main__":
    main()
