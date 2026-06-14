"""Build real-market A-share snapshot reports from public quote endpoints."""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from datetime import datetime
from datetime import time as day_time
from datetime import timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from a_share_monitor.reporting.tencent_quote import TENCENT_BATCH_SIZE
from a_share_monitor.reporting.tencent_quote import fetch_tencent_universe_quotes

EASTMONEY_UT = "bd1d9ddb04089700cf9c27f6f7426281"
CHINA_TZ = ZoneInfo("Asia/Shanghai")
HTTP_ATTEMPTS = 2
HTTP_TIMEOUT_SECONDS = 12
FALLBACK_PROBE_LIMIT = 3
MAX_KLINE_SCREEN_SYMBOLS = 12
FALLBACK_POOL = {
    "300750": "CATL",
    "002594": "BYD",
    "600519": "Kweichow Moutai",
    "601318": "Ping An",
    "600036": "CMB",
    "601899": "Zijin Mining",
    "688981": "SMIC",
    "300059": "East Money",
    "002230": "iFlytek",
    "601138": "Foxconn Industrial Internet",
    "002371": "NAURA",
    "688111": "Kingsoft Office",
    "600900": "Yangtze Power",
}


def build_real_snapshot_report(
    *,
    requested_trade_date: str | None = None,
    user_intent: str = "latest_completed_session",
    progress: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Build a compact real-market snapshot report for the Web UI agent."""
    resolved_date = resolve_market_date(requested_trade_date)
    _progress(progress, "resolve_trade_date", {"trade_date": resolved_date})
    quotes = _fetch_a_share_quotes(resolved_date, progress=progress)
    report = _build_snapshot_report(
        quotes, resolved_date, requested_trade_date, progress=progress
    )
    report["user_intent"] = user_intent
    return report


def build_unavailable_real_snapshot(
    *,
    error: str,
    requested_trade_date: str | None = None,
    user_intent: str = "latest_completed_session",
) -> dict[str, Any]:
    """Return an explicit no-data report without falling back to fixtures."""
    resolved_date = resolve_market_date(requested_trade_date)
    return {
        "schema_version": "a-share-monitor.real-snapshot.v1",
        "status": "DATA_UNAVAILABLE",
        "generated_at": _now().isoformat(),
        "user_intent": user_intent,
        "trade_date": resolved_date,
        "data_freshness": {
            "mode": "real",
            "requested_trade_date": requested_trade_date,
            "resolved_trade_date": resolved_date,
            "current_date": _now().date().isoformat(),
            "fallback_to_fixture": False,
        },
        "data_acquisition": _data_acquisition_summary([], error=error),
        "decision_boundary": _decision_boundary(
            "real data unavailable; do not infer recommendations from stale fixture data"
        ),
        "error": error,
        "selection_summary": {
            "min_risk_reward": 1.5,
            "planned_symbols": [],
            "watchlist_symbols": [],
            "recommendation_count": 0,
        },
        "recommendations": [],
        "watchlist": [],
        "critic_review": {
            "status": "fail",
            "findings": ["real_market_data_unavailable"],
            "confidence": "high",
        },
    }


def resolve_market_date(requested_trade_date: str | None = None) -> str:
    """Resolve the data date for real-market questions.

    If the user does not name a date, use the latest completed China A-share
    session by weekday approximation. Holiday gaps are handled by the data
    fetcher walking backward until public kline data exists.
    """
    if requested_trade_date:
        return requested_trade_date
    now = _now()
    candidate = now.date()
    if candidate.weekday() >= 5 or now.time() < day_time(16, 0):
        candidate = _previous_weekday(candidate)
    return candidate.isoformat()


def _fetch_a_share_quotes(
    trade_date: str, *, progress: Callable[[str, dict[str, Any]], None] | None = None
) -> list[dict[str, Any]]:
    _progress(
        progress,
        "quote_source_start",
        {"source": "tencent_batch_quote", "batch_size": TENCENT_BATCH_SIZE},
    )
    try:
        quotes = fetch_tencent_universe_quotes(progress=progress)
        if quotes:
            _progress(
                progress,
                "quote_source_done",
                {"source": "tencent_batch_quote", "usable_quotes": len(quotes)},
            )
            return quotes
    except (RuntimeError, ValueError) as exc:
        _progress(
            progress,
            "quote_source_failed",
            {"source": "tencent_batch_quote", "error": str(exc)},
        )

    fields = "f12,f14,f2,f3,f5,f6,f15,f16,f17,f18,f20,f21,f62"
    fs = "m:1+t:2,m:1+t:23,m:0+t:6,m:0+t:80"
    _progress(progress, "quote_source_start", {"source": "eastmoney_quote"})
    try:
        first = _fetch_quote_page(1, 100, fields, fs)
        total = int(first["data"]["total"])
        rows = list(first["data"]["diff"])
        _progress(
            progress,
            "quote_page",
            {"source": "eastmoney_quote", "page": 1, "rows": len(rows), "total": total},
        )
        for page in range(2, min((total // 100) + 2, 70)):
            time.sleep(0.12)
            payload = _fetch_quote_page(page, 100, fields, fs)
            rows.extend(payload["data"].get("diff") or [])
            if page == 2 or page % 10 == 0:
                _progress(
                    progress,
                    "quote_page",
                    {
                        "source": "eastmoney_quote",
                        "page": page,
                        "rows": len(rows),
                        "total": total,
                    },
                )
            if len(rows) >= total:
                break
        quotes = [_normalize_quote(row) for row in rows if _is_usable_quote(row)]
        if quotes:
            _progress(
                progress,
                "quote_source_done",
                {"source": "eastmoney_quote", "usable_quotes": len(quotes)},
            )
            return quotes
    except (KeyError, RuntimeError, ValueError) as exc:
        _progress(
            progress,
            "quote_source_failed",
            {"source": "eastmoney_quote", "error": str(exc)},
        )
    return _fetch_fallback_quotes_with_date_walk(trade_date, progress=progress)


def _fetch_fallback_quotes_with_date_walk(
    trade_date: str, *, progress: Callable[[str, dict[str, Any]], None] | None = None
) -> list[dict[str, Any]]:
    candidate = date.fromisoformat(trade_date)
    last_error = "no usable fallback quotes"
    _progress(
        progress,
        "fallback_probe_start",
        {"source": "fallback_kline_pool", "probe_limit": FALLBACK_PROBE_LIMIT},
    )
    for _ in range(8):
        candidate = (
            candidate if candidate.weekday() < 5 else _previous_weekday(candidate)
        )
        try:
            quotes = _fetch_fallback_quotes(candidate.isoformat(), progress=progress)
            if quotes:
                _progress(
                    progress,
                    "fallback_probe_done",
                    {
                        "source": "fallback_kline_pool",
                        "trade_date": candidate.isoformat(),
                        "usable_quotes": len(quotes),
                    },
                )
                return quotes
        except RuntimeError as exc:
            last_error = str(exc)
        candidate = _previous_weekday(candidate)
    raise RuntimeError(last_error)


def _fetch_fallback_quotes(
    trade_date: str, *, progress: Callable[[str, dict[str, Any]], None] | None = None
) -> list[dict[str, Any]]:
    quotes = []
    for index, (symbol, name) in enumerate(FALLBACK_POOL.items(), start=1):
        if index > FALLBACK_PROBE_LIMIT:
            break
        time.sleep(0.1)
        _progress(
            progress,
            "fallback_symbol",
            {"symbol": symbol, "index": index, "limit": FALLBACK_PROBE_LIMIT},
        )
        rows = _fetch_kline(symbol, trade_date)
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
        raise RuntimeError(f"fallback kline pool returned no quotes for {trade_date}")
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
    quotes: list[dict[str, Any]],
    trade_date: str,
    requested_trade_date: str | None,
    *,
    progress: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    history_rows = []
    kline_attempt_count = 0
    kline_success_count = 0
    preliminary_acquisition = _data_acquisition_summary(quotes)
    if preliminary_acquisition["quality_state"] != "usable":
        _progress(
            progress,
            "quality_gate_failed",
            {
                "quality_state": preliminary_acquisition["quality_state"],
                "quote_count": preliminary_acquisition["quote_count"],
                "minimum_full_market_quotes": preliminary_acquisition[
                    "minimum_full_market_quotes"
                ],
            },
        )
        return _degraded_snapshot_report(
            quotes,
            trade_date,
            requested_trade_date,
            acquisition=preliminary_acquisition,
        )
    liquid = [
        row
        for row in quotes
        if row["amount"] >= 80_000_000
        and -8 <= row["pct_change"] <= 8
        and row["close"] > row["open"]
    ]
    _progress(
        progress,
        "kline_screen_start",
        {"eligible_quotes": len(liquid), "max_attempts": MAX_KLINE_SCREEN_SYMBOLS},
    )
    for quote in sorted(liquid, key=lambda item: item["amount"], reverse=True)[
        :MAX_KLINE_SCREEN_SYMBOLS
    ]:
        time.sleep(0.1)
        kline_attempt_count += 1
        _progress(
            progress,
            "kline_symbol",
            {
                "symbol": quote["symbol"],
                "attempt": kline_attempt_count,
                "max_attempts": MAX_KLINE_SCREEN_SYMBOLS,
            },
        )
        history = _fetch_kline(quote["symbol"], trade_date)
        if len(history) < 60:
            continue
        kline_success_count += 1
        signal = _technical_signal(quote, history)
        if signal["status"] != "rejected":
            history_rows.append(signal)
        if len(history_rows) >= 12:
            break
    recommendations = [row for row in history_rows if row["status"] == "candidate"][:5]
    watchlist = [row for row in history_rows if row["status"] == "watchlist"][:10]
    planned_symbols = [row["symbol"] for row in recommendations]
    watchlist_symbols = [row["symbol"] for row in watchlist]
    report = {
        "schema_version": "a-share-monitor.real-snapshot.v1",
        "status": "PASS",
        "generated_at": _now().isoformat(),
        "trade_date": trade_date,
        "data_freshness": {
            "mode": "real",
            "requested_trade_date": requested_trade_date,
            "resolved_trade_date": trade_date,
            "current_date": _now().date().isoformat(),
            "fallback_to_fixture": False,
        },
        "data_acquisition": _data_acquisition_summary(
            quotes,
            kline_attempt_count=kline_attempt_count,
            kline_success_count=kline_success_count,
        ),
        "decision_boundary": _decision_boundary(
            "public quote/kline snapshot; verify broker data before trading"
        ),
        "market": _market_summary(quotes),
        "selection_summary": {
            "min_risk_reward": 1.5,
            "planned_symbols": planned_symbols,
            "watchlist_symbols": watchlist_symbols,
            "recommendation_count": len(recommendations),
        },
        "recommendations": recommendations,
        "watchlist": watchlist,
    }
    _apply_data_quality_gate(report)
    report["critic_review"] = _review_real_snapshot(report)
    _progress(
        progress,
        "report_done",
        {
            "status": report["status"],
            "quality_state": report["data_acquisition"]["quality_state"],
            "recommendation_count": report["selection_summary"]["recommendation_count"],
        },
    )
    return report


def _degraded_snapshot_report(
    quotes: list[dict[str, Any]],
    trade_date: str,
    requested_trade_date: str | None,
    *,
    acquisition: dict[str, Any],
) -> dict[str, Any]:
    report = {
        "schema_version": "a-share-monitor.real-snapshot.v1",
        "status": "DATA_DEGRADED",
        "generated_at": _now().isoformat(),
        "trade_date": trade_date,
        "data_freshness": {
            "mode": "real",
            "requested_trade_date": requested_trade_date,
            "resolved_trade_date": trade_date,
            "current_date": _now().date().isoformat(),
            "fallback_to_fixture": False,
        },
        "data_acquisition": acquisition,
        "decision_boundary": _decision_boundary(
            "market data coverage is insufficient for a buy recommendation; "
            "return control to the user and retry later"
        ),
        "market": _market_summary(quotes),
        "selection_summary": {
            "min_risk_reward": 1.5,
            "planned_symbols": [],
            "watchlist_symbols": [],
            "recommendation_count": 0,
        },
        "recommendations": [],
        "watchlist": [],
    }
    report["critic_review"] = _review_real_snapshot(report)
    return report


def _apply_data_quality_gate(report: dict[str, Any]) -> None:
    acquisition = report["data_acquisition"]
    if acquisition["quality_state"] == "usable":
        return
    report["status"] = "DATA_DEGRADED"
    report["recommendations"] = []
    report["selection_summary"]["planned_symbols"] = []
    report["selection_summary"]["recommendation_count"] = 0
    report["decision_boundary"]["disclaimer"] = (
        "market data coverage is insufficient for a buy recommendation; "
        "return control to the user and retry later"
    )


def _data_acquisition_summary(
    quotes: list[dict[str, Any]],
    *,
    kline_attempt_count: int = 0,
    kline_success_count: int = 0,
    error: str | None = None,
) -> dict[str, Any]:
    source_counts = Counter(str(row.get("source") or "unknown") for row in quotes)
    primary_quote_count = source_counts.get(
        "tencent_batch_quote", 0
    ) + source_counts.get("eastmoney_quote", 0)
    minimum_full_market_quotes = 500
    if not quotes:
        quality_state = "unavailable"
    elif primary_quote_count >= minimum_full_market_quotes:
        quality_state = "usable"
    else:
        quality_state = "degraded"
    channels = [
        {
            "name": "tencent_batch_quote",
            "purpose": "A-share quote universe, breadth, amount, and price snapshot",
            "usable_records": source_counts.get("tencent_batch_quote", 0),
        },
        {
            "name": "eastmoney_quote",
            "purpose": "backup A-share quote universe when Tencent batch quote fails",
            "usable_records": source_counts.get("eastmoney_quote", 0),
        },
        {
            "name": "eastmoney_kline",
            "purpose": "daily kline history for technical confirmation",
            "attempted_symbols": kline_attempt_count,
            "successful_symbols": kline_success_count,
        },
        {
            "name": "tencent_kline",
            "purpose": "fallback daily kline history when Eastmoney kline fails",
            "usable_records": source_counts.get("fallback_kline_pool", 0),
        },
    ]
    return {
        "channels": channels,
        "quality_state": quality_state,
        "minimum_full_market_quotes": minimum_full_market_quotes,
        "quote_count": len(quotes),
        "source_counts": dict(source_counts),
        "kline_attempt_count": kline_attempt_count,
        "kline_success_count": kline_success_count,
        "retry_policy": {
            "http_attempts_per_request": HTTP_ATTEMPTS,
            "http_timeout_seconds": HTTP_TIMEOUT_SECONDS,
            "fallback_trade_date_walk_days": 8,
            "fallback_probe_limit": FALLBACK_PROBE_LIMIT,
            "fixture_fallback": False,
        },
        "failure_action": "return_control_to_root_and_user",
        "error": error or "",
    }


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
        "amount": round(quote["amount"], 2),
        "main_net_inflow": round(quote["main_net_inflow"], 2),
        "entry_zone": [round(close - atr14 * 0.2, 2), entry_upper],
        "technical_exit_price": stop,
        "technical_exit_reason": "exit if price closes below the stop or loses EMA20 support",
        "fundamental_exit_trigger": "review and exit on material negative announcements, earnings downgrade, or regulatory risk",
        "ownership_flow_risk": _ownership_flow_note(quote),
        "time_exit_rule": "if no upside confirmation within 3-5 trading days, move to watchlist",
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
        "amount": round(quote["amount"], 2),
        "reason": reason,
        "ema20": round(ema20, 4),
        "ema60": round(ema60, 4),
    }


def _review_real_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    findings = []
    if report.get("status") == "DATA_DEGRADED":
        findings.append("market_data_coverage_degraded")
    if report.get("data_acquisition", {}).get("quality_state") != "usable":
        findings.append("data_acquisition_not_usable")
    if report.get("data_freshness", {}).get("mode") != "real":
        findings.append("not_real_market_mode")
    for item in report.get("recommendations", []):
        for field in (
            "technical_exit_price",
            "technical_exit_reason",
            "fundamental_exit_trigger",
            "ownership_flow_risk",
            "time_exit_rule",
        ):
            if not item.get(field):
                findings.append(f"{item.get('symbol', 'unknown')}:missing_{field}")
        if float(item.get("risk_reward") or 0.0) <= 1.5:
            findings.append(f"{item.get('symbol', 'unknown')}:risk_reward_below_1_5")
    return {
        "status": "pass" if not findings else "fail",
        "findings": findings,
        "confidence": "medium",
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
    return [_parse_eastmoney_kline(row) for row in rows]


def _fetch_tencent_kline(symbol: str, end_date: str) -> list[dict[str, float | str]]:
    prefix = "sh" if symbol.startswith(("6", "9")) else "sz"
    param = f"{prefix}{symbol},day,2025-01-01,{end_date},400,qfq"
    payload = _get_json(
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
        + urllib.parse.urlencode({"param": param})
    )
    data = payload.get("data", {}).get(f"{prefix}{symbol}", {})
    rows = data.get("qfqday") or data.get("day") or []
    result = []
    previous_close = 0.0
    for row in rows:
        trade_date, open_price, close, high, low, volume = row[:6]
        close_value = float(close)
        pct_change = (
            ((close_value / previous_close) - 1) * 100 if previous_close else 0.0
        )
        result.append(
            {
                "date": trade_date,
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


def _get_json(url: str) -> dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0 AShareMonitor/0.1",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://quote.eastmoney.com/",
    }
    last_error: Exception | None = None
    for attempt in range(1, HTTP_ATTEMPTS + 1):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(
                request, timeout=HTTP_TIMEOUT_SECONDS
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, http.client.RemoteDisconnected) as exc:
            last_error = exc
            time.sleep(0.5 * attempt)
    raise RuntimeError(f"market data request failed after retries: {last_error}")


def _parse_eastmoney_kline(row: str) -> dict[str, float | str]:
    parts = row.split(",")
    return {
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
        "source": "eastmoney_quote",
    }


def _is_usable_quote(row: dict[str, Any]) -> bool:
    try:
        name = str(row.get("name") or row["f14"])
        close = float(row.get("close") or row["f2"])
        amount = float(row.get("amount") or row["f6"])
    except (KeyError, TypeError, ValueError):
        return False
    return close > 0 and amount > 0 and "ST" not in name.upper()


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


def _decision_boundary(disclaimer: str) -> dict[str, Any]:
    return {
        "real_trading_enabled": False,
        "final_decision_owner": "user",
        "disclaimer": disclaimer,
    }


def _ownership_flow_note(quote: dict[str, Any]) -> str:
    inflow = float(quote.get("main_net_inflow") or 0.0)
    if inflow < 0:
        return "main net inflow is negative; watch for institution exit against retail crowding"
    if inflow > 0:
        return "main net inflow is positive in the public quote snapshot"
    return "ownership flow data is incomplete; user should verify institution/retail positioning"


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


def _previous_weekday(value: date) -> date:
    current = value - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _now() -> datetime:
    return datetime.now(CHINA_TZ)


def _progress(
    callback: Callable[[str, dict[str, Any]], None] | None,
    stage: str,
    payload: dict[str, Any],
) -> None:
    if callback is not None:
        callback(stage, payload)
