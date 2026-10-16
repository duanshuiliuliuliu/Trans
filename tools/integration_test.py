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

# 自检启动的应用实例也会写日志，写到临时文件，避免污染用户日志
config_module.LOG_PATH = os.path.join(tempfile.gettempdir(), "trans-integration.log")

SAMPLE = (
    "Measurements of the transverse momentum imbalance in proton-lead collisions "
    "provide new constraints on the parton distribution inside the nucleon."
)


def load_entry_module():
    """Trans.pyw 不是常规 .py 后缀，用 SourceFileLoader 显式加载。"""
    loader = importlib.machinery.SourceFileLoader("trans_entry", os.path.join(ROOT, "Trans.pyw"))
    return loader.load_module()


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
    module = load_entry_module()
    app = module.App()
    try:
        app.root.after(40, app._tick)  # 替代 run()，让消息泵与结果回收跑起来

        # 启用状态要在图标、托盘菜单、设置界面三处保持一致
        def icon_matches(enabled: bool) -> bool:
            want_off = app.tray.icon_path.endswith("icon_off.ico")
            return want_off == (not enabled)

        enabled_now = bool(config.get("trigger", "enabled", True))
        print(f"启动图标与配置一致 = {icon_matches(enabled_now)}（启用={enabled_now}）")
        app._toggle_enabled()
        flipped = bool(app.config.get("trigger", "enabled", True))
        menu_label = module.tray_menu_items(flipped)[0][1]
        print(f"托盘切换后图标一致 = {icon_matches(flipped)}，菜单显示=「{menu_label}」")
        app._toggle_enabled()
        print(f"切换回原状态 = {bool(app.config.get('trigger', 'enabled', True)) == enabled_now}")

        # 取词依赖鼠标事件，自动化里无法合成，这里直接驱动“翻译 → 弹窗”这一段
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
