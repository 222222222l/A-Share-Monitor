"""10jqka selected-symbol fund-flow adapter."""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from typing import Any

from a_share_monitor.config import DEFAULT_STRATEGY_CONFIG
from a_share_monitor.config import get_bool
from a_share_monitor.config import get_float
from a_share_monitor.config import get_int
from a_share_monitor.reporting.fund_flow import classify_counterparty_signal
from a_share_monitor.reporting.fund_flow import risk_note

THS_FUND_FLOW_SOURCE = "10jqka_real_funds"
THS_AMOUNT_MULTIPLIER = 10_000


def fetch_ths_symbol_fund_flows(
    symbols: list[str],
    strategy_config: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Fetch selected-symbol real-time fund-flow data from 10jqka."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    if not symbols:
        return {}, _summary("skipped", 0, 0, "")
    if not get_bool(strategy_config, "tonghuashun.enabled", True):
        return {}, _summary("skipped", len(symbols), 0, "10jqka source disabled")

    result: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    delay = get_float(strategy_config, "tonghuashun.request_delay_seconds", 0.25)
    for index, symbol in enumerate(sorted(set(symbols))):
        if index:
            time.sleep(delay)
        try:
            payload = _fetch_real_funds(symbol, strategy_config)
        except RuntimeError as exc:
            errors[symbol] = str(exc)
            continue
        parsed = normalize_ths_real_funds(symbol, payload, strategy_config)
        if parsed:
            result[symbol] = parsed
        else:
            errors[symbol] = "10jqka realFunds returned no usable fund-flow fields"

    status = "usable" if result else "unavailable"
    error = "; ".join(f"{symbol}: {error}" for symbol, error in errors.items())
    return result, _summary(status, len(symbols), len(result), error, errors)


def normalize_ths_real_funds(
    symbol: str,
    payload: dict[str, Any],
    strategy_config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Normalize 10jqka /spService/{code}/Funds/realFunds JSON."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    title = payload.get("title") or {}
    if not isinstance(title, dict):
        return None
    flash = payload.get("flash") or []
    if not isinstance(flash, list):
        flash = []
    flash_values = _flash_values(flash)
    large_in = flash_values.get("large_in", 0.0)
    large_out = flash_values.get("large_out", 0.0)
    medium_in = flash_values.get("medium_in", 0.0)
    medium_out = flash_values.get("medium_out", 0.0)
    small_in = flash_values.get("small_in", 0.0)
    small_out = flash_values.get("small_out", 0.0)
    large_net = large_in - large_out
    medium_net = medium_in - medium_out
    small_net = small_in - small_out
    institutional_net = large_net
    retail_proxy_net = medium_net + small_net
    total_inflow = _money_wan(title.get("zlr"))
    total_outflow = _money_wan(title.get("zlc"))
    main_net = _money_wan(title.get("je"))
    if main_net == 0.0 and (total_inflow or total_outflow):
        main_net = total_inflow - total_outflow
    if not any((total_inflow, total_outflow, large_net, medium_net, small_net)):
        return None
    signal = classify_counterparty_signal(
        institutional_net=institutional_net,
        retail_proxy_net=retail_proxy_net,
        strategy_config=strategy_config,
    )
    field = payload.get("field") or {}
    if not isinstance(field, dict):
        field = {}
    return {
        "symbol": symbol,
        "name": str(field.get("stockname") or field.get("name") or ""),
        "industry_name": str(field.get("hyname") or ""),
        "concept_tags": [],
        "source": THS_FUND_FLOW_SOURCE,
        "proxy_note": (
            "10jqka selected-symbol realFunds: large orders approximate "
            "institutional flow; medium/small orders approximate retail flow"
        ),
        "main_net_inflow": main_net,
        "main_net_inflow_pct": 0.0,
        "super_large_net": 0.0,
        "super_large_net_pct": 0.0,
        "large_net": large_net,
        "large_net_pct": 0.0,
        "medium_net": medium_net,
        "medium_net_pct": 0.0,
        "small_net": small_net,
        "small_net_pct": 0.0,
        "institutional_proxy_net": institutional_net,
        "retail_proxy_net": retail_proxy_net,
        "total_inflow": total_inflow,
        "total_outflow": total_outflow,
        "counterparty_signal": signal,
        "risk_note": risk_note(signal),
    }


def _fetch_real_funds(
    symbol: str,
    strategy_config: dict[str, Any],
) -> dict[str, Any]:
    url = f"https://stockpage.10jqka.com.cn/spService/{symbol}/Funds/realFunds"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AShareMonitor/0.1",
            "Accept": "application/json,text/plain,*/*",
            "Referer": f"https://stockpage.10jqka.com.cn/{symbol}/funds/",
        },
    )
    attempts = get_int(strategy_config, "tonghuashun.http_attempts_per_request", 2)
    timeout = get_int(strategy_config, "tonghuashun.request_timeout_seconds", 10)
    opener = _opener(strategy_config)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with opener.open(request, timeout=timeout) as response:
                text = response.read().decode("utf-8", errors="ignore")
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise RuntimeError("10jqka realFunds returned non-object JSON")
            return payload
        except (
            RuntimeError,
            json.JSONDecodeError,
            urllib.error.URLError,
            http.client.RemoteDisconnected,
        ) as exc:
            last_error = exc
            time.sleep(0.4 * attempt)
    raise RuntimeError(f"10jqka realFunds request failed: {last_error}")


def _opener(strategy_config: dict[str, Any]) -> urllib.request.OpenerDirector:
    if get_bool(strategy_config, "data_quality.disable_system_proxy", True):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def _flash_values(rows: list[Any]) -> dict[str, float]:
    values = {
        "large_in": 0.0,
        "large_out": 0.0,
        "medium_in": 0.0,
        "medium_out": 0.0,
        "small_in": 0.0,
        "small_out": 0.0,
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        amount = _money_wan(row.get("sr"))
        if "大单流入" in name:
            values["large_in"] += amount
        elif "大单流出" in name:
            values["large_out"] += amount
        elif "中单流入" in name:
            values["medium_in"] += amount
        elif "中单流出" in name:
            values["medium_out"] += amount
        elif "小单流入" in name:
            values["small_in"] += amount
        elif "小单流出" in name:
            values["small_out"] += amount
    return values


def _summary(
    status: str,
    requested: int,
    usable: int,
    error: str,
    symbol_errors: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "source": THS_FUND_FLOW_SOURCE,
        "status": status,
        "requested_symbols": requested,
        "usable_records": usable,
        "source_counts": {THS_FUND_FLOW_SOURCE: usable} if usable else {},
        "symbol_errors": symbol_errors or {},
        "error": error,
    }


def _money_wan(value: Any) -> float:
    return _to_float(value) * THS_AMOUNT_MULTIPLIER


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None, "--"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
