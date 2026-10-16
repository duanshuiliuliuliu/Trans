"""Win32 原生能力封装：隐藏窗口与消息泵、托盘图标、全局热键、鼠标钩子、
剪贴板读写与快照、按键模拟、窗口样式调整、DPAPI 加解密。

全部通过 ctypes 直接调用系统 API，不依赖第三方库。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
import time
from ctypes import POINTER, Structure, Union, byref, sizeof
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# ----------------------------------------------------------------- 基础类型

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
HANDLE = wt.HANDLE
HWND = wt.HWND
HMENU = wt.HANDLE
HICON = wt.HANDLE
HINSTANCE = wt.HANDLE
HGLOBAL = wt.HANDLE

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

# ----------------------------------------------------------------- 常量

WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_CONTEXTMENU = 0x007B
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_HOTKEY = 0x0312
WM_APP = 0x8000

PM_REMOVE = 0x0001
HWND_BROADCAST = 0xFFFF

WS_POPUP = 0x80000000
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001
IDC_ARROW = 32512

MF_STRING = 0x0000
MF_GRAYED = 0x0001
MF_DISABLED = 0x0002
MF_CHECKED = 0x0008
MF_SEPARATOR = 0x0800

TPM_LEFTALIGN = 0x0000
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
SM_CXSMICON = 49
SM_CYSMICON = 50

WH_MOUSE_LL = 14
HC_ACTION = 0
LLMHF_INJECTED = 0x00000001

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

CF_TEXT = 1
CF_OEMTEXT = 7
CF_UNICODETEXT = 13
CF_LOCALE = 16
GMEM_MOVEABLE = 0x0002

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_C = 0x43

SPI_GETWORKAREA = 0x0030
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
LOGPIXELSX = 88

ERROR_ALREADY_EXISTS = 183


# ----------------------------------------------------------------- 结构体


class POINT(Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]


class RECT(Structure):
    _fields_ = [
        ("left", wt.LONG),
        ("top", wt.LONG),
        ("right", wt.LONG),
        ("bottom", wt.LONG),
    ]


class MSG(Structure):
    _fields_ = [
        ("hwnd", HWND),
        ("message", wt.UINT),
        ("wParam", wt.WPARAM),
        ("lParam", wt.LPARAM),
        ("time", wt.DWORD),
        ("pt", POINT),
        ("lPrivate", wt.DWORD),
    ]


WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)


class WNDCLASSW(Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", HINSTANCE),
        ("hIcon", HICON),
        ("hCursor", HANDLE),
        ("hbrBackground", HANDLE),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


class NOTIFYICONDATAW(Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", HWND),
        ("uID", wt.UINT),
        ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.UINT),
        ("hIcon", HICON),
        ("szTip", wt.WCHAR * 128),
        ("dwState", wt.DWORD),
        ("dwStateMask", wt.DWORD),
        ("szInfo", wt.WCHAR * 256),
        ("uVersion", wt.UINT),
        ("szInfoTitle", wt.WCHAR * 64),
        ("dwInfoFlags", wt.DWORD),
    ]


class MSLLHOOKSTRUCT(Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(Structure):
    _fields_ = [
        ("dx", wt.LONG),
        ("dy", wt.LONG),
        ("mouseData", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(Structure):
    _fields_ = [
        ("uMsg", wt.DWORD),
        ("wParamL", wt.WORD),
        ("wParamH", wt.WORD),
    ]


class _INPUTUNION(Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


class DATA_BLOB(Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", POINTER(ctypes.c_char))]


# ----------------------------------------------------------------- 函数签名

_SIG = {
    # user32
    "RegisterClassW": (wt.ATOM, [POINTER(WNDCLASSW)]),
    "UnregisterClassW": (wt.BOOL, [wt.LPCWSTR, HINSTANCE]),
    "CreateWindowExW": (
        HWND,
        [
            wt.DWORD,
            wt.LPCWSTR,
            wt.LPCWSTR,
            wt.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            HWND,
            HMENU,
            HINSTANCE,
            ctypes.c_void_p,
        ],
    ),
    "DestroyWindow": (wt.BOOL, [HWND]),
    "DefWindowProcW": (LRESULT, [HWND, wt.UINT, wt.WPARAM, wt.LPARAM]),
    "PeekMessageW": (
        wt.BOOL,
        [POINTER(MSG), HWND, wt.UINT, wt.UINT, wt.UINT],
    ),
    "TranslateMessage": (wt.BOOL, [POINTER(MSG)]),
    "DispatchMessageW": (LRESULT, [POINTER(MSG)]),
    "PostMessageW": (wt.BOOL, [HWND, wt.UINT, wt.WPARAM, wt.LPARAM]),
    "RegisterWindowMessageW": (wt.UINT, [wt.LPCWSTR]),
    "RegisterHotKey": (wt.BOOL, [HWND, ctypes.c_int, wt.UINT, wt.UINT]),
    "UnregisterHotKey": (wt.BOOL, [HWND, ctypes.c_int]),
    "SendInput": (wt.UINT, [wt.UINT, POINTER(INPUT), ctypes.c_int]),
    "SetWindowsHookExW": (HANDLE, [ctypes.c_int, HOOKPROC, HINSTANCE, wt.DWORD]),
    "UnhookWindowsHookEx": (wt.BOOL, [HANDLE]),
    "CallNextHookEx": (LRESULT, [HANDLE, ctypes.c_int, wt.WPARAM, wt.LPARAM]),
    "GetCursorPos": (wt.BOOL, [POINTER(POINT)]),
    "WindowFromPoint": (HWND, [POINT]),
    "GetForegroundWindow": (HWND, []),
    "GetWindowThreadProcessId": (wt.DWORD, [HWND, POINTER(wt.DWORD)]),
    "SetForegroundWindow": (wt.BOOL, [HWND]),
    "GetSystemMetrics": (ctypes.c_int, [ctypes.c_int]),
    "LoadImageW": (
        HANDLE,
        [HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT],
    ),
    "DestroyIcon": (wt.BOOL, [HICON]),
    "CreatePopupMenu": (HMENU, []),
    "DestroyMenu": (wt.BOOL, [HMENU]),
    "AppendMenuW": (wt.BOOL, [HMENU, wt.UINT, ULONG_PTR, wt.LPCWSTR]),
    "TrackPopupMenu": (
        wt.BOOL,
        [HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, HWND, ctypes.c_void_p],
    ),
    "SystemParametersInfoW": (wt.BOOL, [wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT]),
    "SetProcessDPIAware": (wt.BOOL, []),
    "GetDpiForSystem": (wt.UINT, []),
    "SetWindowPos": (
        wt.BOOL,
        [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT],
    ),
    # shell32
    "Shell_NotifyIconW": (wt.BOOL, [wt.DWORD, POINTER(NOTIFYICONDATAW)]),
    # kernel32（剪贴板相关在 user32/kernel32 中均可，这里统一走 kernel32 的全局内存接口）
    "GetModuleHandleW": (HINSTANCE, [wt.LPCWSTR]),
    "CreateMutexW": (HANDLE, [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]),
    "GlobalAlloc": (HGLOBAL, [wt.UINT, ctypes.c_size_t]),
    "GlobalLock": (ctypes.c_void_p, [HGLOBAL]),
    "GlobalUnlock": (wt.BOOL, [HGLOBAL]),
    "LocalFree": (HANDLE, [HANDLE]),
    # gdi32
    "GetDeviceCaps": (ctypes.c_int, [HANDLE, ctypes.c_int]),
}

_LIB_OF = {
    "Shell_NotifyIconW": shell32,
}


def _bind(func_name: str, lib) -> Callable:
    if func_name not in _SIG:
        raise AttributeError(f"未定义签名：{func_name}")
    restype, argtypes = _SIG[func_name]
    fn = getattr(lib, func_name)
    fn.restype = restype
    fn.argtypes = argtypes
    return fn


OpenClipboard = user32.OpenClipboard
OpenClipboard.restype = wt.BOOL
OpenClipboard.argtypes = [HWND]
CloseClipboard = user32.CloseClipboard
CloseClipboard.restype = wt.BOOL
EmptyClipboard = user32.EmptyClipboard
EmptyClipboard.restype = wt.BOOL
GetClipboardData = user32.GetClipboardData
GetClipboardData.restype = HANDLE
GetClipboardData.argtypes = [wt.UINT]
SetClipboardData = user32.SetClipboardData
SetClipboardData.restype = HANDLE
SetClipboardData.argtypes = [wt.UINT, HANDLE]
IsClipboardFormatAvailable = user32.IsClipboardFormatAvailable
IsClipboardFormatAvailable.restype = wt.BOOL
IsClipboardFormatAvailable.argtypes = [wt.UINT]
EnumClipboardFormats = user32.EnumClipboardFormats
EnumClipboardFormats.restype = wt.UINT
EnumClipboardFormats.argtypes = [wt.UINT]
GetClipboardSequenceNumber = user32.GetClipboardSequenceNumber
GetClipboardSequenceNumber.restype = wt.DWORD
RegisterClipboardFormatW = user32.RegisterClipboardFormatW
RegisterClipboardFormatW.restype = wt.UINT
RegisterClipboardFormatW.argtypes = [wt.LPCWSTR]

if hasattr(user32, "GetWindowLongPtrW"):
    _get_wl = user32.GetWindowLongPtrW
    _set_wl = user32.SetWindowLongPtrW
else:  # 32 位
    _get_wl = user32.GetWindowLongW
    _set_wl = user32.SetWindowLongW
_get_wl.restype = LRESULT
_get_wl.argtypes = [HWND, ctypes.c_int]
_set_wl.restype = LRESULT
_set_wl.argtypes = [HWND, ctypes.c_int, LRESULT]

_register_class = _bind("RegisterClassW", user32)
_unregister_class = _bind("UnregisterClassW", user32)
_create_window = _bind("CreateWindowExW", user32)
_destroy_window = _bind("DestroyWindow", user32)
_def_window_proc = _bind("DefWindowProcW", user32)
_peek_message = _bind("PeekMessageW", user32)
_translate_message = _bind("TranslateMessage", user32)
_dispatch_message = _bind("DispatchMessageW", user32)
_post_message = _bind("PostMessageW", user32)
_register_window_message = _bind("RegisterWindowMessageW", user32)
_register_hotkey = _bind("RegisterHotKey", user32)
_unregister_hotkey = _bind("UnregisterHotKey", user32)
_send_input = _bind("SendInput", user32)
_set_windows_hook = _bind("SetWindowsHookExW", user32)
_unhook_windows_hook = _bind("UnhookWindowsHookEx", user32)
_call_next_hook = _bind("CallNextHookEx", user32)
_get_cursor_pos = _bind("GetCursorPos", user32)
_window_from_point = _bind("WindowFromPoint", user32)
_get_foreground_window = _bind("GetForegroundWindow", user32)
_get_window_thread_process_id = _bind("GetWindowThreadProcessId", user32)
_set_foreground_window = _bind("SetForegroundWindow", user32)
_get_system_metrics = _bind("GetSystemMetrics", user32)
_load_image = _bind("LoadImageW", user32)
_destroy_icon = _bind("DestroyIcon", user32)
_create_popup_menu = _bind("CreatePopupMenu", user32)
_destroy_menu = _bind("DestroyMenu", user32)
_append_menu = _bind("AppendMenuW", user32)
_track_popup_menu = _bind("TrackPopupMenu", user32)
_system_parameters_info = _bind("SystemParametersInfoW", user32)
_set_window_pos = _bind("SetWindowPos", user32)
_shell_notify_icon = _bind("Shell_NotifyIconW", shell32)
_get_module_handle = _bind("GetModuleHandleW", kernel32)
_create_mutex = _bind("CreateMutexW", kernel32)
_global_alloc = _bind("GlobalAlloc", kernel32)
_global_lock = _bind("GlobalLock", kernel32)
_global_unlock = _bind("GlobalUnlock", kernel32)
_local_free = _bind("LocalFree", kernel32)
_get_device_caps = _bind("GetDeviceCaps", gdi32)
_get_dc = user32.GetDC
_get_dc.restype = HANDLE
_get_dc.argtypes = [HWND]
_release_dc = user32.ReleaseDC
_release_dc.restype = ctypes.c_int
_release_dc.argtypes = [HWND, HANDLE]


# ----------------------------------------------------------------- 进程级设置


def enable_dpi_awareness() -> None:
    """启用 per-monitor v2 DPI 感知，失败时逐级降级。"""
    try:
        fn = user32.SetProcessDpiAwarenessContext
        fn.restype = wt.BOOL
        fn.argtypes = [ctypes.c_ssize_t]
        if fn(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            return
    except (AttributeError, OSError):
        pass
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        if shcore.SetProcessDpiAwareness(2) == 0:
            return
    except (AttributeError, OSError):
        pass
    try:
        _bind("SetProcessDPIAware", user32)()
    except Exception:
        pass


def system_dpi() -> int:
    """返回系统 DPI（96 为 100% 缩放）。"""
    try:
        fn = user32.GetDpiForSystem
        fn.restype = wt.UINT
        fn.argtypes = []
        dpi = fn()
        if dpi:
            return int(dpi)
    except (AttributeError, OSError):
        pass
    hdc = _get_dc(None)
    try:
        return int(_get_device_caps(hdc, LOGPIXELSX)) or 96
    finally:
        _release_dc(None, hdc)


def create_singleton_mutex(name: str) -> Tuple[HANDLE, bool]:
    """创建单实例互斥体，返回 (句柄, 是否已有实例)。"""
    handle = _create_mutex(None, False, name)
    already = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    return handle, already


def get_cursor_pos() -> Tuple[int, int]:
    pt = POINT()
    _get_cursor_pos(byref(pt))
    return int(pt.x), int(pt.y)


def get_work_area() -> Tuple[int, int, int, int]:
    rect = RECT()
    _system_parameters_info(SPI_GETWORKAREA, 0, byref(rect), 0)
    if rect.right <= rect.left or rect.bottom <= rect.top:
        return 0, 0, _get_system_metrics(0), _get_system_metrics(1)
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def window_pid(hwnd: int) -> int:
    pid = wt.DWORD()
    _get_window_thread_process_id(hwnd, byref(pid))
    return int(pid.value)


def window_from_point(x: int, y: int) -> int:
    return int(_window_from_point(POINT(int(x), int(y))) or 0)


_get_async_key_state = user32.GetAsyncKeyState
_get_async_key_state.restype = ctypes.c_short
_get_async_key_state.argtypes = [ctypes.c_int]


def ctrl_pressed() -> bool:
    """当前是否按着 Ctrl（用于“按住 Ctrl 划选才翻译”）。"""
    return bool(_get_async_key_state(VK_CONTROL) & 0x8000)


def set_no_activate(hwnd: int, no_activate: bool = True) -> None:
    """给窗口加上 WS_EX_NOACTIVATE / WS_EX_TOOLWINDOW，避免弹窗抢焦点。"""
    if not hwnd:
        return
    style = _get_wl(hwnd, GWL_EXSTYLE)
    style |= WS_EX_TOOLWINDOW
    if no_activate:
        style |= WS_EX_NOACTIVATE
    _set_wl(hwnd, GWL_EXSTYLE, style)
    _set_window_pos(
        hwnd, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
    )


def send_ctrl_c() -> bool:
    """模拟一次 Ctrl+C 复制。"""
    inputs = (INPUT * 4)()
    for index, (vk, up) in enumerate(
        ((VK_CONTROL, False), (VK_C, False), (VK_C, True), (VK_CONTROL, True))
    ):
        inputs[index].type = INPUT_KEYBOARD
        inputs[index].ki.wVk = vk
        inputs[index].ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    sent = _send_input(4, inputs, sizeof(INPUT))
    return sent == 4


# ----------------------------------------------------------------- 剪贴板

_SAFE_RESTORE_FORMATS = {CF_TEXT, CF_OEMTEXT, CF_UNICODETEXT, CF_LOCALE}
# 剪贴板是跨进程独占锁，可能被别的程序占住较长时间。
# 这些函数必须在工作线程里调用——在主线程里等待会拖慢整机鼠标（钩子由主线程服务）。
_CLIPBOARD_RETRY = 12


def _open_clipboard() -> bool:
    for _ in range(_CLIPBOARD_RETRY):
        if OpenClipboard(None):
            return True
        time.sleep(0.015)
    return False


def clipboard_formats() -> List[int]:
    if not _open_clipboard():
        return []
    try:
        formats: List[int] = []
        fmt = 0
        while True:
            fmt = EnumClipboardFormats(fmt)
            if not fmt:
                break
            formats.append(int(fmt))
        return formats
    finally:
        CloseClipboard()


def clipboard_get_text() -> Optional[str]:
    if not _open_clipboard():
        return None
    try:
        handle = GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = _global_lock(handle)
        if not ptr:
            return None
        try:
            return ctypes.c_wchar_p(ptr).value
        finally:
            _global_unlock(handle)
    finally:
        CloseClipboard()


def clipboard_set_text(text: str) -> bool:
    if not _open_clipboard():
        return False
    try:
        EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        handle = _global_alloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        ptr = _global_lock(handle)
        if not ptr:
            return False
        ctypes.memmove(ptr, data, len(data))
        _global_unlock(handle)
        if not SetClipboardData(CF_UNICODETEXT, handle):
            return False
        return True  # 所有权已转移给系统，无需再释放
    finally:
        CloseClipboard()


def clipboard_sequence_number() -> int:
    return int(GetClipboardSequenceNumber())


def clipboard_available() -> bool:
    """剪贴板当前能否打开；被别的程序独占时会返回 False。"""
    if _open_clipboard():
        CloseClipboard()
        return True
    return False


def clipboard_has_rich_content() -> bool:
    """剪贴板中含文本以外的格式（图片、文件、HTML 等）时返回 True。"""
    formats = clipboard_formats()
    if not formats:
        return False
    return any(fmt not in _SAFE_RESTORE_FORMATS for fmt in formats)


# ----------------------------------------------------------------- 菜单与图标


def show_popup_menu(
    owner_hwnd: int,
    items: Sequence[Tuple[int, str, bool, bool]],
    x: Optional[int] = None,
    y: Optional[int] = None,
) -> int:
    """弹出原生菜单，返回被点中的菜单项 id（未选择返回 0）。

    items 为 (id, 文本, 是否选中, 是否可用) 序列，文本为 '-' 表示分隔线。
    """
    menu = _create_popup_menu()
    if not menu:
        return 0
    try:
        for item_id, label, checked, enabled in items:
            if label == "-":
                _append_menu(menu, MF_SEPARATOR, 0, None)
                continue
            flags = MF_STRING
            if checked:
                flags |= MF_CHECKED
            if not enabled:
                flags |= MF_GRAYED
            _append_menu(menu, flags, item_id, label)
        if x is None or y is None:
            x, y = get_cursor_pos()
        _set_foreground_window(owner_hwnd)
        command = _track_popup_menu(
            menu, TPM_LEFTALIGN | TPM_RIGHTBUTTON | TPM_RETURNCMD, int(x), int(y), 0, owner_hwnd, None
        )
        _post_message(owner_hwnd, WM_NULL, 0, 0)
        return int(command)
    finally:
        _destroy_menu(menu)


def load_icon(path: str, size: Optional[int] = None) -> int:
    if not path or not os.path.isfile(path):
        return 0
    if size is None:
        size = _get_system_metrics(SM_CXSMICON) or 16
    return int(_load_image(None, path, IMAGE_ICON, size, size, LR_LOADFROMFILE) or 0)


def destroy_icon(handle: int) -> None:
    if handle:
        _destroy_icon(handle)


# ----------------------------------------------------------------- 隐藏窗口


class NativeWindow:
    """不可见的顶层窗口，用于接收托盘、热键、自定义注册消息，并按时泵消息。"""

    def __init__(self, class_name: str = "TransHiddenWnd", title: str = "Trans"):
        self.class_name = class_name
        self.title = title
        self.hwnd = 0
        self._handlers: Dict[int, List[Callable[[int, int], Optional[int]]]] = {}
        self._wndproc = WNDPROC(self._on_message)  # 必须持有引用，否则回调被回收
        self._msg = MSG()

    # --- 生命周期 ---------------------------------------------------
    def create(self) -> int:
        hinst = _get_module_handle(None)
        wc = WNDCLASSW()
        wc.style = CS_HREDRAW | CS_VREDRAW
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, IDC_ARROW)
        wc.lpszClassName = self.class_name
        atom = _register_class(byref(wc))
        if not atom and ctypes.get_last_error() != 1410:  # 1410 = 类已存在
            raise ctypes.WinError(ctypes.get_last_error())
        self.hwnd = int(
            _create_window(
                0, self.class_name, self.title, WS_POPUP, 0, 0, 0, 0, None, None, hinst, None
            )
            or 0
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        return self.hwnd

    def destroy(self) -> None:
        if self.hwnd:
            _destroy_window(self.hwnd)
            self.hwnd = 0
        _unregister_class(self.class_name, _get_module_handle(None))

    # --- 消息处理 ---------------------------------------------------
    def add_handler(self, message: int, handler: Callable[[int, int], Optional[int]]) -> None:
        self._handlers.setdefault(int(message), []).append(handler)

    def register_message(self, name: str) -> int:
        return int(_register_window_message(name))

    def post(self, message: int, wparam: int = 0, lparam: int = 0) -> None:
        if self.hwnd:
            _post_message(self.hwnd, message, wparam, lparam)

    def pump(self) -> None:
        """只处理本窗口的待处理消息，避免干扰 Tk 自己的消息泵。"""
        if not self.hwnd:
            return
        while _peek_message(byref(self._msg), self.hwnd, 0, 0, PM_REMOVE):
            _translate_message(byref(self._msg))
            _dispatch_message(byref(self._msg))

    def _on_message(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        for handler in self._handlers.get(int(message), ()):
            try:
                result = handler(int(wparam), int(lparam))
            except Exception:
                result = None
            if result is not None:
                return int(result)
        return int(_def_window_proc(hwnd, message, wparam, lparam))


# ----------------------------------------------------------------- 托盘图标


class TrayIcon:
    """Shell_NotifyIcon 托盘图标（旧版回调语义：lParam 为鼠标消息）。"""

    def __init__(
        self,
        hwnd: int,
        callback_message: int,
        tooltip: str,
        icon_path: str,
        icon_id: int = 1,
    ) -> None:
        self.hwnd = hwnd
        self.callback_message = callback_message
        self.icon_id = icon_id
        self.icon_path = icon_path
        self.tooltip = tooltip
        self.hicon = 0
        self._data = NOTIFYICONDATAW()
        self._data.cbSize = sizeof(NOTIFYICONDATAW)
        self._icon_cache: Dict[str, int] = {}  # 路径 -> 已加载的图标句柄，避免反复读盘

    def add(self) -> bool:
        handle = self._icon_cache.get(self.icon_path) or load_icon(self.icon_path)
        if handle:
            self._icon_cache[self.icon_path] = handle
            self.hicon = handle
        data = self._data
        data.hWnd = self.hwnd
        data.uID = self.icon_id
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = self.callback_message
        data.hIcon = self.hicon
        data.szTip = self.tooltip[:127]
        return bool(_shell_notify_icon(NIM_ADD, byref(data)))

    def remove(self) -> None:
        data = self._data
        data.hWnd = self.hwnd
        data.uID = self.icon_id
        _shell_notify_icon(NIM_DELETE, byref(data))
        for handle in self._icon_cache.values():
            destroy_icon(handle)
        self._icon_cache.clear()
        if self.hicon:
            destroy_icon(self.hicon)
            self.hicon = 0

    def update(self, icon_path: Optional[str] = None, tooltip: Optional[str] = None) -> None:
        """一次调用同时更新图标与提示文字。

        Shell_NotifyIcon 是同步调用，会等资源管理器响应；合并调用可以减少卡顿风险。
        图标句柄按路径缓存，切换状态时不再重新读盘。
        """
        flags = 0
        if icon_path and icon_path != self.icon_path:
            handle = self._icon_cache.get(icon_path)
            if not handle:
                handle = load_icon(icon_path)
                if handle:
                    self._icon_cache[icon_path] = handle
            if handle:
                self.icon_path = icon_path
                self.hicon = handle
                flags |= NIF_ICON
        if tooltip is not None and tooltip != self.tooltip:
            self.tooltip = tooltip
            flags |= NIF_TIP
        if not flags:
            return
        data = self._data
        data.hWnd = self.hwnd
        data.uID = self.icon_id
        data.uFlags = flags
        data.hIcon = self.hicon
        data.szTip = self.tooltip[:127]
        _shell_notify_icon(NIM_MODIFY, byref(data))

    def set_icon(self, icon_path: str) -> None:
        self.update(icon_path=icon_path)

    def set_tooltip(self, tooltip: str) -> None:
        self.update(tooltip=tooltip)

    def show_balloon(self, title: str, text: str) -> None:
        """弹出气泡提示（V2 结构的 NIF_INFO）。"""
        data = self._data
        data.hWnd = self.hwnd
        data.uID = self.icon_id
        data.uFlags = NIF_INFO
        data.szInfoTitle = title[:63]
        data.szInfo = text[:255]
        data.uVersion = 10000
        data.dwInfoFlags = NIIF_INFO
        _shell_notify_icon(NIM_MODIFY, byref(data))

# ----------------------------------------------------------------- 全局热键

HOTKEY_ID_DEFAULT = 0x5452

_KEY_NAMES = {chr(code): code for code in range(0x30, 0x3A)}  # 0-9
_KEY_NAMES.update({chr(code): code for code in range(0x41, 0x5B)})  # A-Z
_KEY_NAMES.update({f"F{i}": 0x6F + i for i in range(1, 13)})
_KEY_NAMES.update({"TAB": 0x09, "SPACE": 0x20, "ENTER": 0x0D, "ESC": 0x1B})
_KEY_NAMES.update({"`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
                   ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF})


def parse_hotkey(text: str) -> Optional[Tuple[int, int]]:
    """解析 "Ctrl+Alt+T" 形式的热键，返回 (修饰键, 虚拟键码)。"""
    if not text or not text.strip():
        return None
    mods = 0
    key = None
    for raw in text.replace("＋", "+").split("+"):
        token = raw.strip()
        if not token:
            continue
        upper = token.upper()
        if upper in ("CTRL", "CONTROL"):
            mods |= MOD_CONTROL
        elif upper in ("ALT", "MENU"):
            mods |= MOD_ALT
        elif upper == "SHIFT":
            mods |= MOD_SHIFT
        elif upper in ("WIN", "WINDOWS", "SUPER", "META"):
            mods |= MOD_WIN
        elif upper in _KEY_NAMES:
            if key is not None:
                return None
            key = _KEY_NAMES[upper]
        elif len(token) == 1:
            code = ctypes.windll.user32.VkKeyScanW(token)
            if code == -1:
                return None
            key = code & 0xFF
        else:
            return None
    if key is None or mods == 0:
        return None
    return mods | MOD_NOREPEAT, key


class HotkeyManager:
    def __init__(self, hwnd: int, hotkey_id: int = HOTKEY_ID_DEFAULT) -> None:
        self.hwnd = hwnd
        self.hotkey_id = hotkey_id
        self.current: Optional[str] = None

    def register(self, text: str) -> Tuple[bool, str]:
        parsed = parse_hotkey(text)
        if not parsed:
            return False, f"热键格式无效：{text}"
        self.unregister()
        mods, vk = parsed
        if not _register_hotkey(self.hwnd, self.hotkey_id, mods, vk):
            return False, f"热键被占用或注册失败：{text}"
        self.current = text
        return True, ""

    def unregister(self) -> None:
        if self.current:
            _unregister_hotkey(self.hwnd, self.hotkey_id)
            self.current = None


# ----------------------------------------------------------------- 鼠标钩子


class MouseHook:
    """低级鼠标钩子：只识别“按住左键拖动划选”这一个动作。

    回调里绝对不做耗时或 Tk 相关操作——钩子是在消息泵内部被系统同步调用的，
    一旦阻塞就会拖慢整机鼠标。
    """

    def __init__(
        self,
        on_select: Callable[[int, int, str], None],
        min_drag_px: int = 4,
        max_drag_seconds: float = 3.0,
        is_ignored_window: Optional[Callable[[int], bool]] = None,
        on_click: Optional[Callable[[int, int], None]] = None,
        on_raw: Optional[Callable[[int, int, int, bool], None]] = None,
        require_ctrl: bool = True,
        ctrl_check: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.on_select = on_select
        self.min_drag_px = int(min_drag_px)
        self.max_drag_seconds = float(max_drag_seconds)
        self.is_ignored_window = is_ignored_window
        self.on_click = on_click
        self.on_raw = on_raw
        self.require_ctrl = bool(require_ctrl)
        self.ctrl_check = ctrl_check or ctrl_pressed
        self.handle = 0
        self._proc = HOOKPROC(self._hook_proc)  # 保持引用
        # (x, y, 按下时刻, 是否跳过本次：自身窗口或不满足修饰键要求)
        self._down: Optional[Tuple[int, int, float, bool]] = None

    def start(self) -> bool:
        if self.handle:
            return True
        self.handle = int(_set_windows_hook(WH_MOUSE_LL, self._proc, _get_module_handle(None), 0) or 0)
        if not self.handle:
            self.handle = int(_set_windows_hook(WH_MOUSE_LL, self._proc, None, 0) or 0)
        return bool(self.handle)

    def stop(self) -> None:
        if self.handle:
            _unhook_windows_hook(self.handle)
            self.handle = 0
        self._down = None

    # --- 钩子回调（必须极快） ---------------------------------------
    def _hook_proc(self, code: int, wparam: int, lparam: int) -> int:
        try:
            if code == HC_ACTION:
                message = int(wparam)
                if message in (WM_LBUTTONDOWN, WM_LBUTTONUP):
                    data = ctypes.cast(lparam, POINTER(MSLLHOOKSTRUCT)).contents
                    x, y = int(data.pt.x), int(data.pt.y)
                    if self.on_raw is not None:
                        try:
                            self.on_raw(message, x, y, bool(data.flags & LLMHF_INJECTED))
                        except Exception:
                            pass
                    self._handle_mouse(message, x, y)
        except Exception:
            pass
        return int(_call_next_hook(None, code, wparam, lparam))

    def _handle_mouse(self, message: int, x: int, y: int) -> None:
        if message == WM_LBUTTONDOWN:
            if self.on_click is not None:
                try:
                    self.on_click(x, y)
                except Exception:
                    pass
            skip = not self._modifier_ok()
            if self.is_ignored_window is not None:
                try:
                    skip = skip or bool(self.is_ignored_window(window_from_point(x, y)))
                except Exception:
                    pass
            self._down = (x, y, time.monotonic(), skip)
            return
        if self._down is None:
            return
        start_x, start_y, start_time, skip = self._down
        self._down = None
        if skip:
            return
        distance = ((x - start_x) ** 2 + (y - start_y) ** 2) ** 0.5
        if distance < self.min_drag_px:
            return
        if time.monotonic() - start_time > self.max_drag_seconds:
            return
        self._emit(x, y, "drag")

    def _emit(self, x: int, y: int, kind: str) -> None:
        try:
            self.on_select(x, y, kind)
        except Exception:
            pass

    def _modifier_ok(self) -> bool:
        """需要按住 Ctrl 时，检查修饰键状态。"""
        return not self.require_ctrl or self.ctrl_check()


# ----------------------------------------------------------------- DPAPI


def _make_blob(data: bytes) -> Tuple[DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(bytes(data), len(data))
    blob = DATA_BLOB(len(data), ctypes.cast(buffer, POINTER(ctypes.c_char)))
    return blob, buffer


def dpapi_encrypt(text: str) -> Optional[bytes]:
    if not text:
        return b""
    try:
        blob_in, _buf = _make_blob(text.encode("utf-8"))
        blob_out = DATA_BLOB()
        crypt32.CryptProtectData.restype = wt.BOOL
        crypt32.CryptProtectData.argtypes = [
            POINTER(DATA_BLOB),
            wt.LPCWSTR,
            POINTER(DATA_BLOB),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wt.DWORD,
            POINTER(DATA_BLOB),
        ]
        if not crypt32.CryptProtectData(
            byref(blob_in), None, None, None, None, 0x1, byref(blob_out)
        ):
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            _local_free(blob_out.pbData)
    except Exception:
        return None


def dpapi_decrypt(data: bytes) -> Optional[str]:
    if not data:
        return ""
    try:
        blob_in, _buf = _make_blob(data)
        blob_out = DATA_BLOB()
        crypt32.CryptUnprotectData.restype = wt.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            POINTER(DATA_BLOB),
            ctypes.c_void_p,
            POINTER(DATA_BLOB),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wt.DWORD,
            POINTER(DATA_BLOB),
        ]
        if not crypt32.CryptUnprotectData(
            byref(blob_in), None, None, None, None, 0x1, byref(blob_out)
        ):
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8")
        finally:
            _local_free(blob_out.pbData)
    except Exception:
        return None


def is_windows() -> bool:
    return sys.platform.startswith("win")


def broadcast_message(message: int) -> None:
    """向所有顶层窗口广播自定义注册消息。"""
    _post_message(HWND_BROADCAST, message, 0, 0)
