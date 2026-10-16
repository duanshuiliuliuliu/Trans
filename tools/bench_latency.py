"""延迟基准测试：对比“翻译前先推理”开关对耗时的影响，并给出接口地板延迟。

用法：python tools/bench_latency.py [每档调用次数，默认 4]
会真实调用已配置的接口，消耗少量额度。改动 translator.py 后可用于前后对比。
"""
from __future__ import annotations

import http.client
import json
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from app.config import Config
from app.translator import translate

SAMPLES = [
    "Measurements of the transverse momentum imbalance in proton-lead collisions "
    "provide new constraints on the parton distribution inside the nucleon.",
    "The system shall gracefully degrade when the upstream service is unavailable.",
    "这个工具需要尽量少占内存，设计要简单明了。",
    "咱们先把方案对齐一下，再决定要不要动这块逻辑。",
]
TARGETS = ["zh", "zh", "en", "en"]


def report(label: str, values: List[float], extra: str = "") -> None:
    if not values:
        print(f"{label}: 无数据")
        return
    print(
        f"{label}: 平均 {statistics.mean(values):.2f}s  中位 {statistics.median(values):.2f}s  "
        f"最快 {min(values):.2f}s  最慢 {max(values):.2f}s  {extra}"
    )


def floor_latency(model_config: Dict[str, Any], rounds: int = 3) -> List[float]:
    """最短请求耗时，代表接口侧的固定开销。"""
    key = model_config["api_key"]
    values: List[float] = []
    for _ in range(rounds):
        payload = {
            "model": model_config["model"],
            "stream": False,
            "max_tokens": 8,
            "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": "只回答两个字：好了"}],
        }
        connection = http.client.HTTPSConnection("api.deepseek.com", timeout=60)
        started = time.time()
        try:
            connection.request(
                "POST",
                "/chat/completions",
                body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
            )
            response = connection.getresponse()
            response.read()
            if response.status == 200:
                values.append(time.time() - started)
        finally:
            connection.close()
    return values


def run_mode(model_config: Dict[str, Any], thinking: bool, rounds: int) -> Tuple[List[float], str]:
    config = dict(model_config)
    config["thinking"] = thinking
    times: List[float] = []
    sample = ""
    for index in range(rounds):
        usage: Dict[str, Any] = {}
        ok, result, elapsed = translate(SAMPLES[index % len(SAMPLES)], TARGETS[index % len(TARGETS)], config, usage)
        if not ok:
            print("调用失败：", result)
            continue
        times.append(elapsed)
        details = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        print(
            f"  第 {index + 1} 次 {elapsed:.2f}s  输出 {usage.get('completion_tokens', '-')} token"
            f"（推理 {details}）"
        )
        sample = result
    return times, sample


def main() -> int:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    model_config = dict(Config.load().section("model"))
    if not (model_config.get("api_key") or "").strip():
        print("配置里没有 API Key，无法测试。")
        return 1

    print(f"模型 {model_config.get('model')}，温度 {model_config.get('temperature')}，每档 {rounds} 次\n")
    print("预热…")
    warm = dict(model_config)
    warm["thinking"] = False
    translate(SAMPLES[0], "zh", warm)

    print("\n【推理关】")
    off_times, off_sample = run_mode(model_config, False, rounds)
    report("  汇总", off_times)
    if off_sample:
        print(f"  示例译文：{off_sample[:60]}")

    print("\n【推理开】")
    on_times, on_sample = run_mode(model_config, True, rounds)
    report("  汇总", on_times)
    if on_sample:
        print(f"  示例译文：{on_sample[:60]}")

    print("\n【接口地板延迟（最短请求）】")
    floor = floor_latency(model_config)
    report("  汇总", floor)

    print()
    if off_times and on_times:
        saved = statistics.mean(on_times) - statistics.mean(off_times)
        print(f"关闭推理可省：平均 {saved:.2f}s（{statistics.mean(on_times):.2f}s → {statistics.mean(off_times):.2f}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
