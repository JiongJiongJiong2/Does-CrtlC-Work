"""Read the visible bottom taskbar edge without changing shell settings."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


ABM_GETAUTOHIDEBAREX = 0x0000000B
ABE_BOTTOM = 3
MONITOR_DEFAULTTONEAREST = 2
HIDDEN_STRIP_DIP = 4.0


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _Rect),
        ("rcWork", _Rect),
        ("dwFlags", wintypes.DWORD),
    ]


class _AppBarData(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", _Rect),
        ("lParam", wintypes.LPARAM),
    ]


class TaskbarBoundary:
    """Return a logical-pixel bottom boundary for one Qt screen.

    Qt's available geometry already handles a fixed taskbar. Windows' public
    appbar API is consulted only for an auto-hide taskbar, whose current
    animated rectangle is not necessarily reserved in the work area.
    """

    @classmethod
    def effective_bottom(cls, screen, window_id: int) -> float:
        available = screen.availableGeometry()
        geometry = screen.geometry()
        qt_bottom = float(available.y() + available.height())
        screen_bottom = float(geometry.y() + geometry.height())

        if not sys.platform.startswith("win"):
            return qt_bottom

        native_top = cls._windows_autohide_top(window_id)
        if native_top is None:
            return qt_bottom

        native_monitor_top, native_monitor_bottom, taskbar_top = native_top
        native_height = native_monitor_bottom - native_monitor_top
        if native_height <= 0 or geometry.height() <= 0:
            return qt_bottom

        scale = geometry.height() / native_height
        taskbar_top_logical = geometry.y() + (
            taskbar_top - native_monitor_top) * scale

        # A hidden auto-hide taskbar leaves only its activation strip. Do not
        # lift the feedback for that strip; start following once it slides in.
        if screen_bottom - taskbar_top_logical <= HIDDEN_STRIP_DIP:
            return min(qt_bottom, screen_bottom)
        return min(qt_bottom, taskbar_top_logical)

    @staticmethod
    def _windows_autohide_top(window_id: int):
        try:
            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            user32.MonitorFromWindow.restype = wintypes.HMONITOR
            user32.MonitorFromWindow.argtypes = [
                wintypes.HWND, wintypes.DWORD]
            # GetMonitorInfoW is also used by the native tray menu. ctypes
            # stores signatures on the shared DLL function object, so using
            # two different POINTER(MONITORINFO) classes makes whichever
            # module initialized last reject the other's structure. Keep the
            # output parameter untyped while retaining the correct layout.
            user32.GetMonitorInfoW.argtypes = [
                wintypes.HMONITOR, ctypes.c_void_p]
            user32.GetWindowRect.argtypes = [
                wintypes.HWND, ctypes.c_void_p]
            shell32.SHAppBarMessage.argtypes = [
                wintypes.DWORD, ctypes.c_void_p]

            monitor = user32.MonitorFromWindow(
                wintypes.HWND(int(window_id)), MONITOR_DEFAULTTONEAREST)
            if not monitor:
                return None

            monitor_info = _MonitorInfo()
            monitor_info.cbSize = ctypes.sizeof(_MonitorInfo)
            if not user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
                return None

            appbar = _AppBarData()
            appbar.cbSize = ctypes.sizeof(_AppBarData)
            appbar.uEdge = ABE_BOTTOM
            appbar.rc = monitor_info.rcMonitor
            shell32.SHAppBarMessage.restype = ctypes.c_size_t
            taskbar = shell32.SHAppBarMessage(
                ABM_GETAUTOHIDEBAREX, ctypes.byref(appbar))
            if not taskbar:
                return None

            taskbar_rect = _Rect()
            if not user32.GetWindowRect(
                    wintypes.HWND(taskbar), ctypes.byref(taskbar_rect)):
                return None
            return (monitor_info.rcMonitor.top,
                    monitor_info.rcMonitor.bottom,
                    taskbar_rect.top)
        except (AttributeError, ctypes.ArgumentError, OSError, TypeError,
                ValueError):
            return None
