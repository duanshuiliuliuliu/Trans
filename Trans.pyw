"""Trans —— 极简划词翻译托盘工具（DeepSeek 驱动）。

双击本文件即可运行（.pyw 不会弹出控制台窗口）。
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
import faulthandler
from typing import Any, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import APP_NAME, __version__, native, resource_dir
from app import config as config_module
from app.config import Config, language_label
from app.lang import pick_target
from app.translator import translate
from app.ui_popup import Popup
from app.ui_settings import SettingsWindow

MUTEX_NAME = "Trans.TrayApp.Singleton"
SHOW_SETTINGS_MESSAGE = "Trans.ShowSettings"
WM_TRAY = native.WM_APP + 1

ICON_DIR = os.path.join(resource_dir(), "assets")
ICON_ON = os.path.join(ICON_DIR, "icon.ico")
ICON_OFF = os.path.join(ICON_DIR, "icon_off.ico")

MENU_TOGGLE = 1001
MENU_SETTINGS = 1002
MENU_QUIT = 1005

TICK_MS = 40
COPY_POLL_MS = 25
COPY_POLL_ATTEMPTS = 24

START_MARK = "=== Trans 启动"
EXIT_MARK = "=== Trans 退出 ==="


def tray_menu_items(enabled: bool) -> list:
    """托盘右键菜单：只有启用/禁用、设置、退出三项，且都不显示对号。"""
    return [
        (MENU_TOGGLE, "禁用" if enabled else "启用", False, True),
        (MENU_SETTINGS, "设置…", False, True),
        (MENU_QUIT, "退出", False, True),
    ]


def _install_crash_log() -> None:
    """把硬崩溃（访问违例、栈溢出等）的栈回溯写进日志文件。

    pythonw 没有控制台，崩溃现场默认什么都留不下，这里用 faulthandler 兜住。
    """
    try:
        log_path = config_module.LOG_PATH
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        handle = open(log_path, "a", encoding="utf-8", errors="replace", buffering=1)
        faulthandler.enable(file=handle, all_threads=True)
    except Exception:
        pass


def _check_previous_run() -> None:
    """上次若不是正常退出，写一条记录——崩溃往往只留下这个线索。"""
    try:
        with open(config_module.LOG_PATH, "r", encoding="utf-8", errors="replace") as handle:
            lines = [line.strip() for line in handle if line.strip()]
    except OSError:
        return
    if not lines:
        return
    tail = lines[-2000:]
    last_start = max((index for index, line in enumerate(tail) if START_MARK in line), default=-1)
    last_exit = max((index for index, line in enumerate(tail) if EXIT_MARK in line), default=-1)
    if last_start < 0 or last_exit > last_start:
        return  # 没有启动标记，或上次是正常退出
    Config.log(f"WARN 上次运行没有正常退出，最后一条记录：{tail[-1]}")


class App:
    def __init__(self, show_settings_on_start: bool = False) -> None:
        self.config = Config.load()
        self._selections: "queue.Queue[Tuple[int, int]]" = queue.Queue()
        self._clicks: "queue.Queue[Tuple[int, int]]" = queue.Queue()
        self._results: "queue.Queue[Tuple[int, Any]]" = queue.Queue()
        self._callbacks: "queue.Queue[Tuple[Any, Any]]" = queue.Queue()
        self._busy = False
        self._generation = 0
        self._dismissed_generation = 0
        self._stopping = False
        self._menu_open = False
        self._last_tick = time.time()
        self._last_action = "启动"
        self._pending_anchor: Tuple[int, int] = (0, 0)

        self.root = tk.Tk()
        self.root.withdraw()
        self._apply_dpi_scaling()
        # Tk 回调里的异常在 pythonw 下是看不到的，统一写进日志
        self.root.report_callback_exception = self._on_tk_exception

        self.native_window = native.NativeWindow()
        self.native_window.create()
        self.native_window.add_handler(WM_TRAY, self._on_tray_message)
        self.native_window.add_handler(native.WM_HOTKEY, self._on_hotkey)
        self._taskbar_created = self.native_window.register_message("TaskbarCreated")
        self.native_window.add_handler(self._taskbar_created, self._on_taskbar_created)
        self._show_settings_message = self.native_window.register_message(SHOW_SETTINGS_MESSAGE)
        self.native_window.add_handler(self._show_settings_message, self._on_show_settings_message)

        self.tray = native.TrayIcon(
            self.native_window.hwnd,
            WM_TRAY,
            self._tray_tooltip(),
            ICON_ON,
        )
        if not self._install_tray():
            self._log("托盘图标注册失败，稍后重试")
            self.root.after(1500, self._install_tray)

        self.hotkeys = native.HotkeyManager(self.native_window.hwnd)
        self._register_hotkey()

        self.popup = Popup(
            self.root,
            self.config,
            on_dismiss=self._on_popup_dismiss,
            logger=self._log,
            copy_text=self._copy_text_async,
        )
        self.settings = SettingsWindow(self.root, self.config, self._apply_config)
        self.hook = native.MouseHook(
            on_select=self._on_selection,
            min_drag_px=int(self.config.get("trigger", "min_drag_px", 4) or 4),
            is_ignored_window=self._is_own_window,
            on_click=self._on_mouse_click,
            require_ctrl=bool(self.config.get("trigger", "require_ctrl", True)),
        )
        if self.config.get("trigger", "mouse_selection", True):
            self._start_hook()
        if not self.config.get("ui", "hint_shown", False):
            self.root.after(800, self._show_first_run_hint)

        if show_settings_on_start:
            self.root.after(120, self.settings.show)
        self._start_watchdog()
        Config.log(f"{START_MARK} v{__version__} ===")

    # ------------------------------------------------------------ 启动/退出
    def _apply_dpi_scaling(self) -> None:
        try:
            scale = native.system_dpi() / 96.0
            if scale > 0:
                # tk scaling 表示“每磅像素数”，96 DPI 时约为 96/72
                self.root.tk.call("tk", "scaling", 96.0 * scale / 72.0)
        except Exception:
            pass

    def _install_tray(self) -> bool:
        if self.tray.add():
            return True
        return False

    # ------------------------------------------------------------ 稳定性监控
    def _mark_action(self, action: str) -> None:
        """记录最近一步动作，卡顿时看门狗会把它写进日志。"""
        self._last_action = action

    def _start_watchdog(self) -> None:
        self._last_tick = time.time()
        threading.Thread(target=self._watchdog_loop, name="trans-watchdog", daemon=True).start()

    def _watchdog_loop(self) -> None:
        """主线程卡住超过 2 秒就记一条日志（鼠标变卡的根因通常就在这里）。"""
        while not self._stopping:
            time.sleep(0.5)
            if getattr(self, "_menu_open", False):
                self._last_tick = time.time()  # 原生菜单是模态循环，不算卡死
                continue
            stalled = time.time() - self._last_tick
            if stalled > 2.0:
                Config.log(f"WARN 主线程卡住 {stalled:.1f}s（最近动作：{self._last_action}）")
                self._last_tick = time.time()

    def _on_tk_exception(self, exc_type, value, tb) -> None:
        try:
            detail = "".join(traceback.format_exception(exc_type, value, tb))
            Config.log("ERROR Tk 回调异常：\n" + detail)
        except Exception:
            pass

    def _show_first_run_hint(self) -> None:
        self.tray.show_balloon(
            "Trans 已启动",
            "按住 Ctrl 用鼠标划选文字即可翻译；也可按 Ctrl+Alt+T 翻译当前选中内容。",
        )
        self.config.set("ui", "hint_shown", True)
        self.config.save()

    def _start_hook(self) -> None:
        if self.hook.handle:
            return
        if self.hook.start():
            self._log("鼠标钩子已安装")
        else:
            Config.log("ERROR 鼠标钩子安装失败，划选取词不可用")
            self.tray.show_balloon("Trans", "鼠标钩子安装失败，请改用 Ctrl+Alt+T 取词。")

    def _tray_tooltip(self) -> str:
        state = "已启用" if self.config.get("trigger", "enabled", True) else "已禁用"
        return f"{APP_NAME} 划词翻译 · {state}"

    def run(self) -> None:
        self.root.after(TICK_MS, self._tick)
        self.root.mainloop()

    def _quit(self) -> None:
        self._stopping = True
        try:
            self.hook.stop()
            self.hotkeys.unregister()
            self.tray.remove()
            self.popup.hide()
            self.settings.destroy()
            self.native_window.destroy()
        except Exception:
            pass
        Config.log(EXIT_MARK)  # 正常退出标记始终写入：下次启动用它判断上次是否崩过
        try:
            self.root.quit()
            self.root.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 消息循环
    def _tick(self) -> None:
        self._last_tick = time.time()
        self.native_window.pump()
        self._drain_callbacks()
        self._drain_selections()
        self._drain_clicks()
        self._drain_results()
        self.root.after(TICK_MS, self._tick)

    def _run_async(self, work: Any, done: Any) -> None:
        """在工作线程里做可能阻塞的事（剪贴板、网络），结果回主线程处理。"""

        def runner() -> None:
            try:
                result = work()
            except Exception as exc:
                self._log_traceback("后台任务异常", exc)
                result = None
            self._callbacks.put((done, result))

        threading.Thread(target=runner, name="trans-worker", daemon=True).start()

    def _drain_callbacks(self) -> None:
        while True:
            try:
                done, result = self._callbacks.get_nowait()
            except queue.Empty:
                break
            try:
                done(result)
            except Exception as exc:
                self._log_traceback("回调异常", exc)

    def _log_traceback(self, label: str, exc: BaseException) -> None:
        try:
            Config.log(f"ERROR {label}：{''.join(traceback.format_exception(exc))}")
        except Exception:
            pass

    def _log(self, message: str) -> None:
        if self.config.data.get("debug"):
            Config.log(message)

    def _log_error(self, message: str) -> None:
        Config.log("ERROR " + message)

    # ------------------------------------------------------------ 托盘
    def _on_tray_message(self, wparam: int, lparam: int) -> Optional[int]:
        if lparam == native.WM_LBUTTONDBLCLK:
            self.settings.show()
        elif lparam == native.WM_RBUTTONUP:
            self._show_menu()
        return 0

    def _show_menu(self) -> None:
        enabled = bool(self.config.get("trigger", "enabled", True))
        self._mark_action("显示托盘菜单")
        self._menu_open = True
        try:
            command = native.show_popup_menu(self.native_window.hwnd, tray_menu_items(enabled))
        finally:
            self._menu_open = False
            self._last_tick = time.time()
        if command == MENU_TOGGLE:
            self._toggle_enabled()
        elif command == MENU_SETTINGS:
            self.settings.show()
        elif command == MENU_QUIT:
            self._quit()

    def _toggle_enabled(self) -> None:
        enabled = not bool(self.config.get("trigger", "enabled", True))
        self.config.set("trigger", "enabled", enabled)
        self.config.save()
        self.tray.set_icon(ICON_ON if enabled else ICON_OFF)
        self.tray.set_tooltip(self._tray_tooltip())
        self._log(f"切换启用状态：{enabled}")

    def _on_taskbar_created(self, _wparam: int, _lparam: int) -> Optional[int]:
        self._install_tray()
        return 0

    def _on_show_settings_message(self, _wparam: int, _lparam: int) -> Optional[int]:
        self.settings.show()
        return 0

    # ------------------------------------------------------------ 热键
    def _register_hotkey(self) -> None:
        hotkey = self.config.get("trigger", "hotkey", "Ctrl+Alt+T")
        ok, message = self.hotkeys.register(hotkey)
        if not ok:
            Config.log(f"ERROR 热键注册失败：{message}")

    def _on_hotkey(self, _wparam: int, _lparam: int) -> Optional[int]:
        self._translate_current_selection(*native.get_cursor_pos())
        return 0

    # ------------------------------------------------------------ 配置应用
    def _apply_config(self) -> None:
        self.hotkeys.unregister()
        self._register_hotkey()
        self.tray.set_icon(ICON_ON if self.config.get("trigger", "enabled", True) else ICON_OFF)
        self.tray.set_tooltip(self._tray_tooltip())
        self.hook.min_drag_px = int(self.config.get("trigger", "min_drag_px", 4) or 4)
        self.hook.require_ctrl = bool(self.config.get("trigger", "require_ctrl", True))
        if self.config.get("trigger", "mouse_selection", True):
            self._start_hook()
        else:
            self.hook.stop()
        self._log("配置已更新")

    # ------------------------------------------------------------ 取词
    def _on_selection(self, x: int, y: int, kind: str = "drag") -> None:
        """鼠标钩子回调：只入队，不做耗时操作。"""
        if not self.config.get("trigger", "enabled", True):
            return
        if not self.config.get("trigger", "mouse_selection", True):
            return
        self._log(f"检测到{'双击选词' if kind == 'click' else '划选'} ({x},{y})")
        self._selections.put((x, y, kind))

    def _drain_selections(self) -> None:
        latest: Optional[Tuple[int, int, str]] = None
        while True:
            try:
                latest = self._selections.get_nowait()
            except queue.Empty:
                break
        if latest is None:
            return
        self._schedule_capture(latest)

    def _schedule_capture(self, selection: Tuple[int, int, str]) -> None:
        x, y, kind = selection
        delay = int(self.config.get("trigger", "copy_delay_ms", 130) or 0)
        if kind == "click":
            # 双击之后可能还有三击，多等一会儿再复制，避免取到半截选中内容
            delay = max(delay, 260)

        def start() -> None:
            self._translate_current_selection(x, y)

        if delay > 0:
            self.root.after(delay, start)
        else:
            self.root.after(0, start)

    def _translate_current_selection(self, x: int, y: int) -> None:
        if not self.config.get("trigger", "enabled", True):
            return
        self._pending_anchor = (x, y)
        self._mark_action("取词：保存剪贴板快照")
        # 剪贴板可能被别的程序独占到秒级，一律放工作线程，避免卡住主线程（钩子由主线程服务）
        self._run_async(self._snapshot_clipboard, self._after_snapshot)

    def _after_snapshot(self, snapshot: Any) -> None:
        sequence = native.clipboard_sequence_number()
        self._mark_action("取词：模拟 Ctrl+C")
        native.send_ctrl_c()
        self._poll_clipboard(sequence, snapshot or {}, 0)

    def _poll_clipboard(self, sequence: int, snapshot: Dict[str, Any], attempt: int) -> None:
        if native.clipboard_sequence_number() != sequence:
            self._consume_selection(snapshot)
            return
        if attempt >= COPY_POLL_ATTEMPTS:
            self._run_async(lambda: self._restore_clipboard(snapshot), lambda _r: None)
            self._log("未取到选中文本（目标程序没有响应复制）")
            return  # 没有复制到任何内容，静默放弃
        self._mark_action("取词：等待剪贴板变化")
        self.root.after(COPY_POLL_MS, lambda: self._poll_clipboard(sequence, snapshot, attempt + 1))

    def _consume_selection(self, snapshot: Dict[str, Any]) -> None:
        self._mark_action("取词：读取剪贴板")
        self._run_async(lambda: self._read_selection(snapshot), self._after_read)

    def _read_selection(self, snapshot: Dict[str, Any]) -> str:
        """工作线程内：先读走选中文本，再还原原剪贴板（顺序不能反）。"""
        text = native.clipboard_get_text() or ""
        self._restore_clipboard(snapshot)
        return text.strip()

    def _after_read(self, text: Any) -> None:
        value = str(text or "").strip()
        if not value:
            self._log("剪贴板为空或被其它程序占用，放弃本次取词")
            return
        self._log(f"取到文本 {len(value)} 字")
        self._start_translation(value, self._pending_anchor)

    def _translate_clipboard(self) -> None:
        anchor = native.get_cursor_pos()
        self._mark_action("读剪贴板内容")
        self._run_async(
            lambda: (native.clipboard_get_text() or "").strip(),
            lambda text: self._after_clipboard_read(str(text or "").strip(), anchor),
        )

    def _after_clipboard_read(self, text: str, anchor: Tuple[int, int]) -> None:
        if not text:
            self.popup.show_error("剪贴板里没有可翻译的文本。", *anchor)
            return
        self._start_translation(text, anchor)

    def _copy_text_async(self, text: str, done: Any) -> None:
        self._run_async(lambda: native.clipboard_set_text(text), done)

    # ------------------------------------------------------------ 剪贴板快照
    def _snapshot_clipboard(self) -> Dict[str, Any]:
        """只能在 work 线程调用（读剪贴板可能等待别的程序释放）。"""
        return {
            "text": native.clipboard_get_text(),
            "rich": native.clipboard_has_rich_content(),
        }

    def _restore_clipboard(self, snapshot: Dict[str, Any]) -> None:
        """只能在 work 线程调用。"""
        policy = str(self.config.get("trigger", "restore_clipboard", "auto") or "auto")
        if policy == "never":
            return
        if policy == "auto" and snapshot.get("rich"):
            return  # 原剪贴板含图片/文件等格式，避免破坏
        text = snapshot.get("text")
        if text:
            native.clipboard_set_text(text)

    # ------------------------------------------------------------ 翻译
    def _start_translation(self, text: str, anchor: Tuple[int, int]) -> None:
        max_chars = int(self.config.get("rules", "max_chars", 3000) or 3000)
        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True

        detected, target, _rule = pick_target(text, self.config.rules, fallback="zh")
        model_config = dict(self.config.section("model"))
        if not (model_config.get("api_key") or "").strip():
            self.popup.show_error("尚未配置 API Key，请在设置里填写。", *anchor)
            return

        self._generation += 1
        generation = self._generation
        self._busy = True
        self._mark_action("翻译：请求接口")
        self._log(f"开始翻译：{len(text)} 字 → {target}")
        self.popup.show_pending(anchor[0], anchor[1], f"{language_label(detected) or '自动识别'} → {language_label(target) or target}")

        def worker() -> None:
            ok, result, elapsed = translate(text, target, model_config)
            self._results.put(
                (
                    generation,
                    {
                        "ok": ok,
                        "result": result,
                        "elapsed": elapsed,
                        "source": text,
                        "target": target,
                        "detected": detected,
                        "truncated": truncated,
                        "anchor": anchor,
                    },
                )
            )

        threading.Thread(target=worker, name="trans-worker", daemon=True).start()

    def _drain_results(self) -> None:
        while True:
            try:
                generation, payload = self._results.get_nowait()
            except queue.Empty:
                break
            if generation != self._generation:
                continue  # 已被更新的请求取代
            self._busy = False
            if generation == self._dismissed_generation:
                self._log("结果已返回，但弹窗被用户关闭，跳过显示")
                continue
            self._show_payload(payload)

    def _show_payload(self, payload: Dict[str, Any]) -> None:
        anchor = payload["anchor"]
        self._mark_action("渲染结果弹窗")
        if not payload["ok"]:
            self._log_error(f"翻译失败：{payload['result']}")
            self.popup.show_error(str(payload["result"]), *anchor)
            return
        self._log(f"翻译完成，耗时 {payload['elapsed']:.1f}s")
        meta_parts = [
            f"{language_label(payload['detected']) or '自动识别'} → {language_label(payload['target']) or payload['target']}"
        ]
        model_name = str(self.config.get("model", "model", "") or "")
        if model_name:
            meta_parts.append(model_name)
        meta_parts.append(f"{payload['elapsed']:.1f}s")
        if payload["truncated"]:
            meta_parts.append("已截断")
        self.popup.show_result(
            payload["source"], payload["result"], " · ".join(meta_parts), *anchor
        )

    # ------------------------------------------------------------ 辅助
    def _is_own_window(self, hwnd: int) -> bool:
        return native.window_pid(hwnd) == os.getpid()

    def _on_mouse_click(self, x: int, y: int) -> None:
        """钩子回调里只入队：绝对不能在这里做 Tk 操作（会重入消息泵）。"""
        self._clicks.put((x, y))

    def _drain_clicks(self) -> None:
        latest: Optional[Tuple[int, int]] = None
        while True:
            try:
                latest = self._clicks.get_nowait()
            except queue.Empty:
                break
        if latest is None:
            return
        if self.popup.closing:
            return  # 关闭流程自己管销毁时机，别在这里插手
        if self.popup.visible and not self.popup.contains(latest[0], latest[1]):
            self._mark_action("点击弹窗外部，关闭弹窗")
            self.popup.hide()

    def _on_popup_dismiss(self) -> None:
        """用户点了 ✕：这一轮的结果不要再弹出来打扰他。"""
        self._dismissed_generation = self._generation
        self._mark_action("用户关闭弹窗")


def main() -> int:
    _install_crash_log()
    _check_previous_run()
    native.enable_dpi_awareness()
    _handle, already_running = native.create_singleton_mutex(MUTEX_NAME)
    if already_running:
        # 已有实例：广播消息让它打开设置窗口，本进程直接退出
        message = native._register_window_message(SHOW_SETTINGS_MESSAGE)
        native.broadcast_message(message)
        return 0
    App().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
