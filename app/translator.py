"""DeepSeek（OpenAI 兼容）接口调用，仅使用标准库。"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .lang import target_display_name

DEFAULT_BASE_URL = "https://api.deepseek.com"

PRESET_MODELS = (
    ("deepseek-flash", "响应快，适合划词翻译（推荐）"),
    ("deepseek-v4-pro", "能力更强，速度稍慢"),
)

# 接口明确表示不认识 thinking 参数时置位，之后不再发送（兼容别的 OpenAI 兼容服务）
_thinking_param_supported = True


class TranslateError(Exception):
    pass


def build_endpoint(base_url: str) -> str:
    base = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if not base:
        base = DEFAULT_BASE_URL
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def build_messages(
    text: str,
    target: str,
    system_prompt: str,
    routing: Optional[str] = None,
) -> List[Dict[str, str]]:
    """routing 非空时把规则表附在系统提示里，由模型判断原文语言并选择目标语言。"""
    template = system_prompt or "请把下面的文本翻译成{target}。"
    if routing:
        # 目标语言交给规则表决定，提示词里不能出现固定目标语言，否则模型会优先听它
        instruction = template.replace("{target}", "下面规则指定的语言")
        instruction = f"{instruction}\n\n{routing}"
    else:
        instruction = template.replace("{target}", target_display_name(target))
    return [
        {"role": "system", "content": instruction},
        {"role": "user", "content": text},
    ]


def build_payload(
    text: str,
    target: str,
    model_config: Dict[str, Any],
    disable_thinking: Optional[bool] = None,
    routing: Optional[str] = None,
) -> Dict[str, Any]:
    """组装请求体。disable_thinking=None 时按配置决定。"""
    if disable_thinking is None:
        disable_thinking = not bool(model_config.get("thinking", False))
    payload: Dict[str, Any] = {
        "model": (model_config.get("model") or "deepseek-flash").strip() or "deepseek-flash",
        "messages": build_messages(
            text, target, model_config.get("system_prompt") or "", routing
        ),
        "stream": False,
    }
    try:
        payload["temperature"] = float(model_config.get("temperature", 0.3))
    except (TypeError, ValueError):
        payload["temperature"] = 0.3
    if disable_thinking and _thinking_param_supported:
        # 官方写法；关掉后模型不再产生隐藏的推理 token
        payload["thinking"] = {"type": "disabled"}
    return payload


def _rejected_thinking_param(message: str) -> bool:
    """判断接口报错是否因为不认识 thinking 参数。"""
    text = (message or "").lower()
    if "thinking" not in text and "unknown" not in text:
        return False
    return any(
        token in text
        for token in ("unsupported", "unknown", "not support", "invalid", "unrecognized", "额外", "不支持")
    )


def _post_json(url: str, payload: Dict[str, Any], api_key: str, timeout: float) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "Trans/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        message = _extract_error(detail) or exc.reason or "HTTP 错误"
        raise TranslateError(f"接口返回 {exc.code}：{message}") from exc
    except urllib.error.URLError as exc:
        raise TranslateError(f"网络错误：{exc.reason}") from exc
    except TimeoutError as exc:
        raise TranslateError("请求超时") from exc
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise TranslateError("接口返回内容无法解析") from exc


def _extract_error(detail: str) -> str:
    if not detail:
        return ""
    try:
        data = json.loads(detail)
    except ValueError:
        return detail[:200]
    error = data.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("type") or "")[:200]
    if isinstance(error, str):
        return error[:200]
    return str(data.get("message") or "")[:200]


def translate(
    text: str,
    target: str,
    model_config: Dict[str, Any],
    usage: Optional[Dict[str, Any]] = None,
    routing: Optional[str] = None,
) -> Tuple[bool, str, float]:
    """调用 DeepSeek 翻译，返回 (是否成功, 译文或错误信息, 耗时秒)。"""
    api_key = (model_config.get("api_key") or "").strip()
    if not api_key:
        return False, "尚未配置 API Key，请打开设置填写。", 0.0

    try:
        timeout = float(model_config.get("timeout", 20)) or 20.0
    except (TypeError, ValueError):
        timeout = 20.0

    url = build_endpoint(model_config.get("base_url") or DEFAULT_BASE_URL)
    started = time.time()
    payload = build_payload(text, target, model_config, routing=routing)
    try:
        data = _post_json(url, payload, api_key, timeout)
    except TranslateError as exc:
        if "thinking" in payload and _rejected_thinking_param(str(exc)):
            # 接口不认 thinking 参数：去掉重试一次，并在本进程内记住
            global _thinking_param_supported
            _thinking_param_supported = False
            try:
                data = _post_json(
                    url,
                    build_payload(text, target, model_config, routing=routing),
                    api_key,
                    timeout,
                )
            except TranslateError as retry_exc:
                return False, str(retry_exc), time.time() - started
        else:
            return False, str(exc), time.time() - started
    except Exception as exc:  # 兜底，避免后台线程崩溃
        return False, f"调用失败：{exc}", time.time() - started

    if usage is not None:
        usage.clear()
        usage.update(data.get("usage") or {})
    choices = data.get("choices") or []
    if not choices:
        return False, "接口未返回译文", time.time() - started
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        return False, "接口返回空译文", time.time() - started
    return True, content, time.time() - started


