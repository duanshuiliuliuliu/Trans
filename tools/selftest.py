"""非交互自检：覆盖数据结构、语言检测、规则匹配、配置读写、
剪贴板、原生窗口与托盘注册等可自动验证的部分。

用法：python tools/selftest.py
托盘/鼠标钩子/弹窗的真实交互无法自动化，需按 README 的检查清单人工回归。
"""
from __future__ import annotations

import ctypes
import importlib.machinery
import json
import os
import sys
import tempfile
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import native
from app import config as config_module
from app.config import Config
from app.lang import detect_language, pick_target
from app.translator import build_endpoint, build_messages

PASSED = 0
FAILED: list[str] = []
SKIPPED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if condition:
        PASSED += 1
        print(f"  [PASS] {name}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name} {detail}")


def skip(name: str, reason: str) -> None:
    SKIPPED.append(name)
    print(f"  [SKIP] {name}（{reason}）")


def test_structs() -> None:
    print("结构体大小")
    expected_input = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    check("INPUT 结构大小", ctypes.sizeof(native.INPUT) == expected_input, f"= {ctypes.sizeof(native.INPUT)}")
    expected_nid = 952 if ctypes.sizeof(ctypes.c_void_p) == 8 else 936
    check(
        "NOTIFYICONDATAW 为 V2 布局",
        ctypes.sizeof(native.NOTIFYICONDATAW) == expected_nid,
        f"= {ctypes.sizeof(native.NOTIFYICONDATAW)}",
    )


def test_hotkey() -> None:
    print("热键解析")
    check("Ctrl+Alt+T", native.parse_hotkey("Ctrl+Alt+T") == (native.MOD_CONTROL | native.MOD_ALT | native.MOD_NOREPEAT, 0x54))
    check("Ctrl+Shift+F2", native.parse_hotkey("ctrl + shift + f2") == (native.MOD_CONTROL | native.MOD_SHIFT | native.MOD_NOREPEAT, 0x71))
    check("缺少修饰键应失败", native.parse_hotkey("T") is None)
    check("非法键名应失败", native.parse_hotkey("Ctrl+Abc") is None)


def test_language() -> None:
    print("语言检测与规则")
    check("中文", detect_language("这是一段中文文本") == "zh")
    check("日语含假名", detect_language("これはテストです") == "ja")
    check("韩语", detect_language("안녕하세요 반갑습니다") == "ko")
    check("英语", detect_language("Hello world, this is a test.") == "en")
    check("俄语", detect_language("Привет мир") == "ru")
    check("纯数字无法判断", detect_language("12345") == "unknown")

    rules = [
        {"source": "zh", "target": "en"},
        {"source": "ja", "target": "en"},
        {"source": "auto", "target": "zh"},
    ]
    check("中文译英", pick_target("你好世界", rules)[1] == "en")
    check("英语译中", pick_target("hello", rules)[1] == "zh")
    check("兜底规则命中", pick_target("12345", rules)[1] == "zh")
    check("无匹配时回退", pick_target("hello", [{"source": "zh", "target": "en"}])[1] == "zh")


def test_translator() -> None:
    print("接口拼装")
    check("默认地址", build_endpoint("https://api.deepseek.com") == "https://api.deepseek.com/chat/completions")
    check("/v1 地址", build_endpoint("https://api.deepseek.com/v1/") == "https://api.deepseek.com/v1/chat/completions")
    check("已含路径", build_endpoint("https://x/chat/completions") == "https://x/chat/completions")
    messages = build_messages("hello", "en", "翻译成{target}")
    check("提示词替换", messages[0]["content"] == "翻译成英语", messages[0]["content"])
    check("用户消息", messages[1] == {"role": "user", "content": "hello"})


def test_config() -> None:
    print("配置读写")
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "config.json")
        config = Config.load(path)
        check("默认热键", config.get("trigger", "hotkey") == "Ctrl+Alt+T")
        config.set("model", "api_key", "sk-test-123456")
        config.set("model", "model", "deepseek-chat")
        config.replace_rules([{"source": "zh", "target": "ja"}])
        config.save()
        raw = open(path, encoding="utf-8").read()
        check("密钥不落明文", "sk-test-123456" not in raw)
        reopened = Config.load(path)
        check("密钥可解密还原", reopened.get("model", "api_key") == "sk-test-123456", str(reopened.get("model", "api_key")))
        check("规则持久化", reopened.rules == [{"source": "zh", "target": "ja"}])
        check("非法 JSON 回退默认", Config.load(os.path.join(folder, "none.json")).get("trigger", "hotkey") == "Ctrl+Alt+T")

    check("DPAPI 往返", native.dpapi_decrypt(native.dpapi_encrypt("测试密钥") or b"") == "测试密钥")


def test_clipboard() -> None:
    print("剪贴板")
    if not native.clipboard_available():
        skip("剪贴板用例", "剪贴板被其它程序独占，暂时打不开")
        return
    backup = native.clipboard_get_text()
    try:
        check("写入文本", native.clipboard_set_text("Trans 自检 hello"))
        check("读回文本", native.clipboard_get_text() == "Trans 自检 hello")
        check("序号变化", native.clipboard_sequence_number() > 0)
        check("格式枚举", native.CF_UNICODETEXT in native.clipboard_formats())
        check("纯文本不算富内容", native.clipboard_has_rich_content() is False)
    finally:
        if backup:
            native.clipboard_set_text(backup)


def test_process_and_screen() -> None:
    print("屏幕与 DPI")
    left, top, right, bottom = native.get_work_area()
    check("工作区有效", right > left and bottom > top, f"{left},{top},{right},{bottom}")
    check("DPI 有值", native.system_dpi() >= 96, str(native.system_dpi()))


def test_native_window_and_tray() -> None:
    print("原生窗口与托盘（会出现极短的托盘图标闪现）")
    window = native.NativeWindow(class_name="TransSelfTestWnd")
    hook = None
    try:
        hwnd = window.create()
        check("隐藏窗口创建", hwnd != 0)
        received: list[int] = []
        window.add_handler(native.WM_APP + 7, lambda w, l: received.append(w) or 0)
        window.post(native.WM_APP + 7, 42, 0)
        window.pump()
        check("消息泵可分发", received == [42], str(received))

        tray = native.TrayIcon(hwnd, native.WM_APP + 1, "Trans 自检", os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.ico"))
        check("托盘图标注册", tray.add())
        tray.set_tooltip("Trans 自检进行中")
        tray.remove()

        hook = native.MouseHook(on_select=lambda x, y, kind: None)
        check("鼠标钩子安装", hook.start())
    finally:
        if hook is not None:
            hook.stop()
        window.destroy()


def test_mouse_detection() -> None:
    print("划选与双击识别")

    def make(require_ctrl: bool, ctrl: bool = False):
        events: list[str] = []
        hook = native.MouseHook(
            on_select=lambda x, y, kind: events.append(kind),
            require_ctrl=require_ctrl,
            ctrl_check=lambda: ctrl,
        )
        return hook, events

    # --- “任意选中都翻译”模式 ---
    hook, events = make(False)
    hook._handle_mouse(native.WM_LBUTTONDOWN, 100, 100)
    hook._handle_mouse(native.WM_LBUTTONUP, 100, 100)
    check("单击不触发翻译", events == [], str(events))

    hook._handle_mouse(native.WM_LBUTTONDOWN, 100, 100)
    hook._handle_mouse(native.WM_LBUTTONUP, 180, 100)
    check("不要求 Ctrl 时拖动触发", events == ["drag"], str(events))

    hook._handle_mouse(native.WM_LBUTTONDOWN, 100, 100)
    hook._handle_mouse(native.WM_LBUTTONUP, 100, 102)
    check("微动不触发", events == ["drag"], str(events))

    hook._handle_mouse(native.WM_LBUTTONDOWN, 100, 100)
    hook._handle_mouse(native.WM_LBUTTONDBLCLK, 101, 101)
    hook._handle_mouse(native.WM_LBUTTONUP, 101, 101)
    check("双击不触发（只认划选）", events == ["drag"], str(events))

    ignored = native.MouseHook(
        on_select=lambda x, y, kind: events.append("own"),
        is_ignored_window=lambda hwnd: True,
        require_ctrl=False,
    )
    ignored._handle_mouse(native.WM_LBUTTONDOWN, 100, 100)
    ignored._handle_mouse(native.WM_LBUTTONUP, 200, 100)
    check("自身窗口内拖动不触发", "own" not in events, str(events))

    # --- 默认模式：必须按住 Ctrl ---
    hook_no_ctrl, events_no_ctrl = make(True, ctrl=False)
    hook_no_ctrl._handle_mouse(native.WM_LBUTTONDOWN, 100, 100)
    hook_no_ctrl._handle_mouse(native.WM_LBUTTONUP, 180, 100)
    check("没按 Ctrl 时不触发", events_no_ctrl == [], str(events_no_ctrl))

    hook_ctrl, events_ctrl = make(True, ctrl=True)
    hook_ctrl._handle_mouse(native.WM_LBUTTONDOWN, 100, 100)
    hook_ctrl._handle_mouse(native.WM_LBUTTONUP, 180, 100)
    check("按住 Ctrl 划选触发", events_ctrl == ["drag"], str(events_ctrl))


def test_tk() -> None:
    print("Tk 界面组件")
    root = tk.Tk()
    root.withdraw()
    try:
        from app.ui_popup import Popup
        from app.ui_settings import SettingsWindow

        config = Config.load(os.path.join(tempfile.gettempdir(), "trans-selftest-none.json"))
        popup = Popup(root, config)
        popup.show_result("hello", "你好", "英语 → 中文 · 0.8s", 100, 100)
        root.update()
        check("结果弹窗渲染", popup.visible)
        popup.hide()
        check("弹窗关闭", not popup.visible)

        # 点 ✕ 的路径：立即隐藏，稍后销毁
        popup.show_result("hello", "你好", "英语 → 中文 · 0.8s", 100, 100)
        root.update()
        check("弹窗再次渲染", popup.visible)
        popup.dismiss()
        check("✕ 后立刻不可见", not popup.visible or popup.closing)
        deadline = time.time() + 2
        while time.time() < deadline and popup.visible:
            root.update()
            time.sleep(0.02)
        check("✕ 后窗口最终被销毁", not popup.visible, "窗口仍然存在")
        check("✕ 后重置内部状态", popup.closing is False)

        settings = SettingsWindow(root, config, lambda: None)
        settings.show()
        root.update()
        check("设置窗口渲染", settings.window is not None and settings.window.winfo_exists())
        settings.destroy()

        from tkinter import font as tkfont

        from app.ui_popup import _wrapped_line_count

        font = tkfont.Font(size=11)
        check("短文本按一行计算", _wrapped_line_count("你好", font, 400) == 1)
        check("长中文按宽度折行", _wrapped_line_count("中" * 120, font, 200) >= 4)
        check("空文本按一行计算", _wrapped_line_count("", font, 400) == 1)
    finally:
        root.destroy()


def test_tray_menu() -> None:
    print("托盘菜单项")
    loader = importlib.machinery.SourceFileLoader(
        "trans_entry_selftest", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Trans.pyw")
    )
    module = loader.load_module()
    enabled_items = module.tray_menu_items(True)
    disabled_items = module.tray_menu_items(False)
    check("菜单只有三项", len(enabled_items) == 3, str(enabled_items))
    check(
        "启用状态下列表为 禁用/设置/退出",
        [label for _id, label, _checked, _ok in enabled_items] == ["禁用", "设置…", "退出"],
        str(enabled_items),
    )
    check(
        "禁用状态下列表为 启用/设置/退出",
        [label for _id, label, _checked, _ok in disabled_items] == ["启用", "设置…", "退出"],
        str(disabled_items),
    )
    check(
        "菜单项都没有对号",
        all(checked is False for _id, _label, checked, _ok in enabled_items + disabled_items),
        str(enabled_items + disabled_items),
    )


def test_previous_run_check() -> None:
    print("上次异常退出检测")
    loader = importlib.machinery.SourceFileLoader(
        "trans_entry_prevrun",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Trans.pyw"),
    )
    module = loader.load_module()
    original = config_module.LOG_PATH
    try:
        with tempfile.TemporaryDirectory() as folder:
            log_path = os.path.join(folder, "trans.log")
            config_module.LOG_PATH = log_path

            open(log_path, "w", encoding="utf-8").close()
            module._check_previous_run()
            check("空日志不报警", open(log_path, encoding="utf-8").read() == "")

            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write("[t] === Trans 启动 v0.1.0 ===\n[t] === Trans 退出 ===\n")
            module._check_previous_run()
            check("正常退出不报警", "上次运行没有正常退出" not in open(log_path, encoding="utf-8").read())

            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write("[t] === Trans 启动 v0.1.0 ===\n[t] 开始翻译：5 字 → en\n")
            module._check_previous_run()
            text = open(log_path, encoding="utf-8").read()
            check("异常结束会报警", "上次运行没有正常退出" in text, text)

            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write("[t] 别的程序写的日志\n")
            module._check_previous_run()
            check(
                "与程序无关的日志不报警",
                "上次运行没有正常退出" not in open(log_path, encoding="utf-8").read(),
            )

            # 大量噪音日志之后仍要能判断出上次是异常结束
            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write("[t] === Trans 启动 v0.1.0 ===\n")
                handle.write("[t] 弹窗：渲染完成\n" * 200)
            module._check_previous_run()
            check(
                "噪音日志不影响判断",
                "上次运行没有正常退出" in open(log_path, encoding="utf-8").read(),
            )
    finally:
        config_module.LOG_PATH = original


def main() -> int:
    if not native.is_windows():
        print("本自检仅支持 Windows")
        return 1
    for test in (
        test_structs,
        test_hotkey,
        test_language,
        test_translator,
        test_config,
        test_clipboard,
        test_process_and_screen,
        test_native_window_and_tray,
        test_mouse_detection,
        test_tk,
        test_tray_menu,
        test_previous_run_check,
    ):
        test()
    print()
    summary = f"通过 {PASSED} 项，失败 {len(FAILED)} 项"
    if SKIPPED:
        summary += f"，跳过 {len(SKIPPED)} 项"
    print(summary)
    for name in SKIPPED:
        print("  跳过：" + name)
    for name in FAILED:
        print("  失败：" + name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
