"""Selected-symbol Eastmoney quote supplements for valuation risk fields."""

from __future__ import annotations

import time
import urllib.parse
from typing import Any, Callable

from a_share_monitor.config import DEFAULT_STRATEGY_CONFIG
from a_share_monitor.config import get_bool
from a_share_monitor.config import get_float
from a_share_monitor.config import get_int

EASTMONEY_SUPPLEMENT_SOURCE = "eastmoney_selected_quote_supplement"
EASTMONEY_SUPPLEMENT_FIELDS = "f12,f14,f2,f3,f5,f6,f7,f8,f9,f10,f20,f21,f23"


def attach_selected_quote_supplements(
    buy_ready: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    strategy_config: dict[str, Any] | None,
    progress: Callable[[str, dict[str, Any]], None] | None,
    get_json,
) -> dict[str, Any]:
    """Attach Eastmoney PE/PB/volume-ratio fields to selected symbols only."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    if not get_bool(strategy_config, "eastmoney_supplement.enabled", True):
        return _summary("skipped", 0, 0, "", {}, scope="disabled")

    buy_symbols = _symbols(buy_ready)
    include_watchlist = get_bool(
        strategy_config, "eastmoney_supplement.include_watchlist", True
    )
    selected = buy_symbols + (_symbols(watchlist) if include_watchlist else [])
    selected = _dedupe(selected)
    if not selected:
        return _summary("skipped", 0, 0, "", {}, scope="empty")

    _progress(
        progress,
        "eastmoney_supplement_start",
        {"source": EASTMONEY_SUPPLEMENT_SOURCE, "symbols": len(selected)},
    )
    records, summary = fetch_selected_quote_supplements(
        selected, get_json, strategy_config, scope="buy_ready_and_watchlist"
    )
    initial_error = str(summary.get("error") or "")
    if (
        not records
        and include_watchlist
        and buy_symbols
        and get_bool(
            strategy_config, "eastmoney_supplement.fallback_buy_ready_only", True
        )
    ):
        _progress(
            progress,
            "eastmoney_supplement_retry_buy_ready_only",
            {"source": EASTMONEY_SUPPLEMENT_SOURCE, "symbols": len(buy_symbols)},
        )
        records, summary = fetch_selected_quote_supplements(
            buy_symbols, get_json, strategy_config, scope="buy_ready_only"
        )
        summary["fallback_from_scope"] = "buy_ready_and_watchlist"
        summary["fallback_reason"] = initial_error

    _attach_rows(buy_ready, records)
    _attach_rows(watchlist, records)
    _progress(
        progress,
        "eastmoney_supplement_done",
        {
            "source": EASTMONEY_SUPPLEMENT_SOURCE,
            "status": summary["status"],
            "requested_symbols": summary["requested_symbols"],
            "usable_records": summary["usable_records"],
            "scope": summary["scope"],
        },
    )
    return summary


def fetch_selected_quote_supplements(
    symbols: list[str],
    get_json,
    strategy_config: dict[str, Any] | None = None,
    *,
    scope: str = "selected_symbols",
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Fetch valuation and volume-ratio fields for a small symbol set."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    batch_size = get_int(strategy_config, "eastmoney_supplement.batch_size", 20)
    delay = get_float(
        strategy_config, "eastmoney_supplement.request_delay_seconds", 0.8
    )
    result: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for index, batch in enumerate(_chunks(_dedupe(symbols), batch_size)):
        if index:
            time.sleep(delay)
        try:
            payload = get_json(
                _selected_quote_url(batch), strategy_config=strategy_config
            )
        except RuntimeError as exc:
            errors[",".join(batch)] = str(exc)
            break
        rows = payload.get("data", {}).get("diff") or []
        for row in rows:
            parsed = normalize_quote_supplement(row, strategy_config)
            if parsed:
                result[parsed["symbol"]] = parsed
    status = "usable" if result else "unavailable"
    error = "; ".join(f"{key}: {value}" for key, value in errors.items())
    return result, _summary(
        status, len(_dedupe(symbols)), len(result), error, errors, scope=scope
    )


def normalize_quote_supplement(
    row: dict[str, Any],
    strategy_config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Normalize selected Eastmoney quote fields."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    symbol = str(row.get("f12") or "")
    if not symbol:
        return None
    parsed = {
        "source": EASTMONEY_SUPPLEMENT_SOURCE,
        "symbol": symbol,
        "name": str(row.get("f14") or ""),
        "close": _to_float(row.get("f2")),
        "pct_change": _to_float(row.get("f3")),
        "volume": _to_float(row.get("f5")),
        "amount": _to_float(row.get("f6")),
        "amplitude": _to_float(row.get("f7")),
        "turnover_rate": _to_float(row.get("f8")),
        "pe_dynamic": _to_float(row.get("f9")),
        "volume_ratio": _to_float(row.get("f10")),
        "total_market_cap": _to_float(row.get("f20")),
        "float_market_cap": _to_float(row.get("f21")),
        "pb": _to_float(row.get("f23")),
    }
    parsed["valuation_risk_flags"] = valuation_risk_flags(parsed, strategy_config)
    return parsed


def valuation_risk_flags(
    parsed: dict[str, Any],
    strategy_config: dict[str, Any] | None = None,
) -> list[str]:
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    pe = float(parsed.get("pe_dynamic") or 0.0)
    pb = float(parsed.get("pb") or 0.0)
    volume_ratio = float(parsed.get("volume_ratio") or 0.0)
    turnover_rate = float(parsed.get("turnover_rate") or 0.0)
    flags = []
    if pe < 0:
        flags.append("negative_dynamic_pe")
    if pe >= get_float(strategy_config, "eastmoney_supplement.pe_high_threshold", 80):
        flags.append("high_dynamic_pe")
    if pb >= get_float(strategy_config, "eastmoney_supplement.pb_high_threshold", 8):
        flags.append("high_pb")
    if volume_ratio >= get_float(
        strategy_config, "eastmoney_supplement.volume_ratio_high_threshold", 3
    ):
        flags.append("high_volume_ratio")
    if turnover_rate >= get_float(
        strategy_config, "eastmoney_supplement.turnover_high_threshold", 10
    ):
        flags.append("high_turnover")
    if "high_volume_ratio" in flags and "high_turnover" in flags:
        flags.append("volume_turnover_crowding")
    return flags


def _selected_quote_url(symbols: list[str]) -> str:
    query = urllib.parse.urlencode(
        {
            "fltt": 2,
            "invt": 2,
            "fields": EASTMONEY_SUPPLEMENT_FIELDS,
            "secids": ",".join(_secid(symbol) for symbol in symbols),
        }
    )
    return f"https://push2.eastmoney.com/api/qt/ulist.np/get?{query}"


def _attach_rows(
    rows: list[dict[str, Any]], records: dict[str, dict[str, Any]]
) -> None:
    for row in rows:
        parsed = records.get(str(row.get("symbol") or ""))
        if not parsed:
            continue
        row["quote_supplement"] = parsed
        row["valuation_risk_flags"] = parsed.get("valuation_risk_flags", [])


def _symbols(rows: list[dict[str, Any]]) -> list[str]:
    return [str(row.get("symbol") or "") for row in rows if row.get("symbol")]


def _dedupe(symbols: list[str]) -> list[str]:
    result = []
    seen = set()
    for symbol in symbols:
        if not symbol or symbol in seen:
            continue
        result.append(symbol)
        seen.add(symbol)
    return result


def _secid(symbol: str) -> str:
    return ("1." if symbol.startswith(("6", "9")) else "0.") + symbol


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _summary(
    status: str,
    requested: int,
    usable: int,
    error: str,
    symbol_errors: dict[str, str],
    *,
    scope: str,
) -> dict[str, Any]:
    return {
        "source": EASTMONEY_SUPPLEMENT_SOURCE,
        "status": status,
        "scope": scope,
        "requested_symbols": requested,
        "usable_records": usable,
        "source_counts": {EASTMONEY_SUPPLEMENT_SOURCE: usable} if usable else {},
        "symbol_errors": symbol_errors,
        "error": error,
    }


def _progress(
    callback: Callable[[str, dict[str, Any]], None] | None,
    stage: str,
    payload: dict[str, Any],
) -> None:
    if callback is not None:
        callback(stage, payload)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None, "--"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
