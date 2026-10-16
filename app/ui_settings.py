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
    (code, label)
    for code, label in config_module.LANGUAGE_LABELS.items()
]

TARGET_CHOICES = [
    (code, label)
    for code, label in config_module.LANGUAGE_LABELS.items()
    if code != "auto"
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
            height=16,
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
            height=16,
            values=[label for _code, label in TARGET_CHOICES],
        )
        target_box.grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
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
    def _sync_mode_state(self) -> None:
        """总开关关闭时，两种取词方式不可选。"""
        state = "normal" if self.var_enabled.get() else "disabled"
        for radio in (self.mode_any, self.mode_ctrl):
            radio.configure(state=state)

    def sync_enabled(self, enabled: bool) -> None:
        """托盘菜单切换启用状态后，同步到已打开的设置窗口。"""
        if self.window is not None and self.window.winfo_exists():
            self.var_enabled.set(bool(enabled))
            self._sync_mode_state()

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
        window.resizable(False, False)  # 固定大小，避免布局被拉花
        window.protocol("WM_DELETE_WINDOW", self._on_close)

        notebook = ttk.Notebook(window)
        notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        # ---------------- 模型 ----------------
        model_tab = ttk.Frame(notebook, padding=12)
        notebook.add(model_tab, text="大模型")
        model_tab.columnconfigure(1, weight=1)

        self.var_base_url = tk.StringVar(value=model.get("base_url", ""))
        self.var_api_key = tk.StringVar(value=model.get("api_key", ""))
        self.var_model = tk.StringVar(value=model.get("model", "deepseek-flash"))
        self.var_temperature = tk.StringVar(value=str(model.get("temperature", 0.3)))
        self.var_thinking = tk.BooleanVar(value=bool(model.get("thinking", False)))
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
        ttk.Checkbutton(
            model_tab,
            text="翻译前先推理（质量略好，实测每次约慢 1 秒）",
            variable=self.var_thinking,
        ).grid(row=3, column=1, sticky="w", pady=(0, 2))
        self._row(
            model_tab,
            4,
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
            5,
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
            row=6, column=0, sticky="nw", pady=4, padx=(0, 8)
        )
        prompt_frame = ttk.Frame(model_tab)
        prompt_frame.grid(row=6, column=1, sticky="nsew", pady=4)
        prompt_frame.columnconfigure(0, weight=1)
        model_tab.rowconfigure(6, weight=1)
        self.prompt_text = tk.Text(
            prompt_frame, width=36, height=6, wrap="word", font=("Microsoft YaHei UI", 10)
        )
        self.prompt_text.insert("1.0", model.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        self.prompt_text.grid(row=0, column=0, sticky="nsew")
        prompt_scroll = ttk.Scrollbar(prompt_frame, command=self.prompt_text.yview)
        prompt_scroll.grid(row=0, column=1, sticky="ns")
        self.prompt_text.configure(yscrollcommand=prompt_scroll.set)
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
        self.var_mode = tk.StringVar(
            value="ctrl" if bool(trigger.get("require_ctrl", True)) else "any"
        )
        self.var_auto_close = tk.StringVar(value=str(ui.get("popup_auto_close", 8)))
        self.var_font_size = tk.StringVar(value=str(ui.get("font_size", 11)))
        self.var_show_source = tk.BooleanVar(value=bool(ui.get("show_source", True)))

        ttk.Checkbutton(
            general_tab,
            text="启用取词翻译",
            variable=self.var_enabled,
            command=self._sync_mode_state,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(4, 6))
        self.mode_any = ttk.Radiobutton(
            general_tab, text="鼠标划选后自动翻译", value="any", variable=self.var_mode
        )
        self.mode_any.grid(row=1, column=0, columnspan=2, sticky="w", padx=(20, 0), pady=3)
        self.mode_ctrl = ttk.Radiobutton(
            general_tab, text="仅按住 Ctrl 划选时翻译", value="ctrl", variable=self.var_mode
        )
        self.mode_ctrl.grid(row=2, column=0, columnspan=2, sticky="w", padx=(20, 0), pady=3)
        self._sync_mode_state()

        ttk.Checkbutton(general_tab, text="弹窗中显示原文", variable=self.var_show_source).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(14, 4)
        )
        self._row(
            general_tab,
            4,
            "弹窗自动关闭（秒，0 不关）",
            ttk.Spinbox(
                general_tab, textvariable=self.var_auto_close, from_=0, to=120, width=8
            ),
            sticky="w",
        )
        self._row(
            general_tab,
            5,
            "字号",
            ttk.Spinbox(general_tab, textvariable=self.var_font_size, from_=8, to=24, width=8),
            sticky="w",
        )

        general_buttons = ttk.Frame(general_tab)
        general_buttons.grid(row=6, column=0, columnspan=2, sticky="w", pady=(14, 0))
        ttk.Button(general_buttons, text="打开配置目录", command=self._open_config_dir).pack(
            side="left"
        )
        ttk.Button(general_buttons, text="打开日志", command=self._open_log).pack(
            side="left", padx=(8, 0)
        )

        # ---------------- 底部按钮 ----------------
        footer = ttk.Frame(window, padding=10)
        footer.pack(fill="x")
        ttk.Button(footer, text="关闭", command=self._on_close).pack(side="right")
        ttk.Button(footer, text="保存并应用", command=self._save).pack(
            side="right", padx=(0, 8)
        )

        # 按使用频率排列页签：通用 / 翻译规则 / 大模型
        tabs = [(general_tab, "通用"), (rules_tab, "翻译规则"), (model_tab, "大模型")]
        for tab, _label in tabs:
            notebook.forget(tab)
        for tab, label in tabs:
            notebook.add(tab, text=label)
        notebook.select(general_tab)

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
        """固定窗口尺寸并居中（尺寸取各页签的最大需求）。"""
        window.update_idletasks()
        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 3)
        window.geometry(f"{width}x{height}+{x}+{y}")

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
            "model": self.var_model.get().strip() or "deepseek-flash",
            "thinking": bool(self.var_thinking.get()),
            "temperature": self._to_float(self.var_temperature.get(), 0.3),
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
        return {
            "model": self._collect_model(),
            "rules": {
                "items": [dict(item) for item in self._rules],
                "max_chars": max(50, self._to_int(self.var_max_chars.get(), 3000)),
            },
            "trigger": {
                "enabled": bool(self.var_enabled.get()),
                "require_ctrl": self.var_mode.get() == "ctrl",
            },
            "ui": {
                "popup_auto_close": max(0, self._to_int(self.var_auto_close.get(), 8)),
                "font_size": max(8, self._to_int(self.var_font_size.get(), 11)),
                "show_source": bool(self.var_show_source.get()),
            },
        }

    def _save(self) -> bool:
        collected = self._collect()
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
        if os.path.isfile(config_module.CRASH_LOG_PATH):
            os.startfile(config_module.CRASH_LOG_PATH)  # type: ignore[attr-defined]
            return
        messagebox.showinfo("Trans 设置", "暂无日志文件。")
