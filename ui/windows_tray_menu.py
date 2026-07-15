"""Owner-drawn Win32 tray menu with a real native popup-menu loop."""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QWidget

from ui.image_layout import (IMAGE_LAYOUT_CASCADE, IMAGE_LAYOUT_FAN,
                             normalize_image_layout)
from ui.resource_path import resource_path


WM_DRAWITEM = 0x002B
WM_MEASUREITEM = 0x002C
WM_NULL = 0x0000
ODT_MENU = 1
ODS_SELECTED = 0x0001
MF_OWNERDRAW = 0x0100
MF_DISABLED = 0x0002
MF_GRAYED = 0x0001
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
MIM_BACKGROUND = 0x00000002
MIM_STYLE = 0x00000010
MNS_NOCHECK = 0x80000000
DT_LEFT = 0x0000
DT_RIGHT = 0x0002
DT_VCENTER = 0x0004
DT_SINGLELINE = 0x0020
DT_END_ELLIPSIS = 0x00008000
DT_NOPREFIX = 0x00000800
TRANSPARENT = 1
PS_SOLID = 0
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
DI_NORMAL = 0x0003
EVENT_SYSTEM_MENUPOPUPSTART = 0x0006
WINEVENT_OUTOFCONTEXT = 0x0000
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

ID_LANGUAGE = 1
ID_FEEDBACK = 2
ID_HOLDING = 3
ID_IMAGE_LAYOUT = 4
ID_DIVIDER = 5
ID_QUIT = 6

WinEventProc = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
    wintypes.LONG, wintypes.DWORD, wintypes.DWORD)


class MeasureItemStruct(ctypes.Structure):
    _fields_ = [
        ('CtlType', wintypes.UINT),
        ('CtlID', wintypes.UINT),
        ('itemID', wintypes.UINT),
        ('itemWidth', wintypes.UINT),
        ('itemHeight', wintypes.UINT),
        ('itemData', ctypes.c_size_t),
    ]


class DrawItemStruct(ctypes.Structure):
    _fields_ = [
        ('CtlType', wintypes.UINT),
        ('CtlID', wintypes.UINT),
        ('itemID', wintypes.UINT),
        ('itemAction', wintypes.UINT),
        ('itemState', wintypes.UINT),
        ('hwndItem', wintypes.HWND),
        ('hDC', wintypes.HDC),
        ('rcItem', wintypes.RECT),
        ('itemData', ctypes.c_size_t),
    ]


class MenuInfo(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('fMask', wintypes.DWORD),
        ('dwStyle', wintypes.DWORD),
        ('cyMax', wintypes.UINT),
        ('hbrBack', wintypes.HBRUSH),
        ('dwContextHelpID', wintypes.DWORD),
        ('dwMenuData', ctypes.c_size_t),
    ]


class MonitorInfo(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('rcMonitor', wintypes.RECT),
        ('rcWork', wintypes.RECT),
        ('dwFlags', wintypes.DWORD),
    ]


def _colorref(hex_color):
    value = hex_color.lstrip('#')
    red, green, blue = (int(value[index:index + 2], 16)
                        for index in (0, 2, 4))
    return red | (green << 8) | (blue << 16)


class WindowsNativeTrayMenu(QWidget):
    """Native HMENU behaviour with owner-drawn Dose Ctrl+C visuals."""

    feedback_toggled = Signal(bool)
    holding_toggled = Signal(bool)
    language_toggled = Signal(str)
    image_layout_changed = Signal(str)
    quit_requested = Signal()

    _TEXT = {
        'zh': {
            'feedback': '显示复制反馈',
            'holding': '等待 Ctrl+V 后收起',
            'quit': '退出',
        },
        'en': {
            'feedback': 'Show copy feedback',
            'holding': 'Dismiss on Ctrl+V',
            'quit': 'Quit',
        },
    }
    _HEIGHTS = {
        ID_LANGUAGE: 24,
        ID_FEEDBACK: 22,
        ID_HOLDING: 22,
        ID_IMAGE_LAYOUT: 28,
        ID_DIVIDER: 5,
        ID_QUIT: 24,
    }

    def __init__(self, language='zh', parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_NativeWindow)
        self.resize(1, 1)
        self.move(-32000, -32000)
        self._language = language if language in self._TEXT else 'zh'
        self._feedback_enabled = True
        self._holding_enabled = False
        self._image_layout_mode = IMAGE_LAYOUT_FAN
        self._menu_open = False
        self._dpi = 96
        self._normal_font = None
        self._title_font = None
        self._menu_window_hook = None
        self._menu_window_callback = None
        self._layout_icons = []
        self._configure_win32()

    def _configure_win32(self):
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self._user32.CreatePopupMenu.restype = wintypes.HMENU
        self._user32.CreatePopupMenu.argtypes = []
        self._user32.AppendMenuW.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_size_t,
            wintypes.LPCWSTR]
        self._user32.SetMenuInfo.argtypes = [
            wintypes.HMENU, ctypes.POINTER(MenuInfo)]
        self._user32.DestroyMenu.argtypes = [wintypes.HMENU]
        self._user32.TrackPopupMenuEx.restype = wintypes.UINT
        self._user32.TrackPopupMenuEx.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, ctypes.c_void_p]
        self._user32.GetDpiForWindow.restype = wintypes.UINT
        self._user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        self._user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        self._user32.MonitorFromPoint.restype = wintypes.HMONITOR
        self._user32.MonitorFromPoint.argtypes = [
            wintypes.POINT, wintypes.DWORD]
        self._user32.GetMonitorInfoW.argtypes = [
            wintypes.HMONITOR, ctypes.c_void_p]
        self._user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self._user32.PostMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self._user32.EndMenu.argtypes = []
        self._user32.SetWinEventHook.restype = wintypes.HANDLE
        self._user32.SetWinEventHook.argtypes = [
            wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE,
            WinEventProc, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        self._user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        self._user32.GetClassNameW.argtypes = [
            wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self._user32.GetWindowRect.argtypes = [
            wintypes.HWND, ctypes.c_void_p]
        self._user32.SetWindowRgn.argtypes = [
            wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
        self._user32.FillRect.argtypes = [
            wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
        self._user32.DrawTextW.argtypes = [
            wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
            ctypes.POINTER(wintypes.RECT), wintypes.UINT]
        self._user32.LoadImageW.restype = wintypes.HANDLE
        self._user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self._user32.DrawIconEx.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON,
            ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HBRUSH,
            wintypes.UINT]
        self._user32.DestroyIcon.argtypes = [wintypes.HICON]

        self._gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
        self._gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
        self._gdi32.CreatePen.restype = wintypes.HPEN
        self._gdi32.CreatePen.argtypes = [
            ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
        self._gdi32.CreateFontW.restype = wintypes.HFONT
        self._gdi32.CreateFontW.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
            wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
            wintypes.DWORD, wintypes.LPCWSTR]
        self._gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self._gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self._gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self._gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
        self._gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
        self._gdi32.RoundRect.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self._gdi32.Ellipse.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int]
        self._gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
        self._gdi32.CreateRoundRectRgn.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int]

        try:
            self._dwmapi = ctypes.windll.dwmapi
            self._dwmapi.DwmSetWindowAttribute.argtypes = [
                wintypes.HWND, wintypes.DWORD, ctypes.c_void_p,
                wintypes.DWORD]
        except (AttributeError, OSError):
            self._dwmapi = None

    @property
    def language(self):
        return self._language

    @property
    def feedback_enabled(self):
        return self._feedback_enabled

    @property
    def holding_enabled(self):
        return self._holding_enabled

    def set_language(self, language):
        self._language = language if language in self._TEXT else 'zh'

    def set_state(self, feedback_enabled, holding_enabled,
                  image_layout_mode='fan'):
        self._feedback_enabled = bool(feedback_enabled)
        self._holding_enabled = bool(holding_enabled)
        self._image_layout_mode = normalize_image_layout(image_layout_mode)

    def isVisible(self):
        return self._menu_open

    def hide(self):
        if self._menu_open:
            self._user32.EndMenu()
        else:
            super().hide()

    def show_near_tray(self, tray_icon):
        """Enter the Win32 modal popup-menu loop at the current tray icon."""
        if self._menu_open:
            return
        self.show()
        QApplication.processEvents()
        hwnd = wintypes.HWND(int(self.winId()))
        self._dpi = int(self._user32.GetDpiForWindow(hwnd) or 96)
        self._create_fonts()
        self._load_layout_icons()
        menu, background_brush = self._create_menu()
        if not menu:
            self._delete_fonts()
            self._delete_layout_icons()
            super().hide()
            return

        position = self._menu_position()
        self._menu_open = True
        try:
            self._user32.SetForegroundWindow(hwnd)
            self._install_menu_window_hook()
            command = ID_LANGUAGE
            while command in (ID_LANGUAGE, ID_IMAGE_LAYOUT):
                command = int(self._user32.TrackPopupMenuEx(
                    menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                    position.x, position.y, hwnd, None) or 0)
                if command in (ID_LANGUAGE, ID_IMAGE_LAYOUT):
                    # A native HMENU ends its loop when an item is chosen.
                    # Apply the language synchronously and immediately enter
                    # the same menu at the same anchor, which refreshes every
                    # visible label without requiring a second tray click.
                    self._apply_command(command)
            self._user32.PostMessageW(hwnd, WM_NULL, 0, 0)
        finally:
            self._remove_menu_window_hook()
            self._menu_open = False
            self._user32.DestroyMenu(menu)
            self._gdi32.DeleteObject(background_brush)
            self._delete_fonts()
            self._delete_layout_icons()
            super().hide()
        self._apply_command(int(command or 0))

    def _install_menu_window_hook(self):
        """Round only this UI thread's transient native menu window."""
        self._menu_window_callback = WinEventProc(self._on_menu_popup_start)
        thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self._menu_window_hook = self._user32.SetWinEventHook(
            EVENT_SYSTEM_MENUPOPUPSTART, EVENT_SYSTEM_MENUPOPUPSTART,
            None, self._menu_window_callback, 0, thread_id,
            WINEVENT_OUTOFCONTEXT)

    def _remove_menu_window_hook(self):
        if self._menu_window_hook:
            self._user32.UnhookWinEvent(self._menu_window_hook)
        self._menu_window_hook = None
        self._menu_window_callback = None

    def _on_menu_popup_start(self, hook, event, window, object_id,
                             child_id, event_thread, event_time):
        """Apply the old panel's 8-DIP rounded silhouette to an HMENU."""
        try:
            class_name = ctypes.create_unicode_buffer(32)
            if (not window or
                    not self._user32.GetClassNameW(
                        window, class_name, len(class_name)) or
                    class_name.value != '#32768'):
                return

            if self._dwmapi is not None:
                preference = ctypes.c_int(DWMWCP_ROUND)
                self._dwmapi.DwmSetWindowAttribute(
                    window, DWMWA_WINDOW_CORNER_PREFERENCE,
                    ctypes.byref(preference), ctypes.sizeof(preference))

            rect = wintypes.RECT()
            if not self._user32.GetWindowRect(window, ctypes.byref(rect)):
                return
            width = max(1, rect.right - rect.left)
            height = max(1, rect.bottom - rect.top)
            diameter = self._px(20)
            region = self._gdi32.CreateRoundRectRgn(
                0, 0, width + 1, height + 1, diameter, diameter)
            if region and not self._user32.SetWindowRgn(window, region, True):
                self._gdi32.DeleteObject(region)
        except (AttributeError, ctypes.ArgumentError, OSError, TypeError,
                ValueError):
            # Styling must never interrupt the native menu loop.
            return

    def _create_menu(self):
        menu = self._user32.CreatePopupMenu()
        if not menu:
            return None, None
        background = self._gdi32.CreateSolidBrush(_colorref('#252525'))
        info = MenuInfo()
        info.cbSize = ctypes.sizeof(MenuInfo)
        info.fMask = MIM_BACKGROUND | MIM_STYLE
        info.dwStyle = MNS_NOCHECK
        info.hbrBack = background
        self._user32.SetMenuInfo(menu, ctypes.byref(info))
        for item_id in (ID_LANGUAGE, ID_FEEDBACK, ID_HOLDING, ID_IMAGE_LAYOUT,
                        ID_DIVIDER, ID_QUIT):
            flags = MF_OWNERDRAW
            if item_id == ID_DIVIDER:
                flags |= MF_DISABLED | MF_GRAYED
            self._user32.AppendMenuW(menu, flags, item_id, None)
        return menu, background

    def _menu_position(self):
        point = wintypes.POINT()
        self._user32.GetCursorPos(ctypes.byref(point))
        scale = self._dpi / 96.0
        width = round(210 * scale)
        height = round(sum(self._HEIGHTS.values()) * scale)
        x = point.x - width
        y = point.y - height

        monitor = self._user32.MonitorFromPoint(point, 2)
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if monitor and self._user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            x = max(info.rcWork.left + 6,
                    min(x, info.rcWork.right - width - 6))
            y = max(info.rcWork.top + 6,
                    min(y, info.rcWork.bottom - height - 6))
        return wintypes.POINT(x, y)

    def _apply_command(self, command):
        if command == ID_LANGUAGE:
            language = 'en' if self._language == 'zh' else 'zh'
            self.set_language(language)
            self.language_toggled.emit(language)
        elif command == ID_FEEDBACK:
            self._feedback_enabled = not self._feedback_enabled
            self.feedback_toggled.emit(self._feedback_enabled)
        elif command == ID_HOLDING:
            self._holding_enabled = not self._holding_enabled
            self.holding_toggled.emit(self._holding_enabled)
        elif command == ID_IMAGE_LAYOUT:
            self._image_layout_mode = (
                IMAGE_LAYOUT_CASCADE
                if self._image_layout_mode == IMAGE_LAYOUT_FAN
                else IMAGE_LAYOUT_FAN)
            self.image_layout_changed.emit(self._image_layout_mode)
        elif command == ID_QUIT:
            self.quit_requested.emit()

    def nativeEvent(self, event_type, message):
        try:
            msg = ctypes.cast(
                int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == WM_MEASUREITEM:
                measure = ctypes.cast(
                    msg.lParam, ctypes.POINTER(MeasureItemStruct)).contents
                if measure.CtlType == ODT_MENU:
                    self._measure_item(measure)
                    return True, 1
            elif msg.message == WM_DRAWITEM:
                draw = ctypes.cast(
                    msg.lParam, ctypes.POINTER(DrawItemStruct)).contents
                if draw.CtlType == ODT_MENU:
                    self._draw_item(draw)
                    return True, 1
        except (TypeError, ValueError, OSError):
            pass
        return super().nativeEvent(event_type, message)

    def _measure_item(self, measure):
        scale = self._dpi / 96.0
        measure.itemWidth = round(210 * scale)
        measure.itemHeight = round(
            self._HEIGHTS.get(measure.itemID, 24) * scale)

    def _draw_item(self, draw):
        hdc = draw.hDC
        rect = draw.rcItem
        selected = bool(draw.itemState & ODS_SELECTED)
        self._fill_rect(hdc, rect, '#3a3a3a' if selected else '#252525')
        if draw.itemID == ID_DIVIDER:
            y = (rect.top + rect.bottom) // 2
            line = wintypes.RECT(rect.left + self._px(10), y,
                                 rect.right - self._px(10), y + 1)
            self._fill_rect(hdc, line, '#414141')
            return
        if draw.itemID == ID_LANGUAGE:
            self._draw_text(hdc, 'Does Ctrl+C Work', rect, '#f2f2f2',
                            self._title_font, DT_LEFT, left=10, right=72)
            en_selected = self._language == 'en'
            self._draw_text(
                hdc, 'EN', rect, '#ffffff' if en_selected else '#8e8e8e',
                self._title_font if en_selected else self._normal_font,
                DT_RIGHT, left=130, right=38)
            self._draw_text(hdc, '/', rect, '#555555', self._normal_font,
                            DT_RIGHT, left=166, right=24)
            self._draw_text(
                hdc, '中', rect, '#ffffff' if not en_selected else '#8e8e8e',
                self._title_font if not en_selected else self._normal_font,
                DT_RIGHT, left=178, right=10)
            return

        text = self._TEXT[self._language]
        if draw.itemID == ID_FEEDBACK:
            self._draw_text(hdc, text['feedback'], rect, '#ececec',
                            self._normal_font, DT_LEFT, left=14, right=50)
            self._draw_switch(hdc, rect, self._feedback_enabled)
        elif draw.itemID == ID_HOLDING:
            self._draw_text(hdc, text['holding'], rect, '#ececec',
                            self._normal_font, DT_LEFT, left=14, right=50)
            self._draw_switch(hdc, rect, self._holding_enabled)
        elif draw.itemID == ID_IMAGE_LAYOUT:
            self._draw_image_layout_selector(hdc, rect)
        elif draw.itemID == ID_QUIT:
            self._draw_text(hdc, text['quit'], rect, '#ececec',
                             self._normal_font, DT_LEFT, left=14, right=10)

    def _draw_image_layout_selector(self, hdc, row):
        icon_size = self._px(18)
        cell_width = self._px(32)
        group_left = row.left + (row.right - row.left - cell_width * 2) // 2
        selected = (0 if self._image_layout_mode == IMAGE_LAYOUT_FAN else 1)
        for index in range(2):
            cell_left = group_left + index * cell_width
            if index == selected:
                underline = wintypes.RECT(
                    cell_left + self._px(6), row.bottom - self._px(3),
                    cell_left + cell_width - self._px(6), row.bottom - self._px(1))
                self._fill_rect(hdc, underline, '#facc15')
            if index >= len(self._layout_icons) or not self._layout_icons[index]:
                continue
            x = cell_left + (cell_width - icon_size) // 2
            y = row.top + (row.bottom - row.top - icon_size) // 2
            self._user32.DrawIconEx(
                hdc, x, y, self._layout_icons[index], icon_size, icon_size,
                0, None, DI_NORMAL)

    def _draw_switch(self, hdc, row, checked):
        width, height = self._px(28), self._px(16)
        left = row.right - self._px(12) - width
        top = row.top + (row.bottom - row.top - height) // 2
        track = wintypes.RECT(left, top, left + width, top + height)
        self._round_rect(hdc, track, '#facc15' if checked else '#4b4b4b',
                         height // 2)
        thumb = height - self._px(4)
        thumb_left = (track.right - thumb - self._px(2)
                      if checked else track.left + self._px(2))
        self._ellipse(hdc, wintypes.RECT(
            thumb_left, track.top + self._px(2), thumb_left + thumb,
            track.top + self._px(2) + thumb), '#f7f7f7')

    def _draw_text(self, hdc, text, row, color, font, alignment,
                   left, right):
        rect = wintypes.RECT(row.left + self._px(left), row.top,
                             row.right - self._px(right), row.bottom)
        old_font = self._gdi32.SelectObject(hdc, font)
        self._gdi32.SetBkMode(hdc, TRANSPARENT)
        self._gdi32.SetTextColor(hdc, _colorref(color))
        flags = (alignment | DT_VCENTER | DT_SINGLELINE |
                 DT_END_ELLIPSIS | DT_NOPREFIX)
        self._user32.DrawTextW(hdc, text, -1, ctypes.byref(rect), flags)
        self._gdi32.SelectObject(hdc, old_font)

    def _fill_rect(self, hdc, rect, color):
        brush = self._gdi32.CreateSolidBrush(_colorref(color))
        self._user32.FillRect(hdc, ctypes.byref(rect), brush)
        self._gdi32.DeleteObject(brush)

    def _round_rect(self, hdc, rect, color, radius):
        brush = self._gdi32.CreateSolidBrush(_colorref(color))
        pen = self._gdi32.CreatePen(PS_SOLID, 1, _colorref(color))
        old_brush = self._gdi32.SelectObject(hdc, brush)
        old_pen = self._gdi32.SelectObject(hdc, pen)
        self._gdi32.RoundRect(hdc, rect.left, rect.top, rect.right,
                              rect.bottom, radius, radius)
        self._gdi32.SelectObject(hdc, old_brush)
        self._gdi32.SelectObject(hdc, old_pen)
        self._gdi32.DeleteObject(brush)
        self._gdi32.DeleteObject(pen)

    def _ellipse(self, hdc, rect, color):
        brush = self._gdi32.CreateSolidBrush(_colorref(color))
        pen = self._gdi32.CreatePen(PS_SOLID, 1, _colorref(color))
        old_brush = self._gdi32.SelectObject(hdc, brush)
        old_pen = self._gdi32.SelectObject(hdc, pen)
        self._gdi32.Ellipse(hdc, rect.left, rect.top, rect.right, rect.bottom)
        self._gdi32.SelectObject(hdc, old_brush)
        self._gdi32.SelectObject(hdc, old_pen)
        self._gdi32.DeleteObject(brush)
        self._gdi32.DeleteObject(pen)

    def _create_fonts(self):
        self._normal_font = self._font(11, 400)
        self._title_font = self._font(11, 600)

    def _font(self, pixels, weight):
        return self._gdi32.CreateFontW(
            -self._px(pixels), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0,
            'Segoe UI')

    def _delete_fonts(self):
        for font in (self._normal_font, self._title_font):
            if font:
                self._gdi32.DeleteObject(font)
        self._normal_font = None
        self._title_font = None

    def _load_layout_icons(self):
        self._delete_layout_icons()
        size = self._px(18)
        for filename in ('fluent_image_multiple.ico',
                         'fluent_slide_multiple.ico'):
            handle = self._user32.LoadImageW(
                None, resource_path('assets', 'image_layout', filename),
                IMAGE_ICON, size, size, LR_LOADFROMFILE)
            self._layout_icons.append(handle)

    def _delete_layout_icons(self):
        for handle in self._layout_icons:
            if handle:
                self._user32.DestroyIcon(handle)
        self._layout_icons = []

    def _px(self, value):
        return max(1, round(value * self._dpi / 96.0))
