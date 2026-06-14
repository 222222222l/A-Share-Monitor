#!/usr/bin/env python
"""Run a real-market snapshot smoke test without adding a formal data adapter."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_OUTPUT = PACKAGE_ROOT / "reports" / "real_snapshot_2026-06-12.json"
DEFAULT_BASE_URL = "https://api.laozhang.ai/v1"
DEFAULT_MODEL = "gemini-3-flash-preview"
EASTMONEY_UT = "bd1d9ddb04089700cf9c27f6f7426281"
FALLBACK_POOL = {
    "300750": "宁德时代",
    "002594": "比亚迪",
    "600519": "贵州茅台",
    "000858": "五粮液",
    "601318": "中国平安",
    "600036": "招商银行",
    "000333": "美的集团",
    "601899": "紫金矿业",
    "600276": "恒瑞医药",
    "688981": "中芯国际",
    "688256": "寒武纪",
    "300059": "东方财富",
    "002230": "科大讯飞",
    "002475": "立讯精密",
    "000651": "格力电器",
    "600887": "伊利股份",
    "600030": "中信证券",
    "000977": "浪潮信息",
    "300308": "中际旭创",
    "601138": "工业富联",
    "002241": "歌尔股份",
    "300124": "汇川技术",
    "600031": "三一重工",
    "601919": "中远海控",
    "002371": "北方华创",
    "300760": "迈瑞医疗",
    "688111": "金山办公",
    "601012": "隆基绿能",
    "600309": "万华化学",
    "600900": "长江电力",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real snapshot smoke test.")
    parser.add_argument("--trade-date", default="2026-06-12")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key-env", default="A_SHARE_MONITOR_API_KEY")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(
            json.dumps(
                {"status": "SKIP", "reason": f"missing env {args.api_key_env}"},
                indent=2,
            )
        )
        return 2

    try:
        quotes = _fetch_a_share_quotes(args.trade_date)
        report = _build_snapshot_report(quotes, args.trade_date)
        llm_summary = _call_llm(args.base_url, api_key, args.model, report)
    except (RuntimeError, AssertionError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2))
        return 1

    output = {
        "status": "PASS",
        "source": "eastmoney_public_snapshot",
        "trade_date": args.trade_date,
        "model": args.model,
        "report": report,
        "llm_summary": llm_summary,
    }
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "trade_date": args.trade_date,
                "universe_size": report["market"]["universe_size"],
                "advancing_count": report["market"]["advancing_count"],
                "declining_count": report["market"]["declining_count"],
                "candidate_count": len(report["candidates"]),
                "watchlist_count": len(report["watchlist"]),
                "output": str(output_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def _fetch_a_share_quotes(trade_date: str) -> list[dict[str, Any]]:
    fields = "f12,f14,f2,f3,f5,f6,f15,f16,f17,f18,f20,f21,f62"
    fs = "m:1+t:2,m:1+t:23,m:0+t:6,m:0+t:80"
    try:
        first = _fetch_quote_page(1, 100, fields, fs)
        total = int(first["data"]["total"])
        rows = list(first["data"]["diff"])
        for page in range(2, min((total // 100) + 2, 70)):
            time.sleep(0.15)
            payload = _fetch_quote_page(page, 100, fields, fs)
            rows.extend(payload["data"].get("diff") or [])
            if len(rows) >= total:
                break
        return [_normalize_quote(row) for row in rows if _is_usable_quote(row)]
    except RuntimeError:
        return _fetch_fallback_quotes(trade_date)


def _fetch_fallback_quotes(trade_date: str) -> list[dict[str, Any]]:
    quotes = []
    for symbol, name in FALLBACK_POOL.items():
        time.sleep(0.12)
        try:
            rows = _fetch_kline(symbol, trade_date)
        except RuntimeError:
            continue
        if not rows:
            continue
        latest = rows[-1]
        if latest["date"] != trade_date:
            continue
        previous_close = rows[-2]["close"] if len(rows) >= 2 else latest["open"]
        quotes.append(
            {
                "symbol": symbol,
                "name": name,
                "close": float(latest["close"]),
                "pct_change": float(latest["pct_change"]),
                "volume": float(latest["volume"]),
                "amount": float(latest["amount"]),
                "high": float(latest["high"]),
                "low": float(latest["low"]),
                "open": float(latest["open"]),
                "prev_close": float(previous_close),
                "float_market_cap": 0.0,
                "main_net_inflow": 0.0,
                "source": "fallback_kline_pool",
            }
        )
    if not quotes:
        raise RuntimeError("fallback kline pool returned no usable quotes")
    return quotes


def _fetch_quote_page(
    page: int, page_size: int, fields: str, fs: str
) -> dict[str, Any]:
    query = (
        f"pn={page}&pz={page_size}&po=1&np=1&ut={EASTMONEY_UT}"
        f"&fltt=2&invt=2&fid=f6&fs={fs}&fields={fields}"
    )
    return _get_json(f"https://push2.eastmoney.com/api/qt/clist/get?{query}")


def _build_snapshot_report(
    quotes: list[dict[str, Any]], trade_date: str
) -> dict[str, Any]:
    liquid = [
        row
        for row in quotes
        if row["amount"] >= 80_000_000
        and -8 <= row["pct_change"] <= 8
        and row["close"] > row["open"]
    ]
    history_rows = []
    for quote in sorted(liquid, key=lambda item: item["amount"], reverse=True)[:80]:
        time.sleep(0.12)
        try:
            history = _fetch_kline(quote["symbol"], trade_date)
        except RuntimeError:
            continue
        if len(history) >= 60:
            signal = _technical_signal(quote, history)
            if signal["status"] != "rejected":
                history_rows.append(signal)
        if len(history_rows) >= 12:
            break
    candidates = [row for row in history_rows if row["status"] == "candidate"]
    watchlist = [row for row in history_rows if row["status"] == "watchlist"]
    return {
        "schema_version": "a-share-monitor.real-smoke.v1",
        "trade_date": trade_date,
        "decision_boundary": {
            "real_trading_enabled": False,
            "final_decision_owner": "user",
            "data_source": "Eastmoney public quote/kline endpoints",
        },
        "market": _market_summary(quotes),
        "candidates": candidates[:5],
        "watchlist": watchlist[:10],
        "audit": {
            "formal_external_adapter": False,
            "f_group_development": "deferred",
            "usage": "snapshot smoke test only",
        },
    }


def _fetch_kline(symbol: str, end_date: str) -> list[dict[str, float | str]]:
    secid = ("1." if symbol.startswith(("6", "9")) else "0.") + symbol
    query = urllib.parse.urlencode(
        {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": 101,
            "fqt": 1,
            "beg": "20250101",
            "end": end_date.replace("-", ""),
        }
    )
    try:
        payload = _get_json(
            f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{query}"
        )
    except RuntimeError:
        return _fetch_tencent_kline(symbol, end_date)
    rows = payload.get("data", {}).get("klines") or []
    result = []
    for row in rows:
        parts = row.split(",")
        result.append(
            {
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
                "amount": float(parts[6]),
                "pct_change": float(parts[8]),
                "turnover": float(parts[10]),
            }
        )
    return result


def _fetch_tencent_kline(symbol: str, end_date: str) -> list[dict[str, float | str]]:
    prefix = "sh" if symbol.startswith(("6", "9")) else "sz"
    param = f"{prefix}{symbol},day,2025-01-01,{end_date},400,qfq"
    query = urllib.parse.urlencode({"param": param})
    payload = _get_json(f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?{query}")
    data = payload.get("data", {}).get(f"{prefix}{symbol}", {})
    rows = data.get("qfqday") or data.get("day") or []
    result = []
    previous_close = 0.0
    for row in rows:
        date, open_price, close, high, low, volume = row[:6]
        close_value = float(close)
        pct_change = (
            ((close_value / previous_close) - 1) * 100 if previous_close else 0.0
        )
        result.append(
            {
                "date": date,
                "open": float(open_price),
                "close": close_value,
                "high": float(high),
                "low": float(low),
                "volume": float(volume),
                "amount": float(volume) * close_value,
                "pct_change": pct_change,
                "turnover": 0.0,
            }
        )
        previous_close = close_value
    return result


def _technical_signal(
    quote: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    closes = [float(row["close"]) for row in rows]
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    close = closes[-1]
    ema5 = _ema(closes, 5)
    ema10 = _ema(closes, 10)
    ema20 = _ema(closes, 20)
    ema60 = _ema(closes, 60)
    atr14 = _atr(highs, lows, closes, 14)
    trend = (
        close > ema20 and ema20 >= ema60 * 0.995 and close >= ema5 and close >= ema10
    )
    near_ma20 = abs(close / ema20 - 1) <= 0.08
    if not trend:
        return _watch_or_reject(
            quote, close, ema20, ema60, "technical_signal_not_ready"
        )
    stop = round(max(min(lows[-10:]), ema20 - atr14 * 0.35), 2)
    entry_upper = round(close + atr14 * 0.2, 2)
    risk = max(entry_upper - stop, close * 0.01)
    target = round(max(max(highs[-20:]), entry_upper + risk * 1.6), 2)
    risk_reward = round((target - entry_upper) / risk, 4)
    if risk_reward <= 1.5 or not near_ma20:
        return _watch_or_reject(
            quote, close, ema20, ema60, "risk_reward_or_entry_not_ready"
        )
    return {
        "status": "candidate",
        "symbol": quote["symbol"],
        "name": quote["name"],
        "decision": "buy_ready",
        "setup_type": "trend_pullback",
        "close": close,
        "pct_change": quote["pct_change"],
        "amount": quote["amount"],
        "main_net_inflow": quote["main_net_inflow"],
        "entry_zone": [round(close - atr14 * 0.2, 2), entry_upper],
        "technical_exit_price": stop,
        "target_1": target,
        "risk_reward": risk_reward,
        "technical_reason": f"close>{ema20:.2f} EMA20 and EMA20 aligns with EMA60 {ema60:.2f}",
    }


def _watch_or_reject(
    quote: dict[str, Any], close: float, ema20: float, ema60: float, reason: str
) -> dict[str, Any]:
    if quote["amount"] < 120_000_000:
        return {"status": "rejected", "symbol": quote["symbol"], "reason": "liquidity"}
    return {
        "status": "watchlist",
        "symbol": quote["symbol"],
        "name": quote["name"],
        "close": close,
        "pct_change": quote["pct_change"],
        "amount": quote["amount"],
        "reason": reason,
        "ema20": round(ema20, 4),
        "ema60": round(ema60, 4),
    }


def _market_summary(quotes: list[dict[str, Any]]) -> dict[str, Any]:
    advancing = sum(1 for row in quotes if row["pct_change"] > 0)
    declining = sum(1 for row in quotes if row["pct_change"] < 0)
    limit_up = sum(1 for row in quotes if row["pct_change"] >= 9.8)
    limit_down = sum(1 for row in quotes if row["pct_change"] <= -9.8)
    total_amount = sum(row["amount"] for row in quotes)
    return {
        "universe_size": len(quotes),
        "advancing_count": advancing,
        "declining_count": declining,
        "advancing_ratio": round(advancing / max(len(quotes), 1), 4),
        "limit_up_count": limit_up,
        "limit_down_count": limit_down,
        "total_amount": round(total_amount, 2),
    }


def _call_llm(base_url: str, api_key: str, model: str, report: dict[str, Any]) -> str:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你生成中文A股监控摘要。禁止声称这是个性化投资建议；"
                    "禁止生成真实下单指令。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "基于以下真实行情快照 smoke report 输出 JSON，包含 market, "
                    "candidates, watchlist, risks, decision_boundary。\n"
                    + json.dumps(report, ensure_ascii=False)
                ),
            },
        ],
        "temperature": 0.1,
        "max_tokens": 1800,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "a-share-monitor-real-smoke/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API HTTP {exc.code}: {detail[:300]}") from exc
    except (urllib.error.URLError, http.client.RemoteDisconnected) as exc:
        raise RuntimeError(f"LLM API connection failed: {exc}") from exc
    data = json.loads(body)
    text = str(data["choices"][0]["message"]["content"]).strip()
    if len(text) < 80:
        raise AssertionError("LLM summary too short")
    return text


def _get_json(url: str) -> dict[str, Any]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://quote.eastmoney.com/",
    }
    last_error: Exception | None = None
    for attempt in range(1, 4):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, http.client.RemoteDisconnected) as exc:
            last_error = exc
            time.sleep(0.6 * attempt)
    raise RuntimeError(f"market data request failed after retries: {last_error}")


def _normalize_quote(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": str(row["f12"]),
        "name": str(row["f14"]),
        "close": float(row["f2"]),
        "pct_change": float(row["f3"]),
        "volume": float(row["f5"]),
        "amount": float(row["f6"]),
        "high": float(row["f15"]),
        "low": float(row["f16"]),
        "open": float(row["f17"]),
        "prev_close": float(row["f18"]),
        "float_market_cap": float(row.get("f21") or 0),
        "main_net_inflow": float(row.get("f62") or 0),
    }


def _is_usable_quote(row: dict[str, Any]) -> bool:
    try:
        name = str(row["f14"])
        close = float(row["f2"])
        amount = float(row["f6"])
    except (TypeError, ValueError):
        return False
    return close > 0 and amount > 0 and "ST" not in name.upper()


def _ema(values: list[float], window: int) -> float:
    alpha = 2 / (window + 1)
    result = values[0]
    for value in values[1:]:
        result = value * alpha + result * (1 - alpha)
    return result


def _atr(
    highs: list[float], lows: list[float], closes: list[float], window: int
) -> float:
    ranges = []
    for index, high in enumerate(highs):
        low = lows[index]
        if index == 0:
            ranges.append(high - low)
            continue
        previous_close = closes[index - 1]
        ranges.append(
            max(high - low, abs(high - previous_close), abs(low - previous_close))
        )
    sample = ranges[-window:]
    return sum(sample) / len(sample)


if __name__ == "__main__":
    raise SystemExit(main())
