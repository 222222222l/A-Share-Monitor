#!/usr/bin/env python
"""Smoke test D-group structured report generation through an LLM API."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from a_share_monitor.reporting import build_latest_fixture_report


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_OUTPUT = PACKAGE_ROOT / "reports" / "d_group_llm_report.json"
DEFAULT_BASE_URL = "https://api.laozhang.ai/v1"
DEFAULT_MODEL = "gemini-3-flash-preview"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test D-group LLM report.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--api-key-env",
        default="A_SHARE_MONITOR_API_KEY",
        help="Environment variable that contains the API key.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output JSON path. Defaults to reports/d_group_llm_report.json.",
    )
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(
            json.dumps(
                {
                    "status": "SKIP",
                    "reason": f"missing API key env: {args.api_key_env}",
                },
                indent=2,
            )
        )
        return 2

    source_report = build_latest_fixture_report()
    try:
        response_text = _call_chat_completion(
            base_url=args.base_url,
            api_key=api_key,
            model=args.model,
            source_report=source_report,
        )
        _validate_response(response_text, source_report)
    except (AssertionError, RuntimeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2))
        return 1

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "PASS",
        "model": args.model,
        "base_url": args.base_url,
        "trade_date": source_report["trade_date"],
        "planned_symbols": source_report["selection_summary"]["planned_symbols"],
        "response_text": response_text,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "model": args.model,
                "output": str(output_path),
                "response_chars": len(response_text),
                "planned_symbols": source_report["selection_summary"][
                    "planned_symbols"
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def _call_chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    source_report: dict[str, Any],
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    request_payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You generate concise Chinese structured research reports. "
                    "Do not provide personalized financial advice. Do not invent "
                    "prices, targets, risk fields, or order execution."
                ),
            },
            {
                "role": "user",
                "content": (
                    "基于以下 JSON 生成结构化 A 股监控摘要，必须包含："
                    "market_summary、candidate_reviews、watchlist、risk_boundary。"
                    "输出 JSON，不要 Markdown。\n\n"
                    + json.dumps(
                        _compact_report_for_llm(source_report), ensure_ascii=False
                    )
                ),
            },
        ],
        "temperature": 0.1,
        "max_tokens": 1600,
    }
    data = json.dumps(request_payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "a-share-monitor-smoke/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API HTTP {exc.code}: {detail[:300]}") from exc
    except (urllib.error.URLError, http.client.RemoteDisconnected) as exc:
        raise RuntimeError(f"LLM API connection failed: {exc}") from exc
    payload = json.loads(body)
    return str(payload["choices"][0]["message"]["content"]).strip()


def _compact_report_for_llm(source_report: dict[str, Any]) -> dict[str, Any]:
    recommendations = []
    for item in source_report["recommendations"]:
        recommendations.append(
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "decision": item["decision"],
                "setup_type": item["setup_type"],
                "entry_zone": item["entry_zone"],
                "technical_exit_price": item["technical_exit_price"],
                "technical_exit_reason": item["technical_exit_reason"],
                "fundamental_exit_trigger": item["fundamental_exit_trigger"],
                "target_1": item["target_1"],
                "target_2": item["target_2"],
                "risk_reward": item["risk_reward"],
                "position_size": item["position_size"],
                "ownership_flow_risk": item["ownership_flow_risk"],
                "time_exit_rule": item["time_exit_rule"],
                "confidence": item["confidence"],
            }
        )
    return {
        "trade_date": source_report["trade_date"],
        "decision_boundary": source_report["decision_boundary"],
        "selection_summary": source_report["selection_summary"],
        "recommendations": recommendations,
        "critic_review": source_report["critic_review"],
    }


def _validate_response(response_text: str, source_report: dict[str, Any]) -> None:
    if len(response_text) < 80:
        raise AssertionError("LLM report response is too short")
    planned_symbols = source_report["selection_summary"]["planned_symbols"]
    for symbol in planned_symbols:
        if symbol not in response_text:
            raise AssertionError(f"LLM report missing planned symbol: {symbol}")
    for keyword in ("risk", "风险", "watchlist", "观察"):
        if keyword in response_text:
            return
    raise AssertionError("LLM report missing risk/watchlist language")


if __name__ == "__main__":
    raise SystemExit(main())
