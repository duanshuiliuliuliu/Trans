"""结果弹窗：白底卡片、Windows 11 原生圆角、置顶但不抢焦点。

视觉结构：
    ▌ 英语 → 中文 · deepseek-flash · 1.4s      复制  ✕
    ─────────────────────────────────────────────────────
     原文（小号灰色，最多两行）
     译文（正文字号，行距放宽，可选中、可滚动）
"""
from __future__ import annotations

import ctypes
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Dict, Optional

from . import native
from .config import Config

# 配色：浅色 / 暗色两套，字段一一对应
LIGHT_THEME = {
    "card": "#FFFFFF",
    "hairline": "#EDF0F4",
    "text_main": "#1F2430",
    "text_muted": "#98A1B0",
    "text_source": "#9AA3B2",
    "accent": "#2F6FEB",
    "accent_pending": "#9BB4E8",
    "accent_error": "#D64545",
    "text_error": "#A32B2B",
    "hover_bg": "#F1F3F6",
    "select_bg": "#CFE0FF",
    "scroll_bg": "#E3E6EA",
    "scroll_trough": "#F4F6F8",
}

DARK_THEME = {
    "card": "#22262E",
    "hairline": "#31363F",
    "text_main": "#E7EAF0",
    "text_muted": "#9AA3B2",
    "text_source": "#98A1B0",
    "accent": "#5B8DEF",
    "accent_pending": "#3D5C93",
    "accent_error": "#D95656",
    "text_error": "#F2A2A2",
    "hover_bg": "#2C323B",
    "select_bg": "#3C5A8C",
    "scroll_bg": "#3A404A",
    "scroll_trough": "#272C34",
}

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


def _pick_font_family() -> str:
    families = set(tkfont.families())
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"):
        if name in families:
            return name
    return "TkDefaultFont"


def _round_corners(hwnd: int, preference: int = DWMWCP_ROUND) -> None:
    """Windows 11 下让无边框窗口获得系统圆角，其它系统静默忽略。"""
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        value = ctypes.c_int(preference)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(value), 4)
    except (OSError, AttributeError):
        pass


def _wrapped_line_count(
    text: str,
    font: tkfont.Font,
    max_px: int,
    width_cache: Optional[Dict[str, float]] = None,
) -> int:
    """按真实字形宽度估算折行行数（中英文混排也准）。

    逐字累加宽度，避免 "current + char" 那种每次都重新测量的写法。
    font.measure 每次都是一次 Tcl 调用（约 0.1ms），所以传入 width_cache
    按字符缓存测量结果：一段中文里不同字符只有几百个，长文本能省掉大半调用。
    """
    if max_px <= 20 or not text:
        return 1
    total = 0
    for paragraph in text.split("\n"):
        if not paragraph or font.measure(paragraph) <= max_px:
            total += 1
            continue
        width = 0.0
        lines = 1
        for char in paragraph:
            advance = None
            if width_cache is not None:
                advance = width_cache.get(char)
            if advance is None:
                advance = font.measure(char)
                if width_cache is not None:
                    width_cache[char] = advance
            if width and width + advance > max_px:
                lines += 1
                width = advance
            else:
                width += advance
        total += lines
    return total


class Popup:
    """单例弹窗：同一时刻只显示一个。"""

    def __init__(
        self,
        root: tk.Misc,
        config: Config,
        on_dismiss: Optional[Callable[[], None]] = None,
        logger: Optional[Callable[[str], None]] = None,
        copy_text: Optional[Callable[[str, Callable[[bool], None]], None]] = None,
    ) -> None:
        self.root = root
        self.config = config
        self.on_dismiss = on_dismiss
        self._log = logger or (lambda _message: None)
        self.copy_text = copy_text
        self.window: Optional[tk.Toplevel] = None
        self._auto_close_job: Optional[str] = None
        self._auto_close_override: Optional[float] = None
        self._closing = False
        self._drag_offset = (0, 0)
        self._family = _pick_font_family()
        self._fonts: dict = {}  # size -> (正文字体, 小号字体, 原文小号字体)
        self._char_widths: dict = {}  # size -> {字符: 宽度}，避免重复调用 font.measure

    def _fonts_for(self, size: int):
        """按字号缓存字体对象：每次弹窗都新建 Font 会重复查询字体度量。"""
        cached = self._fonts.get(size)
        if cached is None:
            small = max(8, size - 2)
            cached = (
                tkfont.Font(family=self._family, size=size),
                tkfont.Font(family=self._family, size=small),
                tkfont.Font(family=self._family, size=small),
            )
            self._fonts[size] = cached
        return cached

    # --- 对外接口 ---------------------------------------------------
    @property
    def visible(self) -> bool:
        return self.window is not None and bool(self.window.winfo_exists())

    @property
    def closing(self) -> bool:
        """已经点了 ✕、正在等鼠标松开后销毁。"""
        return self._closing

    def contains(self, x: int, y: int) -> bool:
        if not self.visible or self._closing:
            return False
        window = self.window
        assert window is not None
        left = window.winfo_rootx()
        top = window.winfo_rooty()
        return left <= x <= left + window.winfo_width() and top <= y <= top + window.winfo_height()

    def hide(self) -> None:
        self._log("弹窗：销毁开始")
        self._cancel_auto_close()
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
        self._closing = False
        self._auto_close_override = None
        self._log("弹窗：销毁完成")

    def dismiss(self) -> None:
        """用户点 ✕：先隐藏，等鼠标松开之后再真正销毁窗口。

        按下鼠标的那一刻就把窗口销毁，会让 Windows 的隐式鼠标捕获指向一个
        已经不存在的窗口，是输入卡顿的常见来源，所以这里分两步。
        """
        if self._closing:
            return
        self._closing = True
        self._log("弹窗：用户点了关闭")
        if self.on_dismiss is not None:
            try:
                self.on_dismiss()
            except Exception:
                pass
        window = self.window
        if window is None:
            self._closing = False
            return
        self._cancel_auto_close()
        try:
            window.withdraw()
        except tk.TclError:
            self.hide()
            return
        try:
            window.after(160, self.hide)
        except tk.TclError:
            self.hide()

    def show_error(self, message: str, x: int, y: int) -> None:
        self._render("", message, "翻译失败", x, y, state="error")

    def show_pending(self, x: int, y: int, note: str) -> None:
        self._render("", "正在翻译…", note, x, y, state="pending", auto_close=60.0)

    def show_result(self, source: str, translation: str, meta: str, x: int, y: int) -> None:
        self._render(source, translation, meta, x, y, state="result")

    # --- 渲染 -------------------------------------------------------
    def _render(
        self,
        source: str,
        body: str,
        meta: str,
        x: int,
        y: int,
        state: str,
        auto_close: Optional[float] = None,
    ) -> None:
        self.hide()
        self._auto_close_override = auto_close

        error = state == "error"
        pending = state == "pending"
        theme = DARK_THEME if self.config.get("ui", "dark_mode", False) else LIGHT_THEME
        accent = (
            theme["accent_error"]
            if error
            else (theme["accent_pending"] if pending else theme["accent"])
        )
        size = max(9, int(self.config.get("ui", "font_size", 11) or 11))
        body_font, meta_font, source_font = self._fonts_for(size)

        # 按锚点（选中位置）所在显示器取工作区，多显示器下弹窗才会出现在副屏
        work_left, work_top, work_right, work_bottom = native.get_work_area(x, y)
        work_width = max(240, work_right - work_left)
        px_width = int(min(max(360, work_width * 0.36), 620))
        text_px = px_width - 22  # 正文区左右内边距

        window = tk.Toplevel(self.root)
        window.withdraw()
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=theme["card"])

        card = tk.Frame(window, bg=theme["card"])
        card.pack(fill="both", expand=True)

        # 左侧竖条：整卡高度的强调色
        tk.Frame(card, bg=accent, width=3).pack(side="left", fill="y")

        content = tk.Frame(card, bg=theme["card"])
        content.pack(side="left", fill="both", expand=True)

        header = tk.Frame(content, bg=theme["card"])
        header.pack(fill="x", padx=(12, 8), pady=(9, 7))
        title = meta or ("翻译失败" if error else "译文")
        title_label = tk.Label(
            header,
            text=title,
            bg=theme["card"],
            fg=theme["text_error"] if error else theme["text_muted"],
            font=meta_font,
            anchor="w",
            justify="left",
        )
        title_label.pack(side="left", fill="x", expand=True)

        def make_button(text: str, command) -> tk.Label:
            button = tk.Label(
                header,
                text=text,
                bg=theme["card"],
                fg=theme["text_muted"],
                font=meta_font,
                padx=7,
                pady=1,
                cursor="hand2",
            )
            button.pack(side="right", padx=(4, 0))
            button.bind("<Button-1>", command)
            button.bind(
                "<Enter>",
                lambda _e: button.configure(bg=theme["hover_bg"], fg=theme["text_main"]),
            )
            button.bind(
                "<Leave>",
                lambda _e: button.configure(bg=theme["card"], fg=theme["text_muted"]),
            )
            return button

        make_button("✕", lambda _e: self.dismiss())
        # 复制动作要用到后面才生成的译文，这里先占位、稍后重新绑定
        copy_button = (
            make_button("复制", lambda _e: None) if state == "result" else None
        )

        tk.Frame(content, bg=theme["hairline"], height=1).pack(fill="x")

        if source.strip():
            excerpt = source.strip().replace("\r", "")
            if len(excerpt) > 180:
                excerpt = excerpt[:180] + "…"
            tk.Label(
                content,
                text=excerpt,
                bg=theme["card"],
                fg=theme["text_source"],
                font=source_font,
                justify="left",
                anchor="w",
                wraplength=px_width - 30,
            ).pack(fill="x", padx=(12, 12), pady=(8, 0))

        text_body = body.strip()
        widths = self._char_widths.setdefault(size, {})
        estimated_lines = _wrapped_line_count(text_body, body_font, text_px, widths)
        needs_scrollbar = estimated_lines > 14
        if needs_scrollbar:
            estimated_lines = _wrapped_line_count(text_body, body_font, text_px - 16, widths)
        visible_lines = max(2, min(14, estimated_lines))

        body_row = tk.Frame(content, bg=theme["card"])
        body_row.pack(fill="both", expand=True, padx=(12, 10), pady=(7, 10))
        text_area = tk.Text(
            body_row,
            wrap="word",
            font=body_font,
            bg=theme["card"],
            fg=theme["text_error"] if error else theme["text_main"],
            relief="flat",
            highlightthickness=0,
            borderwidth=0,
            width=1,  # 实际宽度由窗口几何决定，这里只占位
            height=visible_lines,
            padx=0,
            pady=0,
            spacing1=1,
            spacing3=4,
            cursor="arrow",
            insertwidth=0,
            selectbackground=theme["select_bg"],
            selectforeground=theme["text_main"],
        )
        text_area.insert("1.0", text_body)
        text_area.configure(state="disabled")
        text_area.pack(side="left", fill="both", expand=True)
        if needs_scrollbar:
            scrollbar = tk.Scrollbar(
                body_row,
                command=text_area.yview,
                width=8,
                bg=theme["scroll_bg"],
                troughcolor=theme["scroll_trough"],
                activebackground=theme["text_muted"],
                borderwidth=0,
                highlightthickness=0,
            )
            scrollbar.pack(side="right", fill="y", padx=(6, 0))
            text_area.configure(yscrollcommand=scrollbar.set)

        if copy_button is not None:
            def do_copy(_event: object = None) -> None:
                def finished(ok: bool) -> None:
                    if not ok or not self.visible:
                        return
                    copy_button.configure(text="已复制", fg=theme["accent"])
                    try:
                        window.after(
                            1200,
                            lambda: copy_button.configure(
                                text="复制", fg=theme["text_muted"]
                            ),
                        )
                    except tk.TclError:
                        pass

                if self.copy_text is not None:
                    # 写剪贴板可能被别的程序阻塞，交给工作线程做
                    self.copy_text(text_body, finished)
                else:
                    finished(native.clipboard_set_text(text_body))

            copy_button.bind("<Button-1>", do_copy)

        # 拖动：按住标题栏移动弹窗
        for widget in (header, title_label):
            widget.bind("<Button-1>", lambda event: self._start_drag(event, window))
            widget.bind("<B1-Motion>", self._on_drag)

        window.update_idletasks()
        width = px_width
        height = window.winfo_reqheight()
        pos_x = int(min(max(work_left + 4, x + 14), work_right - width - 4))
        pos_y = int(min(max(work_top + 4, y + 18), work_bottom - height - 4))
        window.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

        hwnd = int(window.wm_frame(), 16)
        _round_corners(hwnd)
        native.set_no_activate(hwnd)
        window.deiconify()

        self.window = window
        self._log(f"弹窗：渲染完成 {width}x{height} @ ({pos_x},{pos_y})")
        self._schedule_auto_close()
        # 只认窗口本身的进出：子控件的 Enter/Leave 会冒泡到窗口绑定上，
        # 否则鼠标在弹窗内移动就会反复重排自动关闭定时器。
        window.bind("<Enter>", lambda event: self._on_pointer_enter(event, window))
        window.bind("<Leave>", lambda event: self._on_pointer_leave(event, window))

    def _on_pointer_enter(self, event: tk.Event, window: tk.Toplevel) -> None:
        if event.widget is window:
            self._cancel_auto_close()

    def _on_pointer_leave(self, event: tk.Event, window: tk.Toplevel) -> None:
        if event.widget is window:
            self._schedule_auto_close()

    # --- 拖动 -------------------------------------------------------
    def _start_drag(self, event: tk.Event, window: tk.Toplevel) -> None:
        self._drag_offset = (event.x_root - window.winfo_x(), event.y_root - window.winfo_y())

    def _on_drag(self, event: tk.Event) -> None:
        if not self.visible:
            return
        window = self.window
        assert window is not None
        offset_x, offset_y = self._drag_offset
        window.geometry(f"+{event.x_root - offset_x}+{event.y_root - offset_y}")

    # --- 自动关闭 ---------------------------------------------------
    def _schedule_auto_close(self) -> None:
        self._cancel_auto_close()
        seconds = self._auto_close_override
        if seconds is None:
            seconds = self.config.get("ui", "popup_auto_close", 8)
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            seconds = 8.0
        if seconds <= 0 or not self.visible:
            return
        self._log(f"弹窗：{seconds:g}s 后自动关闭")
        window = self.window
        assert window is not None
        self._auto_close_job = window.after(int(seconds * 1000), self.hide)

    def _cancel_auto_close(self) -> None:
        if self._auto_close_job and self.visible:
            window = self.window
            assert window is not None
            try:
                window.after_cancel(self._auto_close_job)
            except (tk.TclError, ValueError):
                pass
        self._auto_close_job = None
