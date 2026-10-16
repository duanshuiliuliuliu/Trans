"""语言识别与翻译规则匹配（本地计算，不消耗接口调用）。

识别能力分三层：
1. 按字符脚本判定（中日韩、希腊、希伯来、阿拉伯、天城文、泰文、西里尔…）；
2. 按特征字母判定拉丁语系中比较好认的几种（越南语、土耳其语、波兰语…）；
3. 判不出来就返回 "latin" / "unknown"，由模型按规则表自行路由（见 translator.build_messages）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .config import language_label

# 字符脚本 -> 语言代码
_SCRIPT_RANGES: Tuple[Tuple[int, int, str], ...] = (
    (0x3040, 0x30FF, "ja"),  # 平假名 / 片假名
    (0xAC00, 0xD7AF, "ko"),  # 谚文
    (0x1100, 0x11FF, "ko"),  # 谚文字母
    (0x4E00, 0x9FFF, "zh"),  # CJK 基本区
    (0x3400, 0x4DBF, "zh"),  # CJK 扩展 A
    (0xF900, 0xFAFF, "zh"),  # CJK 兼容
    (0x0370, 0x03FF, "el"),  # 希腊文
    (0x1F00, 0x1FFF, "el"),  # 希腊文扩展
    (0x0590, 0x05FF, "he"),  # 希伯来文
    (0x0600, 0x06FF, "ar"),  # 阿拉伯文（波斯语见特征字母）
    (0x0750, 0x077F, "ar"),  # 阿拉伯文扩展
    (0x0900, 0x097F, "hi"),  # 天城文
    (0x0980, 0x09FF, "bn"),  # 孟加拉文
    (0x0B80, 0x0BFF, "ta"),  # 泰米尔文
    (0x0E00, 0x0E7F, "th"),  # 泰文
    (0x0400, 0x04FF, "ru"),  # 西里尔字母
)

# 西里尔字母内部再细分
_CYRILLIC_MARKERS = (
    ("uk", "іїєґ"),
    ("sr", "ђћџ"),
    ("bg", ""),  # 保加利亚语无独有字母，保持俄语兜底
)

# 阿拉伯字母内部再细分（波斯语特有字母）
_PERSIAN_MARKERS = "پچژگ"

# 拉丁语系特征字母：score >= 2，或命中 strong 中任意一个即可判定
_LATIN_SIGNATURES: Dict[str, Tuple[str, str]] = {
    # strong 里的字母要求基本只有该语言使用：ơ ư 是越南语独有，ă/ê/ô 与罗马尼亚语、法语等共享
    "vi": ("ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ", "ơư"),
    "tr": ("ğışı", "ğı"),
    "pl": ("łąęśźćń", "łśę"),
    "cs": ("řěů", "řěů"),
    "hu": ("őű", "őű"),
    "ro": ("șț", "șț"),
    "is": ("þð", "þð"),
    "lv": ("āēģķļņ", "ģķļņ"),
    "lt": ("ėįų", "ė"),
    "pt": ("ãõ", "ã"),
}

_DETECTED_LABELS = {"latin": "拉丁文字", "unknown": "自动识别"}

# 拉丁字母系语言：本地只能靠特征字母偶尔认出，短文本常常认不出，需要模型兜底路由
LATIN_SCRIPT_LANGUAGES = {
    "en", "de", "fr", "es", "it", "nl", "ca", "pt", "sv", "no", "da", "fi", "is",
    "pl", "cs", "sk", "hu", "ro", "lv", "lt", "et", "hr", "sl", "sr", "bg", "vi",
    "tr", "id", "ms", "sq",
}


def needs_model_routing(rules: List[Dict[str, Any]]) -> bool:
    """规则表里是否含有本地识别不出的语种——有才值得把规则表交给模型。"""
    for rule in rules or []:
        source = str(rule.get("source") or "auto").lower()
        if source in LATIN_SCRIPT_LANGUAGES:
            return True
    return False


def detect_language(text: str) -> str:
    """粗略判断文本语言，返回语言代码；拉丁语系无法细分时返回 'latin'。

    只做高置信度判断，宁可返回 'latin'/'unknown' 交给模型，也不猜错语种。
    """
    counts: Dict[str, int] = {}
    latin_letters: List[str] = []
    total = 0
    for char in text or "":
        if not char.isalpha():
            if char.isdigit():
                total += 1
            continue
        total += 1
        code = ord(char)
        matched = None
        for start, end, lang in _SCRIPT_RANGES:
            if start <= code <= end:
                matched = lang
                break
        if matched is None:
            if code < 0x0250:  # 基本拉丁字母
                latin_letters.append(char)
                continue
            matched = "other"
        counts[matched] = counts.get(matched, 0) + 1
    if total == 0:
        return "unknown"

    if counts.get("ja"):
        return "ja"
    if counts.get("ko") and counts["ko"] / total >= 0.2:
        return "ko"
    if counts.get("zh"):
        return "zh"
    for lang in ("el", "he", "hi", "bn", "ta", "th"):
        if counts.get(lang):
            return lang
    if counts.get("ar"):
        lowered = text.lower()
        return "fa" if any(ch in lowered for ch in _PERSIAN_MARKERS) else "ar"
    if counts.get("ru"):
        lowered = text.lower()
        for code, markers in _CYRILLIC_MARKERS:
            if markers and any(ch in lowered for ch in markers):
                return code
        return "ru"
    if latin_letters:
        return _detect_latin("".join(latin_letters))
    if counts.get("other"):
        return "unknown"
    return "unknown"


def _detect_latin(letters: str) -> str:
    lowered = letters.lower()
    scores: Dict[str, int] = {}
    strong_hits: List[str] = []
    for code, (letters_set, strong) in _LATIN_SIGNATURES.items():
        score = sum(lowered.count(ch) for ch in letters_set)
        if not score:
            continue
        scores[code] = score
        if any(ch in lowered for ch in strong):
            strong_hits.append(code)
    if len(strong_hits) == 1:
        return strong_hits[0]  # 独有字母只命中一种语言，直接判定
    if not strong_hits and scores:
        best = max(scores, key=lambda key: scores[key])
        if scores[best] >= 2:
            return best
    return "latin"


def detected_label(code: str) -> str:
    """用于弹窗显示的语种名称。"""
    return _DETECTED_LABELS.get(code, language_label(code) or code)


def pick_target(
    text: str, rules: List[Dict[str, Any]], fallback: str = "zh"
) -> Tuple[str, str, Optional[Dict[str, Any]], bool]:
    """按规则表选出目标语言。

    返回 (识别到的源语言, 目标语言代码或名称, 命中的规则, 是否确信)。
    不确信时调用方应把规则表交给模型自行路由。
    """
    detected = detect_language(text)
    confident = detected not in ("latin", "unknown")
    for rule in rules or []:
        source = str(rule.get("source") or "auto").lower()
        target = str(rule.get("target") or "").strip()
        if not target:
            continue
        matched = (
            source in ("auto", "*", "")
            or source == detected
            # 拉丁语系无法细分时，暂按英语的规则走，模型会按规则表纠正
            or (detected == "latin" and source == "en")
        )
        if matched:
            return detected, target, rule, confident
    return detected, fallback, None, confident


def target_display_name(target: str) -> str:
    """把目标语言代码转成提示词里用的名称，自定义名称原样返回。"""
    if not target:
        return language_label("zh")
    return language_label(target) or target


def build_routing_instruction(rules: List[Dict[str, Any]], default_target: str) -> Optional[str]:
    """把规则表写成一段自然语言指令，交给模型判断原文语言并选择目标语言。

    措辞要让规则表成为目标语言的唯一依据——系统提示里不能再出现固定目标语言，
    否则模型会优先听那个。
    """
    items: List[Tuple[str, str]] = []
    has_fallback = False
    for rule in rules or []:
        source = str(rule.get("source") or "auto").lower()
        target = str(rule.get("target") or "").strip()
        if not target:
            continue
        if source in ("auto", "*", ""):
            has_fallback = True
            source_name = "其它情况"
        else:
            source_name = language_label(source) or source
        items.append((source_name, target_display_name(target)))
    if len(items) < 2:
        return None  # 只有一条规则时没有路由空间
    # 用条件句而不是箭头表：实测“法语 → 德语”这种写法模型会忽略，
    # 写成“如果原文是法语，翻译成德语”才会照做
    lines_list: List[str] = []
    for index, (source, target) in enumerate(items, 1):
        if source == "其它情况":
            lines_list.append(f"{index}. 其它情况，翻译成{target}")
        else:
            lines_list.append(f"{index}. 如果原文是{source}，翻译成{target}")
    if not has_fallback:
        lines_list.append(f"{len(lines_list) + 1}. 其它情况，翻译成{target_display_name(default_target)}")
    return (
        "翻译规则（先判断原文语言，再按对应规则翻译；只输出译文）：\n"
        + "\n".join(lines_list)
        + "。"
    )
