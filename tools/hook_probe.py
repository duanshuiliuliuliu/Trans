"""鼠标钩子探针（排障用）：打印本机鼠标输入被钩子收到的情况。

用途：确认「划选文字时 Trans 能不能收到事件」，以及你的鼠标输入是否带
Windows 的“注入（injected）”标记——带该标记的输入以前会被程序过滤掉。

用法：python tools/hook_probe.py [监听秒数，默认 30]
期间用鼠标划选或双击一段文字，然后看输出统计。该脚本不联网、不改配置。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
import time
from ctypes import POINTER, byref

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from app import native

NAMES = {
    native.WM_LBUTTONDOWN: "左键按下",
    native.WM_LBUTTONUP: "左键抬起",
    native.WM_LBUTTONDBLCLK: "左键双击",
}


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    native.enable_dpi_awareness()
    print(f"安装鼠标钩子，{seconds:.0f} 秒内请用鼠标划选（按住左键拖动）或双击一段文字…")
    print("（本脚本只监听、不做任何复制或翻译）")

    stats = {"drag": 0, "click": 0, "injected": 0, "plain": 0}

    def on_raw(message: int, x: int, y: int, injected: bool) -> None:
        stats["injected" if injected else "plain"] += 1
        print(
            f"  {NAMES[message]} @ ({x},{y}) 注入标记={'是' if injected else '否'}"
        )

    def on_select(x: int, y: int, kind: str) -> None:
        stats[kind] = stats.get(kind, 0) + 1
        print(f"  → 识别为{'双击选词' if kind == 'click' else '划选'}，结束位置 ({x},{y})")

    hook = native.MouseHook(on_select=on_select, on_raw=on_raw)
    if not hook.start():
        print("FAIL 钩子安装失败")
        return 1

    message = native.MSG()
    deadline = time.time() + seconds
    try:
        while time.time() < deadline:
            while native._peek_message(byref(message), None, 0, 0, native.PM_REMOVE):
                native._translate_message(byref(message))
                native._dispatch_message(byref(message))
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        hook.stop()

    print()
    print(f"共识别：划选 {stats['drag']} 次，双击选词 {stats['click']} 次")
    print(f"鼠标消息：带注入标记 {stats['injected']} 条，普通 {stats['plain']} 条")
    if stats["plain"] == 0 and stats["injected"] > 0:
        print("说明：你的鼠标输入全部带注入标记（触摸板驱动、远程桌面或鼠标增强软件），")
        print("      旧版本程序会因此忽略它们；当前版本已不再过滤，可以正常取词。")
    elif stats["drag"] + stats["click"] == 0:
        print("说明：没有识别到划选动作。若确实划选了文字，请把上面的输出发给我。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
