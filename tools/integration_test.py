"""端到端集成自检：用真实配置启动程序本体，走完整的
配置 → 语言判断 → 规则匹配 → 接口调用 → 弹窗渲染 链路。

需要配置里已有可用的 API Key，否则直接跳过（退出码 0）。
过程中会短暂注册托盘图标与鼠标钩子。

用法：python tools/integration_test.py
"""
from __future__ import annotations

import importlib.machinery
import os
import sys
import tempfile
import time
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from app import native
from app import config as config_module
from app.config import Config

# 自检会产生“热键被占用”等噪音日志，写到临时文件，避免污染用户日志
config_module.LOG_PATH = os.path.join(tempfile.gettempdir(), "trans-integration.log")

SAMPLE = (
    "Measurements of the transverse momentum imbalance in proton-lead collisions "
    "provide new constraints on the parton distribution inside the nucleon."
)


def load_app_class():
    """Trans.pyw 不是常规 .py 后缀，用 SourceFileLoader 显式加载。"""
    loader = importlib.machinery.SourceFileLoader("trans_entry", os.path.join(ROOT, "Trans.pyw"))
    module = loader.load_module()
    return module.App


def collect_texts(widget: tk.Misc, found: list[str]) -> None:
    for child in widget.winfo_children():
        if isinstance(child, tk.Text):
            found.append(child.get("1.0", "end").strip())
        elif isinstance(child, tk.Label):
            found.append(child.cget("text"))
        collect_texts(child, found)


def main() -> int:
    config = Config.load()
    if not (config.get("model", "api_key") or "").strip():
        print("配置里没有 API Key，跳过集成测试。")
        return 0

    print(f"模型 = {config.get('model', 'model')}，接口 = {config.get('model', 'base_url')}")
    native.enable_dpi_awareness()
    clipboard_backup = native.clipboard_get_text()
    app = load_app_class()()
    try:
        app.root.after(40, app._tick)  # 替代 run()，让消息泵与结果回收跑起来
        if native.clipboard_available():
            native.clipboard_set_text(SAMPLE)
            app._translate_clipboard()
        else:
            # 锁屏等状态下剪贴板不可用，直接驱动“翻译 → 弹窗”这一段
            print("剪贴板当前不可用，跳过取词环节，直接驱动翻译链路")
            app._start_translation(SAMPLE, (200, 200))

        deadline = time.time() + 45
        while time.time() < deadline:
            app.root.update()
            if app.popup.visible and not app._busy:
                texts: list[str] = []
                collect_texts(app.popup.window, texts)
                body = [t for t in texts if t and t != "复制" and t != "✕"]
                translation = next((t for t in body if t != SAMPLE and "→" not in t), "")
                meta = next((t for t in body if "→" in t), "")
                print("弹窗标题：", meta)
                print("译文：", translation)
                ok = any("\u4e00" <= char <= "\u9fff" for char in translation)
                print("结果：", "PASS 译文为中文" if ok else "FAIL 译文不含中文")
                return 0 if ok else 1
            time.sleep(0.05)
        print("FAIL 超时未等到译文弹窗")
        return 1
    except Exception as exc:
        print("FAIL 集成测试异常：", exc)
        return 1
    finally:
        app._quit()
        if clipboard_backup:
            native.clipboard_set_text(clipboard_backup)


if __name__ == "__main__":
    raise SystemExit(main())
