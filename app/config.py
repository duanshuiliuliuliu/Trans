"""配置读写：%APPDATA%\\Trans\\config.json，API Key 以 DPAPI 加密存储。"""
from __future__ import annotations

import base64
import copy
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from . import APP_NAME, native

CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
LOG_PATH = os.path.join(CONFIG_DIR, "trans.log")

DEFAULT_SYSTEM_PROMPT = (
    "你是一名专业翻译。请把用户提供的文本翻译成{target}。"
    "只输出译文本身，不要输出原文、解释、拼音或引号；保留原文的段落与换行结构。"
)

DEFAULTS: Dict[str, Any] = {
    "model": {
        # DeepSeek 接口（OpenAI 兼容）
        "base_url": "https://api.deepseek.com",
        "api_key": "",
        "api_key_encrypted": False,
        "model": "deepseek-flash",
        "temperature": 1.3,
        "timeout": 20,
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
    },
    "rules": {
        "items": [
            {"source": "zh", "target": "en"},
            {"source": "auto", "target": "zh"},
        ],
        "max_chars": 3000,
    },
    "trigger": {
        "enabled": True,
        "mouse_selection": True,
        # True：按住 Ctrl 划选/双击才翻译；False：任意选中都翻译
        "require_ctrl": True,
        "hotkey": "Ctrl+Alt+T",
        "min_drag_px": 4,
        "copy_delay_ms": 130,
        # auto：剪贴板只含纯文本时才还原；always：总是还原文本；never：不还原
        "restore_clipboard": "auto",
    },
    "ui": {
        "popup_auto_close": 8,
        "font_size": 11,
        "show_source": True,
        "hint_shown": False,
    },
    "debug": False,
}

LANGUAGE_LABELS = {
    "auto": "自动识别",
    "zh": "中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "ru": "俄语",
    "ar": "阿拉伯语",
    "pt": "葡萄牙语",
    "it": "意大利语",
    "th": "泰语",
}


def language_label(code: str) -> str:
    return LANGUAGE_LABELS.get(code, code or "")


def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """线程安全的配置对象，内存中始终保留明文 API Key。"""

    def __init__(self, data: Optional[Dict[str, Any]] = None, path: str = CONFIG_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.data: Dict[str, Any] = _merge(DEFAULTS, data or {})

    # --- 读写 -------------------------------------------------------
    @classmethod
    def load(cls, path: str = CONFIG_PATH) -> "Config":
        raw: Dict[str, Any] = {}
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle) or {}
            except (OSError, ValueError):
                raw = {}
        config = cls(raw, path)
        config._decrypt_api_key()
        return config

    def save(self) -> None:
        with self._lock:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            payload = copy.deepcopy(self.data)
            key = self.get("model", "api_key", "") or ""
            if key:
                protected = native.dpapi_encrypt(key)
                if protected is not None:
                    payload["model"]["api_key"] = base64.b64encode(protected).decode("ascii")
                    payload["model"]["api_key_encrypted"] = True
            temp_path = self.path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.path)

    def _decrypt_api_key(self) -> None:
        model = self.data.setdefault("model", {})
        stored = model.get("api_key") or ""
        if not stored:
            return
        if not model.get("api_key_encrypted"):
            return  # 明文（用户手工编辑过配置文件）
        try:
            raw = base64.b64decode(stored)
        except (ValueError, TypeError):
            model["api_key"] = ""
            return
        plain = native.dpapi_decrypt(raw)
        model["api_key"] = plain or ""

    # --- 访问 -------------------------------------------------------
    def get(self, section: str, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        with self._lock:
            self.data.setdefault(section, {})[key] = value

    def section(self, name: str) -> Dict[str, Any]:
        with self._lock:
            return self.data.setdefault(name, {})

    @property
    def rules(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self.data.setdefault("rules", {}).setdefault("items", [])

    def replace_rules(self, items: List[Dict[str, Any]]) -> None:
        with self._lock:
            self.data.setdefault("rules", {})["items"] = [dict(item) for item in items]

    # --- 日志 -------------------------------------------------------
    @staticmethod
    def log(message: str) -> None:
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            if os.path.isfile(LOG_PATH) and os.path.getsize(LOG_PATH) > 512 * 1024:
                os.replace(LOG_PATH, LOG_PATH + ".1")
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(LOG_PATH, "a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}] {message}\n")
        except OSError:
            pass
