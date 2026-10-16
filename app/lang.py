"""语言检测与翻译规则匹配（纯本地计算，不消耗接口调用）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .config import language_label

# Unicode 区间 -> 语言代码
_RANGES: Tuple[Tuple[int, int, str], ...] = (
    (0x3040, 0x30FF, "ja"),  # 平假名 / 片假名
    (0xAC00, 0xD7AF, "ko"),  # 谚文
    (0x4E00, 0x9FFF, "zh"),  # CJK 基本区
    (0x3400, 0x4DBF, "zh"),  # CJK 扩展 A
    (0xF900, 0xFAFF, "zh"),  # CJK 兼容
    (0x0400, 0x04FF, "ru"),  # 西里尔
    (0x0600, 0x06FF, "ar"),  # 阿拉伯
    (0x0E00, 0x0E7F, "th"),  # 泰文
)


def detect_language(text: str) -> str:
    """粗略判断文本主语言，返回语言代码；无法判断时返回 'unknown'。"""
    counts: Dict[str, int] = {}
    latin = 0
    total = 0
    for char in text or "":
        code = ord(char)
        if char.isalpha():
            total += 1
            matched = None
            for start, end, lang in _RANGES:
                if start <= code <= end:
                    matched = lang
                    break
            if matched is None:
                if code < 0x0250:
                    latin += 1
                    continue
                matched = "other"
            counts[matched] = counts.get(matched, 0) + 1
        elif char.isdigit():
            total += 1
    if total == 0:
        return "unknown"

    kana = counts.get("ja", 0)
    hangul = counts.get("ko", 0)
    if kana:
        return "ja"
    if hangul and hangul / total >= 0.2:
        return "ko"
    if counts.get("zh"):
        return "zh"
    for lang in ("ru", "ar", "th"):
        if counts.get(lang):
            return lang
    if latin:
        return "en"
    if counts.get("other"):
        return "unknown"
    return "unknown"


def pick_target(
    text: str, rules: List[Dict[str, Any]], fallback: str = "zh"
) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """按规则表选出目标语言。

    返回 (检测到的源语言, 目标语言代码或名称, 命中的规则)。
    """
    detected = detect_language(text)
    for rule in rules or []:
        source = str(rule.get("source") or "auto").lower()
        target = str(rule.get("target") or "").strip()
        if not target:
            continue
        if source in ("auto", "*", "") or source == detected:
            return detected, target, rule
    return detected, fallback, None


def target_display_name(target: str) -> str:
    """把目标语言代码转成提示词里用的名称，自定义名称原样返回。"""
    if not target:
        return language_label("zh")
    return language_label(target) or target
