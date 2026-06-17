"""Goldminer GM SDK data-source adapter.

GM's Python SDK loads native extensions and registers process-level exit hooks.
Run it in a short-lived subprocess so SDK failures cannot destabilize the
agent runtime.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from datetime import timedelta
from typing import Any, Callable

from a_share_monitor.config import DEFAULT_STRATEGY_CONFIG
from a_share_monitor.config import get_bool
from a_share_monitor.config import get_int
from a_share_monitor.config import get_setting
from a_share_monitor.reporting.fund_flow import classify_counterparty_signal
from a_share_monitor.reporting.fund_flow import risk_note

GM_QUOTE_SOURCE = "gm_current_quote"
GM_KLINE_SOURCE = "gm_history_kline"
GM_FUND_FLOW_SOURCE = "gm_money_flow"
_RESULT_PREFIX = "ASMONITOR_GM_JSON="


def fetch_gm_universe_quotes(
    *,
    strategy_config: dict[str, Any] | None = None,
    progress: Callable[[str, dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Fetch full-market A-share quotes from GM current quote APIs."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    _ensure_enabled(strategy_config)
    batch_size = get_int(strategy_config, "gm.quote_batch_size", 500)
    _progress(
        progress,
        "quote_source_start",
        {"source": GM_QUOTE_SOURCE, "batch_size": batch_size},
    )
    payload = _run_gm_request(
        {
            "action": "quotes",
            "quote_batch_size": batch_size,
            "token_env": _token_env(strategy_config),
            "service_addr_env": _service_addr_env(strategy_config),
        },
        strategy_config,
    )
    rows = [_normalize_gm_quote(row) for row in payload.get("quotes") or []]
    quotes = [row for row in rows if row is not None]
    if not quotes:
        raise RuntimeError("GM quote source returned no usable A-share quotes")
    _progress(
        progress,
        "quote_source_done",
        {"source": GM_QUOTE_SOURCE, "usable_quotes": len(quotes)},
    )
    return quotes


def fetch_gm_kline(
    symbol: str,
    end_date: str,
    *,
    strategy_config: dict[str, Any] | None = None,
) -> list[dict[str, float | str]]:
    """Fetch daily kline rows from GM history APIs."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    _ensure_enabled(strategy_config)
    start_date = _history_start_date(end_date)
    payload = _run_gm_request(
        {
            "action": "kline",
            "symbol": _gm_symbol(symbol),
            "start_time": start_date,
            "end_time": end_date,
            "token_env": _token_env(strategy_config),
            "service_addr_env": _service_addr_env(strategy_config),
        },
        strategy_config,
    )
    rows = payload.get("rows") or []
    return _normalize_gm_klines(rows)


def fetch_gm_symbol_fund_flows(
    symbols: list[str],
    strategy_config: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Fetch GM money-flow rows when the user's account has permission."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    if not symbols:
        return {}, _summary("skipped", 0, 0, "")
    try:
        _ensure_enabled(strategy_config)
        payload = _run_gm_request(
            {
                "action": "fund_flow",
                "symbols": [_gm_symbol(symbol) for symbol in sorted(set(symbols))],
                "token_env": _token_env(strategy_config),
                "service_addr_env": _service_addr_env(strategy_config),
            },
            strategy_config,
        )
    except RuntimeError as exc:
        return {}, _summary("unavailable", len(symbols), 0, str(exc))
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        parsed = _normalize_gm_fund_flow(row, strategy_config)
        if parsed:
            result[parsed["symbol"]] = parsed
    status = "usable" if result else "unavailable"
    error = "" if result else str(payload.get("error") or "no usable GM money flow")
    return result, _summary(status, len(symbols), len(result), error)


def gm_available(strategy_config: dict[str, Any] | None = None) -> bool:
    """Return whether GM is configured and likely callable."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    if not get_bool(strategy_config, "gm.enabled", True):
        return False
    return bool(_token(strategy_config))


def _run_gm_request(
    request: dict[str, Any],
    strategy_config: dict[str, Any],
) -> dict[str, Any]:
    timeout = get_int(strategy_config, "gm.request_timeout_seconds", 45)
    env = os.environ.copy()
    env["A_SHARE_MONITOR_GM_REQUEST"] = json.dumps(request, ensure_ascii=False)
    command = [_python_executable(strategy_config), "-u", "-c", _GM_SUBPROCESS_CODE]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            env=env,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"GM subprocess failed: {exc}") from exc
    payload = _extract_result(completed.stdout)
    if payload is None:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"GM subprocess returned no structured result: {detail}")
    if payload.get("status") != "ok":
        raise RuntimeError(str(payload.get("error") or "GM request failed"))
    return payload


def _extract_result(stdout: str) -> dict[str, Any] | None:
    for line in stdout.splitlines():
        if line.startswith(_RESULT_PREFIX):
            return json.loads(line[len(_RESULT_PREFIX) :])
    return None


def _ensure_enabled(strategy_config: dict[str, Any]) -> None:
    if not get_bool(strategy_config, "gm.enabled", True):
        raise RuntimeError("GM data source is disabled")
    if not _token(strategy_config):
        raise RuntimeError(f"GM token env is not set: {_token_env(strategy_config)}")


def _python_executable(strategy_config: dict[str, Any]) -> str:
    env_name = str(
        get_setting(
            strategy_config, "gm.python_executable_env", "A_SHARE_MONITOR_GM_PYTHON"
        )
    )
    configured = str(get_setting(strategy_config, "gm.python_executable", "") or "")
    return os.environ.get(env_name) or configured or sys.executable


def _token(strategy_config: dict[str, Any]) -> str:
    return os.environ.get(_token_env(strategy_config), "")


def _token_env(strategy_config: dict[str, Any]) -> str:
    return str(get_setting(strategy_config, "gm.token_env", "A_SHARE_MONITOR_GM_TOKEN"))


def _service_addr_env(strategy_config: dict[str, Any]) -> str:
    return str(
        get_setting(
            strategy_config, "gm.service_addr_env", "A_SHARE_MONITOR_GM_SERV_ADDR"
        )
    )


def _history_start_date(end_date: str) -> str:
    return (date.fromisoformat(end_date) - timedelta(days=520)).isoformat()


def _gm_symbol(symbol: str) -> str:
    if "." in symbol:
        return symbol
    exchange = "SHSE" if symbol.startswith(("6", "9")) else "SZSE"
    return f"{exchange}.{symbol}"


def _plain_symbol(symbol: str) -> str:
    return symbol.split(".", 1)[1] if "." in symbol else symbol


def _normalize_gm_quote(row: dict[str, Any]) -> dict[str, Any] | None:
    symbol = _plain_symbol(str(row.get("symbol") or ""))
    name = str(row.get("name") or "")
    close = _to_float(row.get("close"))
    amount = _to_float(row.get("amount"))
    if not symbol or close <= 0 or amount <= 0 or "ST" in name.upper():
        return None
    prev_close = _to_float(row.get("prev_close"))
    pct_change = ((close / prev_close) - 1) * 100 if prev_close > 0 else 0.0
    return {
        "symbol": symbol,
        "name": name,
        "close": close,
        "pct_change": pct_change,
        "volume": _to_float(row.get("volume")),
        "amount": amount,
        "high": _to_float(row.get("high")),
        "low": _to_float(row.get("low")),
        "open": _to_float(row.get("open")),
        "prev_close": prev_close,
        "float_market_cap": 0.0,
        "main_net_inflow": 0.0,
        "source": GM_QUOTE_SOURCE,
    }


def _normalize_gm_klines(rows: list[dict[str, Any]]) -> list[dict[str, float | str]]:
    result: list[dict[str, float | str]] = []
    previous_close = 0.0
    for row in rows:
        close = _to_float(row.get("close"))
        if close <= 0:
            continue
        pct_change = ((close / previous_close) - 1) * 100 if previous_close else 0.0
        result.append(
            {
                "date": str(row.get("date") or ""),
                "open": _to_float(row.get("open")),
                "close": close,
                "high": _to_float(row.get("high")),
                "low": _to_float(row.get("low")),
                "volume": _to_float(row.get("volume")),
                "amount": _to_float(row.get("amount")),
                "pct_change": pct_change,
                "turnover": _to_float(row.get("turnover")),
            }
        )
        previous_close = close
    return result


def _normalize_gm_fund_flow(
    row: dict[str, Any],
    strategy_config: dict[str, Any],
) -> dict[str, Any] | None:
    symbol = _plain_symbol(str(row.get("symbol") or ""))
    if not symbol:
        return None
    main_net = _first_float(row, "net_inflow", "main_net_inflow", "main_net_amount")
    institutional_net = _first_float(
        row,
        "institutional_net",
        "super_large_net",
        "large_net",
        "main_net_inflow",
        "net_inflow",
    )
    retail_proxy_net = _first_float(row, "retail_net", "small_net", "medium_net")
    signal = classify_counterparty_signal(
        institutional_net=institutional_net,
        retail_proxy_net=retail_proxy_net,
        strategy_config=strategy_config,
    )
    return {
        "symbol": symbol,
        "name": str(row.get("sec_name") or row.get("name") or ""),
        "industry_name": str(row.get("industry_name") or ""),
        "concept_tags": [],
        "source": GM_FUND_FLOW_SOURCE,
        "trade_date": str(row.get("trade_date") or ""),
        "proxy_note": "GM money-flow data; field availability depends on account permissions",
        "main_net_inflow": main_net,
        "main_net_inflow_pct": _first_float(row, "net_inflow_ratio", "main_net_pct"),
        "super_large_net": _first_float(row, "super_large_net"),
        "super_large_net_pct": _first_float(row, "super_large_net_pct"),
        "large_net": _first_float(row, "large_net"),
        "large_net_pct": _first_float(row, "large_net_pct"),
        "medium_net": _first_float(row, "medium_net"),
        "medium_net_pct": _first_float(row, "medium_net_pct"),
        "small_net": _first_float(row, "small_net"),
        "small_net_pct": _first_float(row, "small_net_pct"),
        "institutional_proxy_net": institutional_net,
        "retail_proxy_net": retail_proxy_net,
        "counterparty_signal": signal,
        "risk_note": risk_note(signal),
    }


def _first_float(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        if key in row:
            return _to_float(row.get(key))
    return 0.0


def _summary(status: str, requested: int, usable: int, error: str) -> dict[str, Any]:
    return {
        "source": GM_FUND_FLOW_SOURCE,
        "status": status,
        "requested_symbols": requested,
        "usable_records": usable,
        "source_counts": {GM_FUND_FLOW_SOURCE: usable} if usable else {},
        "error": error,
    }


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None, "--"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _progress(
    callback: Callable[[str, dict[str, Any]], None] | None,
    stage: str,
    payload: dict[str, Any],
) -> None:
    if callback is not None:
        callback(stage, payload)


_GM_SUBPROCESS_CODE = r"""
import json
import os
from datetime import date, datetime

PREFIX = "ASMONITOR_GM_JSON="


def emit(payload):
    print(PREFIX + json.dumps(payload, ensure_ascii=False, default=json_default), flush=True)


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def plain_symbol(symbol):
    return symbol.split(".", 1)[1] if "." in symbol else symbol


def quote_rows(api, batch_size):
    instruments = api.get_instruments(
        exchanges="SHSE,SZSE",
        sec_types=1,
        skip_suspended=True,
        skip_st=True,
        df=False,
    )
    meta = {item["symbol"]: item for item in instruments}
    symbols = sorted(meta)
    rows = []
    for start in range(0, len(symbols), batch_size):
        batch = symbols[start : start + batch_size]
        current_rows = api.current(symbols=",".join(batch))
        for item in current_rows:
            symbol = item.get("symbol")
            info = meta.get(symbol, {})
            rows.append(
                {
                    "symbol": symbol,
                    "name": info.get("sec_name", ""),
                    "close": item.get("price"),
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "volume": item.get("cum_volume"),
                    "amount": item.get("cum_amount"),
                    "prev_close": info.get("pre_close"),
                }
            )
    return rows


def kline_rows(api, request):
    rows = api.history(
        symbol=request["symbol"],
        frequency="1d",
        start_time=request["start_time"],
        end_time=request["end_time"],
        fields="symbol,eob,open,high,low,close,volume,amount",
        df=False,
    )
    return [
        {
            "date": item.get("eob"),
            "open": item.get("open"),
            "high": item.get("high"),
            "low": item.get("low"),
            "close": item.get("close"),
            "volume": item.get("volume"),
            "amount": item.get("amount"),
        }
        for item in rows
    ]


def main():
    request = json.loads(os.environ["A_SHARE_MONITOR_GM_REQUEST"])
    from gm import api

    token = os.environ.get(request.get("token_env") or "A_SHARE_MONITOR_GM_TOKEN", "")
    if token:
        api.set_token(token)
    service_addr_env = request.get("service_addr_env") or ""
    service_addr = os.environ.get(service_addr_env, "") if service_addr_env else ""
    if service_addr:
        api.set_serv_addr(service_addr)

    action = request["action"]
    if action == "quotes":
        emit({"status": "ok", "quotes": quote_rows(api, int(request["quote_batch_size"]))})
    elif action == "kline":
        emit({"status": "ok", "rows": kline_rows(api, request)})
    elif action == "fund_flow":
        rows = api.stk_get_money_flow(
            symbols=",".join(request["symbols"]),
            trade_date=request.get("trade_date") or None,
        )
        if hasattr(rows, "to_dict"):
            rows = rows.to_dict(orient="records")
        emit({"status": "ok", "rows": rows})
    else:
        emit({"status": "error", "error": f"unknown GM action: {action}"})


try:
    main()
except BaseException as exc:
    emit({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
"""
