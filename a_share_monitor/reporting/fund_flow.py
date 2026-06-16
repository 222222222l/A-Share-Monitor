"""Order-size fund-flow proxy for institution/retail counterparty signals."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from a_share_monitor.config import DEFAULT_STRATEGY_CONFIG
from a_share_monitor.config import get_bool
from a_share_monitor.config import get_float
from a_share_monitor.config import get_int

EASTMONEY_FUND_FLOW_FIELDS = (
    "f12,f14,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f100,f103"
)


def fetch_symbol_fund_flows(
    symbols: list[str],
    get_json,
    strategy_config: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Fetch fund-flow proxy fields for symbols through Eastmoney ulist."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    if not symbols:
        return {}, _summary("skipped", 0, 0, "")
    batch_size = get_int(strategy_config, "ownership_flow.batch_size", 80)
    result: dict[str, dict[str, Any]] = {}
    last_error = ""
    source_counts: dict[str, int] = {}
    for batch in _chunks(sorted(set(symbols)), batch_size):
        try:
            payload = get_json(_fund_flow_url(batch), strategy_config=strategy_config)
        except RuntimeError as exc:
            last_error = str(exc)
            continue
        for row in payload.get("data", {}).get("diff") or []:
            parsed = normalize_fund_flow(row, strategy_config)
            if parsed:
                result[parsed["symbol"]] = parsed
                _count_source(source_counts, parsed)
    missing = [symbol for symbol in sorted(set(symbols)) if symbol not in result]
    if missing and get_bool(strategy_config, "ownership_flow.akshare_enabled", True):
        akshare_result, akshare_summary = _fetch_akshare_missing(
            missing, strategy_config
        )
        if akshare_summary.get("error"):
            last_error = str(akshare_summary["error"])
        for symbol, parsed in akshare_result.items():
            result[symbol] = parsed
            _count_source(source_counts, parsed)
        missing = [symbol for symbol in sorted(set(symbols)) if symbol not in result]
    for symbol in missing:
        parsed = _fetch_history_fund_flow(symbol, get_json, strategy_config)
        if parsed:
            result[symbol] = parsed
            _count_source(source_counts, parsed)
    status = "usable" if result else "unavailable"
    return result, _summary(
        status, len(symbols), len(result), last_error, source_counts
    )


def normalize_fund_flow(
    row: dict[str, Any],
    strategy_config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    symbol = str(row.get("f12") or "")
    if not symbol:
        return None
    super_large_net = _to_float(row.get("f66"))
    large_net = _to_float(row.get("f72"))
    medium_net = _to_float(row.get("f78"))
    small_net = _to_float(row.get("f84"))
    institutional_net = super_large_net + large_net
    retail_proxy_net = medium_net + small_net
    signal = classify_counterparty_signal(
        institutional_net=institutional_net,
        retail_proxy_net=retail_proxy_net,
        strategy_config=strategy_config,
    )
    return {
        "symbol": symbol,
        "name": str(row.get("f14") or ""),
        "industry_name": str(row.get("f100") or ""),
        "concept_tags": _split_tags(row.get("f103")),
        "source": "eastmoney_order_size_fund_flow",
        "proxy_note": (
            "order-size proxy: super-large/large orders approximate institutional "
            "flow; medium/small orders approximate retail flow"
        ),
        "main_net_inflow": _to_float(row.get("f62")),
        "main_net_inflow_pct": _to_float(row.get("f184")),
        "super_large_net": super_large_net,
        "super_large_net_pct": _to_float(row.get("f69")),
        "large_net": large_net,
        "large_net_pct": _to_float(row.get("f75")),
        "medium_net": medium_net,
        "medium_net_pct": _to_float(row.get("f81")),
        "small_net": small_net,
        "small_net_pct": _to_float(row.get("f87")),
        "institutional_proxy_net": institutional_net,
        "retail_proxy_net": retail_proxy_net,
        "counterparty_signal": signal,
        "risk_note": risk_note(signal),
    }


def classify_counterparty_signal(
    *,
    institutional_net: float,
    retail_proxy_net: float,
    strategy_config: dict[str, Any] | None = None,
) -> str:
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    min_institutional = get_float(
        strategy_config, "ownership_flow.min_institutional_net_amount", 10_000_000
    )
    min_retail = get_float(
        strategy_config, "ownership_flow.min_retail_proxy_net_amount", 5_000_000
    )
    if institutional_net <= -min_institutional and retail_proxy_net >= min_retail:
        return "retail_crowding_institution_exit_risk"
    if institutional_net >= min_institutional and retail_proxy_net <= -min_retail:
        return "retail_exit_institution_accumulation_opportunity"
    if institutional_net >= min_institutional:
        return "institutional_accumulation"
    if institutional_net <= -min_institutional:
        return "institutional_exit"
    return "neutral_or_incomplete"


def risk_note(signal: str) -> str:
    if signal == "retail_crowding_institution_exit_risk":
        return "retail proxy inflow while institutional proxy exits; treat as risk"
    if signal == "retail_exit_institution_accumulation_opportunity":
        return "institutional proxy accumulation with retail proxy exit support"
    if signal == "institutional_accumulation":
        return "institutional proxy net inflow is positive"
    if signal == "institutional_exit":
        return "institutional proxy net inflow is negative"
    return "order-size fund-flow proxy is neutral or incomplete"


def _fund_flow_url(symbols: list[str]) -> str:
    query = urllib.parse.urlencode(
        {
            "fltt": 2,
            "invt": 2,
            "fields": EASTMONEY_FUND_FLOW_FIELDS,
            "secids": ",".join(_secid(symbol) for symbol in symbols),
        }
    )
    return f"https://push2.eastmoney.com/api/qt/ulist.np/get?{query}"


def _fetch_history_fund_flow(
    symbol: str,
    get_json,
    strategy_config: dict[str, Any],
) -> dict[str, Any] | None:
    limit = get_int(strategy_config, "ownership_flow.fallback_history_limit", 5)
    query = urllib.parse.urlencode(
        {
            "lmt": limit,
            "klt": 101,
            "secid": _secid(symbol),
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
        }
    )
    try:
        payload = get_json(
            f"https://push2his.eastmoney.com/api/qt/stock/fflow/kline/get?{query}",
            strategy_config=strategy_config,
        )
    except RuntimeError:
        return None
    rows = payload.get("data", {}).get("klines") or []
    if not rows:
        return None
    return _normalize_history_fund_flow(
        symbol, payload.get("data", {}), rows[-1], strategy_config
    )


def _normalize_history_fund_flow(
    symbol: str,
    data: dict[str, Any],
    row: str,
    strategy_config: dict[str, Any],
) -> dict[str, Any] | None:
    parts = row.split(",")
    if len(parts) < 6:
        return None
    main_net = _to_float(parts[1])
    small_net = _to_float(parts[2])
    medium_net = _to_float(parts[3])
    large_net = _to_float(parts[4])
    super_large_net = _to_float(parts[5])
    institutional_net = super_large_net + large_net
    retail_proxy_net = medium_net + small_net
    signal = classify_counterparty_signal(
        institutional_net=institutional_net,
        retail_proxy_net=retail_proxy_net,
        strategy_config=strategy_config,
    )
    return {
        "symbol": symbol,
        "name": str(data.get("name") or ""),
        "industry_name": "",
        "concept_tags": [],
        "source": "eastmoney_history_fund_flow",
        "trade_date": parts[0],
        "proxy_note": (
            "historical order-size proxy: super-large/large orders approximate "
            "institutional flow; medium/small orders approximate retail flow"
        ),
        "main_net_inflow": main_net,
        "main_net_inflow_pct": 0.0,
        "super_large_net": super_large_net,
        "super_large_net_pct": 0.0,
        "large_net": large_net,
        "large_net_pct": 0.0,
        "medium_net": medium_net,
        "medium_net_pct": 0.0,
        "small_net": small_net,
        "small_net_pct": 0.0,
        "institutional_proxy_net": institutional_net,
        "retail_proxy_net": retail_proxy_net,
        "counterparty_signal": signal,
        "risk_note": risk_note(signal),
    }


def _secid(symbol: str) -> str:
    return ("1." if symbol.startswith(("6", "9")) else "0.") + symbol


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _fetch_akshare_missing(
    symbols: list[str],
    strategy_config: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    from a_share_monitor.reporting.akshare_fund_flow import (
        fetch_akshare_symbol_fund_flows,
    )

    return fetch_akshare_symbol_fund_flows(symbols, strategy_config)


def _count_source(source_counts: dict[str, int], parsed: dict[str, Any]) -> None:
    source = str(parsed.get("source") or "unknown")
    source_counts[source] = source_counts.get(source, 0) + 1


def _summary(
    status: str,
    requested: int,
    usable: int,
    error: str,
    source_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "source": "mixed_order_size_fund_flow",
        "status": status,
        "requested_symbols": requested,
        "usable_records": usable,
        "source_counts": source_counts or {},
        "error": error,
    }


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None, "--"):
            return default
        if isinstance(value, str) and value.startswith("{"):
            return float(json.loads(value))
        return float(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _split_tags(value: Any) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]
