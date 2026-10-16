"""设置窗口：大模型配置、翻译规则、通用选项。"""
from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

from . import config as config_module
from .config import DEFAULT_SYSTEM_PROMPT, Config, language_label
from .translator import PRESET_MODELS

SOURCE_CHOICES = [
    ("auto", "自动识别"),
    ("zh", "中文/日文汉字"),
    ("ja", "日语"),
    ("ko", "韩语"),
    ("en", "英语等拉丁文字"),
    ("ru", "俄语"),
    ("ar", "阿拉伯语"),
    ("th", "泰语"),
]

TARGET_CHOICES = [
    (code, label)
    for code, label in config_module.LANGUAGE_LABELS.items()
    if code != "auto"
]

RESTORE_CHOICES = [
    ("auto", "智能（剪贴板为纯文本时才还原）"),
    ("always", "总是还原原剪贴板文本"),
    ("never", "不还原（保留复制的文本）"),
]


def _code_of(label: str) -> Optional[str]:
    for code, text in config_module.LANGUAGE_LABELS.items():
        if text == label:
            return code
    return None


class RuleDialog:
    """新增 / 编辑单条翻译规则。"""

    def __init__(self, parent: tk.Misc, rule: Optional[Dict[str, Any]] = None) -> None:
        self.result: Optional[Dict[str, Any]] = None
        rule = rule or {"source": "auto", "target": "zh"}

        self.window = tk.Toplevel(parent)
        self.window.title("翻译规则")
        self.window.transient(parent)
        self.window.resizable(False, False)

        body = ttk.Frame(self.window, padding=12)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="当识别到的原文语言为").grid(row=0, column=0, sticky="w", pady=4)
        self.source_var = tk.StringVar(value=language_label(str(rule.get("source", "auto"))))
        source_box = ttk.Combobox(
            body,
            textvariable=self.source_var,
            state="readonly",
            width=26,
            values=[label for _code, label in SOURCE_CHOICES],
        )
        source_box.grid(row=0, column=1, sticky="ew", pady=4, padx=(8, 0))

        ttk.Label(body, text="则翻译为").grid(row=1, column=0, sticky="w", pady=4)
        self.target_var = tk.StringVar(
            value=language_label(str(rule.get("target", "zh"))) or str(rule.get("target", ""))
        )
        target_box = ttk.Combobox(
            body,
            textvariable=self.target_var,
            width=26,
            values=[label for _code, label in TARGET_CHOICES],
        )
        target_box.grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))

        ttk.Label(
            body,
            text="提示：目标语言可自定义输入，例如“文言文”“繁体中文”。\n"
            "规则自上而下匹配，第一条命中的生效。",
            foreground="#6B7280",
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 4))

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="确定", command=self._confirm).pack(side="right")
        ttk.Button(buttons, text="取消", command=self.window.destroy).pack(
            side="right", padx=(0, 8)
        )

        self.window.bind("<Return>", lambda _event: self._confirm())
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.grab_set()
        target_box.focus_set()

    def _confirm(self) -> None:
        source_label = self.source_var.get().strip()
        target_text = self.target_var.get().strip()
        source = _code_of(source_label) or "auto"
        if not target_text:
            messagebox.showwarning("翻译规则", "请填写目标语言。", parent=self.window)
            return
        target = _code_of(target_text) or target_text
        self.result = {"source": source, "target": target}
        self.window.destroy()


class SettingsWindow:
    def __init__(
        self,
        root: tk.Misc,
        config: Config,
        on_apply: Callable[[], None],
    ) -> None:
        self.root = root
        self.config = config
        self.on_apply = on_apply
        self.window: Optional[tk.Toplevel] = None
        self._rules: List[Dict[str, Any]] = [dict(item) for item in config.rules]

    # --- 生命周期 ---------------------------------------------------
    def show(self) -> None:
        if self.window is not None and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            self.window.focus_force()
            return
        self._build()

    def _build(self) -> None:
        model = self.config.section("model")
        rules = self.config.section("rules")
        trigger = self.config.section("trigger")
        ui = self.config.section("ui")

        window = tk.Toplevel(self.root)
        self.window = window
        window.title("Trans 设置")
        window.minsize(500, 450)
        window.protocol("WM_DELETE_WINDOW", self._on_close)

        notebook = ttk.Notebook(window)
        notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        # ---------------- 模型 ----------------
        model_tab = ttk.Frame(notebook, padding=12)
        notebook.add(model_tab, text="大模型")
        model_tab.columnconfigure(1, weight=1)

        self.var_base_url = tk.StringVar(value=model.get("base_url", ""))
        self.var_api_key = tk.StringVar(value=model.get("api_key", ""))
        self.var_model = tk.StringVar(value=model.get("model", "deepseek-chat"))
        self.var_temperature = tk.StringVar(value=str(model.get("temperature", 1.3)))
        self.var_timeout = tk.StringVar(value=str(model.get("timeout", 20)))

        self._row(model_tab, 0, "接口地址", ttk.Entry(model_tab, textvariable=self.var_base_url))
        key_frame = ttk.Frame(model_tab)
        key_entry = ttk.Entry(key_frame, textvariable=self.var_api_key, show="*")
        key_entry.pack(side="left", fill="x", expand=True)
        show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            key_frame,
            text="显示",
            variable=show_key,
            command=lambda: key_entry.configure(show="" if show_key.get() else "*"),
        ).pack(side="left", padx=(6, 0))
        self._row(model_tab, 1, "API Key", key_frame)

        model_box = ttk.Combobox(
            model_tab,
            textvariable=self.var_model,
            values=[name for name, _desc in PRESET_MODELS],
        )
        self._row(model_tab, 2, "模型", model_box)
        self.model_box = model_box
        self._row(
            model_tab,
            3,
            "温度",
            ttk.Spinbox(
                model_tab,
                textvariable=self.var_temperature,
                from_=0.0,
                to=2.0,
                increment=0.1,
                width=10,
            ),
            sticky="w",
        )
        self._row(
            model_tab,
            4,
            "超时（秒）",
            ttk.Spinbox(
                model_tab,
                textvariable=self.var_timeout,
                from_=5,
                to=120,
                increment=5,
                width=10,
            ),
            sticky="w",
        )

        ttk.Label(model_tab, text="翻译提示词").grid(
            row=5, column=0, sticky="nw", pady=4, padx=(0, 8)
        )
        prompt_frame = ttk.Frame(model_tab)
        prompt_frame.grid(row=5, column=1, sticky="nsew", pady=4)
        prompt_frame.columnconfigure(0, weight=1)
        model_tab.rowconfigure(5, weight=1)
        self.prompt_text = tk.Text(
            prompt_frame, width=36, height=6, wrap="word", font=("Microsoft YaHei UI", 10)
        )
        self.prompt_text.insert("1.0", model.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        self.prompt_text.grid(row=0, column=0, sticky="nsew")
        prompt_scroll = ttk.Scrollbar(prompt_frame, command=self.prompt_text.yview)
        prompt_scroll.grid(row=0, column=1, sticky="ns")
        self.prompt_text.configure(yscrollcommand=prompt_scroll.set)
        ttk.Label(
            model_tab,
            text="{target} 会被替换为目标语言名称。",
            foreground="#6B7280",
        ).grid(row=6, column=1, sticky="w")

        # ---------------- 规则 ----------------
        rules_tab = ttk.Frame(notebook, padding=12)
        notebook.add(rules_tab, text="翻译规则")
        rules_tab.columnconfigure(0, weight=1)
        rules_tab.rowconfigure(0, weight=1)

        self.rules_tree = ttk.Treeview(
            rules_tab, columns=("source", "target"), show="headings", height=8
        )
        self.rules_tree.heading("source", text="识别到的原文语言")
        self.rules_tree.heading("target", text="翻译为")
        self.rules_tree.column("source", width=150, anchor="w")
        self.rules_tree.column("target", width=150, anchor="w")
        self.rules_tree.grid(row=0, column=0, sticky="nsew")
        rules_scroll = ttk.Scrollbar(rules_tab, command=self.rules_tree.yview)
        rules_scroll.grid(row=0, column=1, sticky="ns")
        self.rules_tree.configure(yscrollcommand=rules_scroll.set)
        self.rules_tree.bind("<Double-1>", lambda _event: self._edit_rule())

        rule_buttons = ttk.Frame(rules_tab)
        rule_buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        for text, command in (
            ("添加", self._add_rule),
            ("编辑", self._edit_rule),
            ("删除", self._remove_rule),
            ("上移", lambda: self._move_rule(-1)),
            ("下移", lambda: self._move_rule(1)),
        ):
            ttk.Button(rule_buttons, text=text, width=8, command=command).pack(
                side="left", padx=(0, 6)
            )

        options = ttk.Frame(rules_tab)
        options.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(options, text="最长翻译字符数").pack(side="left")
        self.var_max_chars = tk.StringVar(value=str(rules.get("max_chars", 3000)))
        ttk.Spinbox(
            options,
            textvariable=self.var_max_chars,
            from_=50,
            to=20000,
            increment=50,
            width=8,
        ).pack(side="left", padx=(6, 0))

        # ---------------- 通用 ----------------
        general_tab = ttk.Frame(notebook, padding=12)
        notebook.add(general_tab, text="通用")
        general_tab.columnconfigure(1, weight=1)

        self.var_enabled = tk.BooleanVar(value=bool(trigger.get("enabled", True)))
        self.var_mouse = tk.BooleanVar(value=bool(trigger.get("mouse_selection", True)))
        self.var_hotkey = tk.StringVar(value=trigger.get("hotkey", "Ctrl+Alt+T"))
        self.var_restore = tk.StringVar(
            value=dict((code, text) for code, text in RESTORE_CHOICES).get(
                str(trigger.get("restore_clipboard", "auto")), RESTORE_CHOICES[0][1]
            )
        )
        self.var_require_ctrl = tk.BooleanVar(
            value=bool(trigger.get("require_ctrl", True))
        )
        self.var_min_drag = tk.StringVar(value=str(trigger.get("min_drag_px", 4)))
        self.var_delay = tk.StringVar(value=str(trigger.get("copy_delay_ms", 130)))
        self.var_auto_close = tk.StringVar(value=str(ui.get("popup_auto_close", 8)))
        self.var_font_size = tk.StringVar(value=str(ui.get("font_size", 11)))
        self.var_show_source = tk.BooleanVar(value=bool(ui.get("show_source", True)))
        self.var_debug = tk.BooleanVar(value=bool(self.config.data.get("debug", False)))

        ttk.Checkbutton(general_tab, text="启用取词翻译", variable=self.var_enabled).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=4
        )
        ttk.Checkbutton(
            general_tab, text="鼠标划选后自动翻译", variable=self.var_mouse
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(
            general_tab, text="仅按住 Ctrl 划选时翻译", variable=self.var_require_ctrl
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        self._row(
            general_tab,
            3,
            "取词快捷键",
            ttk.Entry(general_tab, textvariable=self.var_hotkey, width=24),
        )
        restore_box = ttk.Combobox(
            general_tab,
            textvariable=self.var_restore,
            state="readonly",
            values=[text for _code, text in RESTORE_CHOICES],
            width=24,
        )
        self._row(general_tab, 4, "剪贴板还原", restore_box)
        self._row(
            general_tab,
            5,
            "最小划选距离（像素）",
            ttk.Spinbox(
                general_tab, textvariable=self.var_min_drag, from_=2, to=60, width=8
            ),
            sticky="w",
        )
        self._row(
            general_tab,
            6,
            "复制前延迟（毫秒）",
            ttk.Spinbox(
                general_tab, textvariable=self.var_delay, from_=0, to=1000, increment=10, width=8
            ),
            sticky="w",
        )
        self._row(
            general_tab,
            7,
            "弹窗自动关闭（秒，0 不关）",
            ttk.Spinbox(
                general_tab, textvariable=self.var_auto_close, from_=0, to=120, width=8
            ),
            sticky="w",
        )
        self._row(
            general_tab,
            8,
            "字号",
            ttk.Spinbox(general_tab, textvariable=self.var_font_size, from_=8, to=24, width=8),
            sticky="w",
        )
        ttk.Checkbutton(
            general_tab, text="弹窗中显示原文", variable=self.var_show_source
        ).grid(row=9, column=1, sticky="w", pady=4)
        ttk.Checkbutton(general_tab, text="记录调试日志", variable=self.var_debug).grid(
            row=10, column=1, sticky="w", pady=4
        )

        general_buttons = ttk.Frame(general_tab)
        general_buttons.grid(row=11, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Button(general_buttons, text="打开配置目录", command=self._open_config_dir).pack(
            side="left"
        )
        ttk.Button(general_buttons, text="打开日志", command=self._open_log).pack(
            side="left", padx=(8, 0)
        )

        # ---------------- 底部按钮 ----------------
        footer = ttk.Frame(window, padding=10)
        footer.pack(fill="x")
        ttk.Label(
            footer,
            text="配置保存在 %APPDATA%\\Trans\\config.json",
            foreground="#6B7280",
        ).pack(side="left")
        ttk.Button(footer, text="关闭", command=self._on_close).pack(side="right")
        ttk.Button(footer, text="保存并应用", command=self._save).pack(
            side="right", padx=(0, 8)
        )

        self._render_rules()
        self._center(window)

    @staticmethod
    def _row(
        parent: tk.Misc, row: int, label: str, widget: tk.Widget, sticky: str = "ew"
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 8))
        widget.grid(row=row, column=1, sticky=sticky, pady=4)

    @staticmethod
    def _center(window: tk.Toplevel) -> None:
        window.update_idletasks()
        width = window.winfo_width() or 640
        height = window.winfo_height() or 520
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 3)
        window.geometry(f"+{x}+{y}")

    # --- 规则操作 ---------------------------------------------------
    def _render_rules(self) -> None:
        self.rules_tree.delete(*self.rules_tree.get_children())
        for index, rule in enumerate(self._rules):
            source = language_label(str(rule.get("source", "auto")))
            target = language_label(str(rule.get("target", ""))) or str(rule.get("target", ""))
            self.rules_tree.insert("", "end", iid=str(index), values=(source, target))

    def _selected_rule_index(self) -> Optional[int]:
        selection = self.rules_tree.selection()
        if not selection:
            return None
        return int(selection[0])

    def _add_rule(self) -> None:
        dialog = RuleDialog(self.window)
        self.window.wait_window(dialog.window)
        if dialog.result:
            self._rules.append(dialog.result)
            self._render_rules()

    def _edit_rule(self) -> None:
        index = self._selected_rule_index()
        if index is None:
            return
        dialog = RuleDialog(self.window, self._rules[index])
        self.window.wait_window(dialog.window)
        if dialog.result:
            self._rules[index] = dialog.result
            self._render_rules()

    def _remove_rule(self) -> None:
        index = self._selected_rule_index()
        if index is None:
            return
        del self._rules[index]
        self._render_rules()

    def _move_rule(self, delta: int) -> None:
        index = self._selected_rule_index()
        if index is None:
            return
        target = index + delta
        if not 0 <= target < len(self._rules):
            return
        self._rules[index], self._rules[target] = self._rules[target], self._rules[index]
        self._render_rules()
        self.rules_tree.selection_set(str(target))

    # --- 采集与保存 -------------------------------------------------
    def _collect_model(self) -> Dict[str, Any]:
        return {
            "base_url": self.var_base_url.get().strip(),
            "api_key": self.var_api_key.get().strip(),
            "model": self.var_model.get().strip() or "deepseek-chat",
            "temperature": self._to_float(self.var_temperature.get(), 1.3),
            "timeout": self._to_float(self.var_timeout.get(), 20.0),
            "system_prompt": self.prompt_text.get("1.0", "end").strip() or DEFAULT_SYSTEM_PROMPT,
        }

    @staticmethod
    def _to_float(text: str, default: float) -> float:
        try:
            return float(str(text).strip())
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_int(text: str, default: int) -> int:
        try:
            return int(float(str(text).strip()))
        except (TypeError, ValueError):
            return default

    def _collect(self) -> Dict[str, Any]:
        restore = _code_of(self.var_restore.get()) or "auto"
        return {
            "model": self._collect_model(),
            "rules": {
                "items": [dict(item) for item in self._rules],
                "max_chars": max(50, self._to_int(self.var_max_chars.get(), 3000)),
            },
            "trigger": {
                "enabled": bool(self.var_enabled.get()),
                "mouse_selection": bool(self.var_mouse.get()),
                "require_ctrl": bool(self.var_require_ctrl.get()),
                "hotkey": self.var_hotkey.get().strip() or "Ctrl+Alt+T",
                "min_drag_px": max(2, self._to_int(self.var_min_drag.get(), 6)),
                "copy_delay_ms": max(0, self._to_int(self.var_delay.get(), 130)),
                "restore_clipboard": restore,
            },
            "ui": {
                "popup_auto_close": max(0, self._to_int(self.var_auto_close.get(), 8)),
                "font_size": max(8, self._to_int(self.var_font_size.get(), 11)),
                "show_source": bool(self.var_show_source.get()),
            },
            "debug": bool(self.var_debug.get()),
        }

    def _save(self) -> bool:
        from .native import parse_hotkey

        collected = self._collect()
        hotkey = collected["trigger"]["hotkey"]
        if not parse_hotkey(hotkey):
            messagebox.showwarning(
                "Trans 设置",
                f"快捷键格式无效：{hotkey}\n示例：Ctrl+Alt+T、Ctrl+Shift+F2",
                parent=self.window,
            )
            return False
        for section, values in collected.items():
            if isinstance(values, dict):
                self.config.section(section).update(values)
            else:
                self.config.data[section] = values
        self.config.save()
        self.on_apply()
        return True

    def _on_close(self) -> None:
        if self._has_changes():
            answer = messagebox.askyesnocancel(
                "Trans 设置", "有未保存的修改，是否保存？", parent=self.window
            )
            if answer is None:
                return
            if answer and not self._save():
                return
        self.destroy()

    def _has_changes(self) -> bool:
        collected = self._collect()
        for section, values in collected.items():
            current = self.config.data.get(section)
            if isinstance(values, dict):
                if any(current.get(key) != value for key, value in values.items()):
                    return True
            elif current != values:
                return True
        return False

    def destroy(self) -> None:
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None

    # --- 其他 -------------------------------------------------------
    @staticmethod
    def _open_config_dir() -> None:
        try:
            os.startfile(config_module.CONFIG_DIR)  # type: ignore[attr-defined]
        except OSError:
            webbrowser.open(config_module.CONFIG_DIR)

    @staticmethod
    def _open_log() -> None:
        if os.path.isfile(config_module.LOG_PATH):
            try:
                os.startfile(config_module.LOG_PATH)  # type: ignore[attr-defined]
                return
            except OSError:
                pass
        messagebox.showinfo("Trans 设置", "暂无日志文件。")
