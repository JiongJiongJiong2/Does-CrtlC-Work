"""Read the current Windows cursor footprint once per feedback session."""

import ctypes
import sys
from dataclasses import dataclass

from PySide6.QtGui import QCursor, QGuiApplication

from config import SIZES


_DEFAULT_CURSOR_EDGE_DIP = 32.0
_MAX_CURSOR_OFFSET_DIP = 160.0


class _Point(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


class _CursorInfo(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.c_uint32),
        ('flags', ctypes.c_uint32),
        ('hCursor', ctypes.c_void_p),
        ('ptScreenPos', _Point),
    ]


class _IconInfo(ctypes.Structure):
    _fields_ = [
        ('fIcon', ctypes.c_int),
        ('xHotspot', ctypes.c_uint32),
        ('yHotspot', ctypes.c_uint32),
        ('hbmMask', ctypes.c_void_p),
        ('hbmColor', ctypes.c_void_p),
    ]


class _Bitmap(ctypes.Structure):
    _fields_ = [
        ('bmType', ctypes.c_long),
        ('bmWidth', ctypes.c_long),
        ('bmHeight', ctypes.c_long),
        ('bmWidthBytes', ctypes.c_long),
        ('bmPlanes', ctypes.c_ushort),
        ('bmBitsPixel', ctypes.c_ushort),
        ('bmBits', ctypes.c_void_p),
    ]


def cursor_ui_scale(cursor_size_dip: float) -> float:
    """Return stable buckets so cursor-shape changes cannot cause tiny jitter."""
    if cursor_size_dip <= 40:
        return 1.0
    if cursor_size_dip <= 56:
        return 1.15
    if cursor_size_dip <= 72:
        return 1.30
    return 1.50


@dataclass(frozen=True)
class CursorMetrics:
    width_dip: float
    height_dip: float
    hotspot_x_dip: float
    hotspot_y_dip: float
    ui_scale: float
    offset_x: float
    offset_y: float

    @classmethod
    def default(cls):
        offset_x = float(SIZES['mouse_offset_x'])
        offset_y = float(SIZES['mouse_offset_y'])
        return cls(_DEFAULT_CURSOR_EDGE_DIP, _DEFAULT_CURSOR_EDGE_DIP,
                   0.0, 0.0, 1.0, offset_x, offset_y)

    @classmethod
    def from_dip(cls, width: float, height: float,
                 hotspot_x: float = 0.0, hotspot_y: float = 0.0):
        width = max(1.0, float(width))
        height = max(1.0, float(height))
        hotspot_x = max(0.0, min(float(hotspot_x), width))
        hotspot_y = max(0.0, min(float(hotspot_y), height))
        scale = cursor_ui_scale(max(width, height))

        # Keep the default cursor exactly where it was. Above the default
        # footprint, move past the cursor edge plus a small gap. UI scale and
        # placement have separate caps: a capped 1.5x card still must not sit
        # underneath a 96/128px accessibility pointer.
        right_extent = max(0.0, width - hotspot_x)
        bottom_extent = max(0.0, height - hotspot_y)
        base_x = float(SIZES['mouse_offset_x']) * scale
        base_y = float(SIZES['mouse_offset_y']) * scale
        offset_x = cls._placement_offset(
            right_extent, base_x, float(SIZES['mouse_offset_x']))
        offset_y = cls._placement_offset(
            bottom_extent, base_y, float(SIZES['mouse_offset_y']))
        return cls(width, height, hotspot_x, hotspot_y, scale, offset_x, offset_y)

    @staticmethod
    def _placement_offset(cursor_extent: float, scaled_base: float,
                          default_offset: float) -> float:
        if cursor_extent <= _DEFAULT_CURSOR_EDGE_DIP:
            return default_offset
        clearance = max(8.0, scaled_base * 0.5)
        return min(_MAX_CURSOR_OFFSET_DIP,
                   max(scaled_base, cursor_extent + clearance))

    @classmethod
    def detect(cls):
        if not sys.platform.startswith('win'):
            return cls.default()
        raw = cls._read_windows_cursor()
        system_cursor_size = cls._read_windows_cursor_base_size()
        if raw is None and system_cursor_size is None:
            return cls.default()
        if raw is None:
            return cls.from_dip(system_cursor_size, system_cursor_size)

        width_px, height_px, hotspot_x_px, hotspot_y_px = raw
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        dpr = max(1.0, float(screen.devicePixelRatio())) if screen else 1.0
        width_dip = width_px / dpr
        height_dip = height_px / dpr
        hotspot_x_dip = hotspot_x_px / dpr
        hotspot_y_dip = hotspot_y_px / dpr

        # Windows accessibility pointer size can scale a cursor display while
        # GetIconInfo still exposes its original resource bitmap. CursorBaseSize
        # is the lightest available source in this PySide-only project. Scale
        # the resource hotspot with it so the visible footprint stays coherent.
        resource_edge = max(width_dip, height_dip)
        if system_cursor_size and system_cursor_size > resource_edge:
            factor = system_cursor_size / resource_edge
            width_dip *= factor
            height_dip *= factor
            hotspot_x_dip *= factor
            hotspot_y_dip *= factor
        return cls.from_dip(width_dip, height_dip, hotspot_x_dip, hotspot_y_dip)

    @staticmethod
    def _read_windows_cursor_base_size():
        """Read the user's Windows accessibility pointer size in DIP.

        There is an official WinRT UISettings.CursorSize API, but this project
        intentionally has no WinRT binding. The same per-user setting is kept
        in CursorBaseSize and can be read with the Python standard library.
        """
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r'Control Panel\Cursors') as key:
                value, _ = winreg.QueryValueEx(key, 'CursorBaseSize')
            size = float(value)
        except (ImportError, OSError, TypeError, ValueError):
            return None
        return size if 1.0 <= size <= 512.0 else None

    @staticmethod
    def _read_windows_cursor():
        """Return physical-pixel (width, height, hotspot_x, hotspot_y)."""
        try:
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
        except AttributeError:
            return None

        # Explicit signatures prevent 64-bit HCURSOR/HBITMAP handles from
        # being implicitly narrowed to C int by ctypes.
        user32.GetCursorInfo.argtypes = [ctypes.POINTER(_CursorInfo)]
        user32.GetCursorInfo.restype = ctypes.c_int
        user32.GetIconInfo.argtypes = [ctypes.c_void_p,
                                       ctypes.POINTER(_IconInfo)]
        user32.GetIconInfo.restype = ctypes.c_int
        gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                     ctypes.c_void_p]
        gdi32.GetObjectW.restype = ctypes.c_int
        gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        gdi32.DeleteObject.restype = ctypes.c_int

        cursor = _CursorInfo()
        cursor.cbSize = ctypes.sizeof(_CursorInfo)
        icon = _IconInfo()
        try:
            if not user32.GetCursorInfo(ctypes.byref(cursor)):
                return None
            if not (cursor.flags & 0x00000001) or not cursor.hCursor:
                return None
            if not user32.GetIconInfo(cursor.hCursor, ctypes.byref(icon)):
                return None

            bitmap_handle = icon.hbmColor or icon.hbmMask
            if not bitmap_handle:
                return None
            bitmap = _Bitmap()
            if not gdi32.GetObjectW(bitmap_handle, ctypes.sizeof(_Bitmap),
                                    ctypes.byref(bitmap)):
                return None
            width = abs(int(bitmap.bmWidth))
            height = abs(int(bitmap.bmHeight))
            if not icon.hbmColor:
                height //= 2
            if width <= 0 or height <= 0:
                return None
            return width, height, int(icon.xHotspot), int(icon.yHotspot)
        except (AttributeError, OSError, ValueError):
            return None
        finally:
            # GetIconInfo creates these bitmaps; the caller owns both handles.
            handles = {handle for handle in (icon.hbmColor, icon.hbmMask) if handle}
            for handle in handles:
                try:
                    gdi32.DeleteObject(handle)
                except (AttributeError, OSError):
                    pass
