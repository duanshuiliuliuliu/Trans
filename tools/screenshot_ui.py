"""开发用：把设置窗口与结果弹窗渲染出来并截图为 PNG，便于核对排版。

依赖 Pillow（仅开发期需要）。
用法：python tools/screenshot_ui.py [输出目录]
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
import time
import tkinter as tk
from ctypes import POINTER, byref

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from app import native
from app.config import Config
from app.ui_popup import Popup
from app.ui_settings import SettingsWindow

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def capture(hwnd: int, path: str) -> None:
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    window_dc = user32.GetWindowDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    user32.PrintWindow(hwnd, mem_dc, 2)  # PW_RENDERFULLCONTENT
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, byref(info), 0)
    image = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1)
    image.convert("RGB").save(path)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, window_dc)
    print(f"已保存 {path} ({width}x{height})")


def settle(root: tk.Misc, rounds: int = 12) -> None:
    for _ in range(rounds):
        root.update()
        time.sleep(0.05)


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TEMP", ".")
    os.makedirs(out_dir, exist_ok=True)
    native.enable_dpi_awareness()

    root = tk.Tk()
    root.withdraw()
    try:
        scale = native.system_dpi() / 96.0
        root.tk.call("tk", "scaling", 96.0 * scale / 72.0)

        config = Config.load(os.path.join(out_dir, "trans-screenshot-config.json"))
        settings = SettingsWindow(root, config, lambda: None)
        settings.show()
        settle(root)
        notebook = settings.window.nametowidget(settings.window.winfo_children()[0])
        for index, name in enumerate(("settings-模型", "settings-规则", "settings-通用")):
            notebook.select(index)
            settle(root, 6)
            capture(int(settings.window.wm_frame(), 16), os.path.join(out_dir, f"{name}.png"))
        settings.destroy()

        popup = Popup(root, config)
        popup.show_result(
            "Measurements of the transverse momentum imbalance in proton-lead collisions",
            "在质子-铅碰撞中对横动量不平衡的测量结果，该观测量为理解核子内部的部分子分布提供了新的约束，"
            "也为后续的核子结构研究给出了更严格的实验依据。",
            "英语 → 中文 · deepseek-chat · 1.4s",
            120,
            120,
        )
        settle(root, 6)
        capture(int(popup.window.wm_frame(), 16), os.path.join(out_dir, "popup-结果.png"))
        popup.hide()

        popup.show_pending(120, 120, "英语 → 中文")
        settle(root, 6)
        capture(int(popup.window.wm_frame(), 16), os.path.join(out_dir, "popup-翻译中.png"))
        popup.hide()

        popup.show_error("接口返回 401：Authentication Fails, Your api key is invalid", 120, 120)
        settle(root, 6)
        capture(int(popup.window.wm_frame(), 16), os.path.join(out_dir, "popup-错误.png"))
        popup.hide()
    finally:
        root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
