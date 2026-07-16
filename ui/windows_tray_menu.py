"""Owner-drawn Win32 tray menu with a real native popup-menu loop."""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QColorDialog, QWidget

from ui.image_layout import (IMAGE_LAYOUT_CASCADE, IMAGE_LAYOUT_FAN,
                             normalize_image_layout)
from ui.theme import tray_colors


WM_DRAWITEM = 0x002B
WM_MEASUREITEM = 0x002C
WM_NULL = 0x0000
ODT_MENU = 1
ODS_SELECTED = 0x0001
MF_OWNERDRAW = 0x0100
MF_POPUP = 0x0010
MF_DISABLED = 0x0002
MF_GRAYED = 0x0001
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NOANIMATION = 0x4000
MIM_BACKGROUND = 0x00000002
MIM_STYLE = 0x00000010
MNS_NOCHECK = 0x80000000
MIIM_DATA = 0x00000020
MIIM_ID = 0x00000002
DT_LEFT = 0x0000
DT_RIGHT = 0x0002
DT_VCENTER = 0x0004
DT_SINGLELINE = 0x0020
DT_END_ELLIPSIS = 0x00008000
DT_NOPREFIX = 0x00000800
TRANSPARENT = 1
PS_SOLID = 0
EVENT_SYSTEM_MENUPOPUPSTART = 0x0006
WINEVENT_OUTOFCONTEXT = 0x0000
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

ID_LANGUAGE = 1
ID_FEEDBACK = 2
ID_HOLDING = 3
ID_IMAGE_LAYOUT = 4
ID_IMAGE_LAYOUT_FAN = 5
ID_IMAGE_LAYOUT_CASCADE = 6
ID_QUIT = 7
ID_BOTTOM_PADDING = 8
ID_PALETTE = 9
ID_PALETTE_CLASSIC = 10
ID_PALETTE_LIGHT = 11
ID_PALETTE_CUSTOM = 12
REOPEN_COMMANDS = (ID_LANGUAGE, ID_FEEDBACK, ID_HOLDING,
                   ID_IMAGE_LAYOUT_FAN, ID_IMAGE_LAYOUT_CASCADE,
                   ID_PALETTE_CLASSIC, ID_PALETTE_LIGHT)

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


class MenuItemInfo(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.UINT),
        ('fMask', wintypes.UINT),
        ('fType', wintypes.UINT),
        ('fState', wintypes.UINT),
        ('wID', wintypes.UINT),
        ('hSubMenu', wintypes.HMENU),
        ('hbmpChecked', wintypes.HANDLE),
        ('hbmpUnchecked', wintypes.HANDLE),
        ('dwItemData', ctypes.c_size_t),
        ('dwTypeData', wintypes.LPWSTR),
        ('cch', wintypes.UINT),
        ('hbmpItem', wintypes.HANDLE),
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
    palette_changed = Signal(str, str)
    quit_requested = Signal()

    _TEXT = {
        'zh': {
            'feedback': '显示复制反馈',
            'holding': '等待 Ctrl+V 后收起',
            'layout': '图片布局',
            'quit': '退出',
        },
        'en': {
            'feedback': 'Show copy feedback',
            'holding': 'Dismiss on Ctrl+V',
            'layout': 'Image layout',
            'quit': 'Quit',
        },
    }
    _HEIGHTS = {
        ID_LANGUAGE: 23,
        ID_FEEDBACK: 21,
        ID_HOLDING: 21,
        ID_IMAGE_LAYOUT: 26,
        ID_IMAGE_LAYOUT_FAN: 24,
        ID_IMAGE_LAYOUT_CASCADE: 24,
        ID_PALETTE: 26,
        ID_PALETTE_CLASSIC: 24,
        ID_PALETTE_LIGHT: 24,
        ID_PALETTE_CUSTOM: 24,
        ID_QUIT: 22,
        ID_BOTTOM_PADDING: 3,
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
        self._icon_font = None
        self._palette_name = 'classic'
        self._custom_color = '#52677f'
        self._configure_win32()

    def _configure_win32(self):
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self._user32.CreatePopupMenu.restype = wintypes.HMENU
        self._user32.CreatePopupMenu.argtypes = []
        self._user32.AppendMenuW.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_size_t,
            wintypes.LPCWSTR]
        self._user32.SetMenuItemInfoW.argtypes = [
            wintypes.HMENU, wintypes.UINT, wintypes.BOOL,
            ctypes.POINTER(MenuItemInfo)]
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

    def set_theme(self, light):
        """Colors are read at draw time; repaint on the next native popup."""
        self.update()

    def set_palette(self, palette, custom_color='#52677f'):
        self._palette_name = (palette if palette in ('classic', 'light', 'custom')
                              else 'classic')
        self._custom_color = custom_color or '#52677f'
        self.update()

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
        menu, background_brush = self._create_menu()
        if not menu:
            self._delete_fonts()
            super().hide()
            return

        position = self._menu_position()
        self._menu_open = True
        try:
            self._user32.SetForegroundWindow(hwnd)
            self._install_menu_window_hook()
            command = ID_LANGUAGE
            while command in REOPEN_COMMANDS:
                command = int(self._user32.TrackPopupMenuEx(
                    menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NOANIMATION,
                    position.x, position.y, hwnd, None) or 0)
                if command in REOPEN_COMMANDS:
                    # A native HMENU ends its loop when an item is chosen.
                    # Apply the state synchronously and immediately enter the
                    # same menu at the same anchor. TPM_NOANIMATION removes
                    # the open/close transition that otherwise reads as a
                    # visible flash for a simple switch click.
                    self._apply_command(command)
            self._user32.PostMessageW(hwnd, WM_NULL, 0, 0)
        finally:
            self._remove_menu_window_hook()
            self._menu_open = False
            self._user32.DestroyMenu(menu)
            self._gdi32.DeleteObject(background_brush)
            self._delete_fonts()
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
            diameter = self._px(16 if width <= self._px(140) else 20)
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
        colors = tray_colors()
        background = self._gdi32.CreateSolidBrush(_colorref(colors.surface))
        self._configure_menu_surface(menu, background)
        layout_menu = self._user32.CreatePopupMenu()
        palette_menu = self._user32.CreatePopupMenu()
        if not layout_menu or not palette_menu:
            if layout_menu:
                self._user32.DestroyMenu(layout_menu)
            if palette_menu:
                self._user32.DestroyMenu(palette_menu)
            self._user32.DestroyMenu(menu)
            self._gdi32.DeleteObject(background)
            return None, None
        self._configure_menu_surface(layout_menu, background)
        self._configure_menu_surface(palette_menu, background)
        self._user32.AppendMenuW(
            layout_menu, MF_OWNERDRAW, ID_IMAGE_LAYOUT_FAN, None)
        self._user32.AppendMenuW(
            layout_menu, MF_OWNERDRAW, ID_IMAGE_LAYOUT_CASCADE, None)
        for item_id in (ID_PALETTE_CLASSIC, ID_PALETTE_LIGHT,
                        ID_PALETTE_CUSTOM):
            self._user32.AppendMenuW(
                palette_menu, MF_OWNERDRAW, item_id, None)
        for item_id in (ID_LANGUAGE, ID_FEEDBACK, ID_HOLDING):
            self._user32.AppendMenuW(menu, MF_OWNERDRAW, item_id, None)
        self._user32.AppendMenuW(
            menu, MF_OWNERDRAW | MF_POPUP, int(layout_menu), None)
        self._set_item_data(menu, 3, ID_IMAGE_LAYOUT)
        self._user32.AppendMenuW(
            menu, MF_OWNERDRAW | MF_POPUP, int(palette_menu), None)
        self._set_item_data(menu, 4, ID_PALETTE)
        self._user32.AppendMenuW(menu, MF_OWNERDRAW, ID_QUIT, None)
        self._user32.AppendMenuW(
            menu, MF_OWNERDRAW | MF_DISABLED | MF_GRAYED, ID_BOTTOM_PADDING,
            None)
        return menu, background

    def _configure_menu_surface(self, menu, background):
        info = MenuInfo()
        info.cbSize = ctypes.sizeof(MenuInfo)
        info.fMask = MIM_BACKGROUND | MIM_STYLE
        info.dwStyle = MNS_NOCHECK
        info.hbrBack = background
        self._user32.SetMenuInfo(menu, ctypes.byref(info))

    def _set_item_data(self, menu, position, item_data):
        info = MenuItemInfo()
        info.cbSize = ctypes.sizeof(MenuItemInfo)
        info.fMask = MIIM_DATA | MIIM_ID
        info.wID = item_data
        info.dwItemData = item_data
        self._user32.SetMenuItemInfoW(menu, position, True, ctypes.byref(info))

    def _menu_position(self):
        point = wintypes.POINT()
        self._user32.GetCursorPos(ctypes.byref(point))
        scale = self._dpi / 96.0
        width = round(210 * scale)
        root_items = (ID_LANGUAGE, ID_FEEDBACK, ID_HOLDING,
                      ID_IMAGE_LAYOUT, ID_PALETTE, ID_QUIT, ID_BOTTOM_PADDING)
        height = round(sum(self._HEIGHTS[item_id] for item_id in root_items)
                       * scale)
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
        elif command in (ID_IMAGE_LAYOUT_FAN, ID_IMAGE_LAYOUT_CASCADE):
            self._image_layout_mode = (
                IMAGE_LAYOUT_FAN if command == ID_IMAGE_LAYOUT_FAN
                else IMAGE_LAYOUT_CASCADE)
            self.image_layout_changed.emit(self._image_layout_mode)
        elif command in (ID_PALETTE_CLASSIC, ID_PALETTE_LIGHT):
            self._palette_name = (
                'classic' if command == ID_PALETTE_CLASSIC else 'light')
            self.palette_changed.emit(self._palette_name, '')
        elif command == ID_PALETTE_CUSTOM:
            color = QColorDialog.getColor(
                QColor(self._custom_color), self,
                'Choose Dose Ctrl+C colour')
            if color.isValid():
                self._palette_name = 'custom'
                self._custom_color = color.name()
                self.palette_changed.emit('custom', self._custom_color)
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
        item_id = int(measure.itemData or measure.itemID)
        width = 116 if item_id in (
            ID_IMAGE_LAYOUT_FAN, ID_IMAGE_LAYOUT_CASCADE,
            ID_PALETTE_CLASSIC, ID_PALETTE_LIGHT, ID_PALETTE_CUSTOM) else 210
        measure.itemWidth = round(width * scale)
        measure.itemHeight = round(
            self._HEIGHTS.get(item_id, 24) * scale)

    def _draw_item(self, draw):
        hdc = draw.hDC
        rect = draw.rcItem
        item_id = int(draw.itemData or draw.itemID)
        colors = tray_colors()
        selected = bool(draw.itemState & ODS_SELECTED)
        self._fill_rect(hdc, rect, colors.hover if selected else colors.surface)
        if item_id == ID_BOTTOM_PADDING:
            return
        if item_id == ID_LANGUAGE:
            self._draw_text(hdc, 'Does Ctrl+C Work', rect, colors.title,
                            self._title_font, DT_LEFT, left=14, right=72)
            en_selected = self._language == 'en'
            self._draw_text(
                hdc, 'EN', rect, colors.title if en_selected else colors.muted,
                self._title_font if en_selected else self._normal_font,
                DT_RIGHT, left=130, right=38)
            self._draw_text(hdc, '/', rect, colors.separator, self._normal_font,
                            DT_RIGHT, left=166, right=24)
            self._draw_text(
                hdc, '中', rect, colors.title if not en_selected else colors.muted,
                self._title_font if not en_selected else self._normal_font,
                DT_RIGHT, left=178, right=10)
            return

        text = self._TEXT[self._language]
        if item_id == ID_FEEDBACK:
            self._draw_text(hdc, text['feedback'], rect, colors.text,
                            self._normal_font, DT_LEFT, left=14, right=50)
            self._draw_switch(hdc, rect, self._feedback_enabled)
        elif item_id == ID_HOLDING:
            self._draw_text(hdc, text['holding'], rect, colors.text,
                            self._normal_font, DT_LEFT, left=14, right=50)
            self._draw_switch(hdc, rect, self._holding_enabled)
        elif item_id == ID_IMAGE_LAYOUT:
            self._draw_image_layout_item(hdc, rect, text)
        elif item_id in (ID_IMAGE_LAYOUT_FAN, ID_IMAGE_LAYOUT_CASCADE):
            self._draw_image_layout_choice(hdc, rect, item_id)
        elif item_id == ID_PALETTE:
            self._draw_palette_item(hdc, rect)
        elif item_id in (ID_PALETTE_CLASSIC, ID_PALETTE_LIGHT,
                         ID_PALETTE_CUSTOM):
            self._draw_palette_choice(hdc, rect, item_id)
        elif item_id == ID_QUIT:
            self._draw_text(hdc, text['quit'], rect, colors.text,
                             self._normal_font, DT_LEFT, left=14, right=10)

    def _draw_image_layout_item(self, hdc, row, text):
        colors = tray_colors()
        # PhotoCollection is a Windows Fluent system glyph. Drawing it as
        # text lets the same source follow the current menu foreground.
        self._draw_text(hdc, '\ue7aa', row, colors.title, self._icon_font,
                        DT_LEFT, left=13, right=180)
        self._draw_text(hdc, text['layout'], row, colors.text,
                        self._normal_font, DT_LEFT, left=38, right=76)
        value = ('扇形' if self._language == 'zh' else 'Fan')
        if self._image_layout_mode == IMAGE_LAYOUT_CASCADE:
            value = '层叠' if self._language == 'zh' else 'Cascade'
        self._draw_text(hdc, value, row, colors.muted, self._normal_font,
                        DT_RIGHT, left=118, right=24)

    def _draw_image_layout_choice(self, hdc, row, item_id):
        colors = tray_colors()
        mode = (IMAGE_LAYOUT_FAN if item_id == ID_IMAGE_LAYOUT_FAN
                else IMAGE_LAYOUT_CASCADE)
        label = ('扇形' if mode == IMAGE_LAYOUT_FAN else '层叠')
        if self._language == 'en':
            label = 'Fan' if mode == IMAGE_LAYOUT_FAN else 'Cascade'
        active = mode == self._image_layout_mode
        self._draw_text(hdc, label, row,
                        colors.title if active else colors.text,
                        self._title_font if active else self._normal_font,
                        DT_LEFT, left=12, right=28)
        if active:
            self._draw_text(hdc, '•', row, colors.title, self._title_font,
                            DT_RIGHT, left=82, right=12)

    def _draw_switch(self, hdc, row, checked):
        width, height = self._px(28), self._px(16)
        left = row.right - self._px(12) - width
        top = row.top + (row.bottom - row.top - height) // 2
        track = wintypes.RECT(left, top, left + width, top + height)
        colors = tray_colors()
        self._round_rect(hdc, track,
                         '#facc15' if checked else colors.switch_off,
                         height // 2)
        thumb = height - self._px(4)
        thumb_left = (track.right - thumb - self._px(2)
                      if checked else track.left + self._px(2))
        self._ellipse(hdc, wintypes.RECT(
            thumb_left, track.top + self._px(2), thumb_left + thumb,
            track.top + self._px(2) + thumb), colors.switch_thumb)

    def _draw_palette_item(self, hdc, row):
        colors = tray_colors()
        label = 'Colour' if self._language == 'en' else '配色'
        values = {
            'classic': 'Classic' if self._language == 'en' else '经典',
            'light': 'Light' if self._language == 'en' else '浅色',
            'custom': 'Custom' if self._language == 'en' else '自定义',
        }
        self._draw_text(hdc, label, row, colors.text, self._normal_font,
                        DT_LEFT, left=14, right=82)
        self._draw_text(hdc, values[self._palette_name], row, colors.muted,
                        self._normal_font, DT_RIGHT, left=112, right=24)

    def _draw_palette_choice(self, hdc, row, item_id):
        choices = {
            ID_PALETTE_CLASSIC: ('classic', 'Classic', '经典深色'),
            ID_PALETTE_LIGHT: ('light', 'Light glass', '浅色玻璃'),
            ID_PALETTE_CUSTOM: ('custom', 'Custom...', '自定义...'),
        }
        palette, en, zh = choices[item_id]
        active = palette == self._palette_name
        colors = tray_colors()
        self._draw_text(hdc, en if self._language == 'en' else zh, row,
                        colors.title if active else colors.text,
                        self._title_font if active else self._normal_font,
                        DT_LEFT, left=12, right=28)
        if active:
            self._draw_text(hdc, '*', row, colors.title, self._title_font,
                            DT_RIGHT, left=82, right=12)

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
        self._icon_font = self._font(15, 400, 'Segoe Fluent Icons')

    def _font(self, pixels, weight, face='Segoe UI'):
        return self._gdi32.CreateFontW(
            -self._px(pixels), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0,
            face)

    def _delete_fonts(self):
        for font in (self._normal_font, self._title_font, self._icon_font):
            if font:
                self._gdi32.DeleteObject(font)
        self._normal_font = None
        self._title_font = None
        self._icon_font = None

    def _px(self, value):
        return max(1, round(value * self._dpi / 96.0))
