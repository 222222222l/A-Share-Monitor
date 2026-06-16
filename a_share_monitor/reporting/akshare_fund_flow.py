"""Optional AkShare fund-flow adapter.

AkShare is not a required dependency for the package. When it is installed, this
adapter can be used as a secondary source after direct public endpoints fail.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from a_share_monitor.config import DEFAULT_STRATEGY_CONFIG
from a_share_monitor.config import get_bool
from a_share_monitor.reporting.fund_flow import classify_counterparty_signal
from a_share_monitor.reporting.fund_flow import risk_note

AKSHARE_SOURCE = "akshare_stock_individual_fund_flow"


def fetch_akshare_symbol_fund_flows(
    symbols: list[str],
    strategy_config: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Fetch latest per-symbol order-size fund-flow rows through AkShare."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    if not symbols:
        return {}, _summary("skipped", 0, 0, "")
    try:
        import akshare as ak  # type: ignore[import-not-found]
    except ImportError as exc:
        return {}, _summary(
            "unavailable", len(symbols), 0, f"akshare not installed: {exc}"
        )

    result: dict[str, dict[str, Any]] = {}
    last_error = ""
    for symbol in sorted(set(symbols)):
        try:
            with _system_proxy_guard(strategy_config):
                row = _latest_individual_flow_row(ak, symbol)
        except Exception as exc:  # noqa: BLE001 - optional external source isolation
            last_error = str(exc)
            continue
        parsed = normalize_akshare_individual_fund_flow(row, symbol, strategy_config)
        if parsed:
            result[symbol] = parsed
    status = "usable" if result else "unavailable"
    return result, _summary(status, len(symbols), len(result), last_error)


def normalize_akshare_individual_fund_flow(
    row: dict[str, Any],
    symbol: str,
    strategy_config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Normalize an AkShare stock_individual_fund_flow row."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    super_large_net = _pick_float(row, "超大单净流入-净额", "超大单净流入")
    large_net = _pick_float(row, "大单净流入-净额", "大单净流入")
    medium_net = _pick_float(row, "中单净流入-净额", "中单净流入")
    small_net = _pick_float(row, "小单净流入-净额", "小单净流入")
    institutional_net = super_large_net + large_net
    retail_proxy_net = medium_net + small_net
    signal = classify_counterparty_signal(
        institutional_net=institutional_net,
        retail_proxy_net=retail_proxy_net,
        strategy_config=strategy_config,
    )
    return {
        "symbol": symbol,
        "name": str(row.get("名称") or row.get("name") or ""),
        "industry_name": str(row.get("所属板块") or row.get("行业") or ""),
        "concept_tags": [],
        "source": AKSHARE_SOURCE,
        "trade_date": str(row.get("日期") or ""),
        "proxy_note": (
            "AkShare order-size proxy: super-large/large orders approximate "
            "institutional flow; medium/small orders approximate retail flow"
        ),
        "main_net_inflow": _pick_float(row, "主力净流入-净额", "主力净流入"),
        "main_net_inflow_pct": _pick_float(row, "主力净流入-净占比", "主力净占比"),
        "super_large_net": super_large_net,
        "super_large_net_pct": _pick_float(row, "超大单净流入-净占比", "超大单净占比"),
        "large_net": large_net,
        "large_net_pct": _pick_float(row, "大单净流入-净占比", "大单净占比"),
        "medium_net": medium_net,
        "medium_net_pct": _pick_float(row, "中单净流入-净占比", "中单净占比"),
        "small_net": small_net,
        "small_net_pct": _pick_float(row, "小单净流入-净占比", "小单净占比"),
        "institutional_proxy_net": institutional_net,
        "retail_proxy_net": retail_proxy_net,
        "counterparty_signal": signal,
        "risk_note": risk_note(signal),
    }


def _latest_individual_flow_row(ak: Any, symbol: str) -> dict[str, Any]:
    market = _akshare_market(symbol)
    frame = ak.stock_individual_fund_flow(stock=symbol, market=market)
    if frame is None or getattr(frame, "empty", True):
        raise RuntimeError(
            f"AkShare returned no individual fund-flow rows for {symbol}"
        )
    return dict(frame.iloc[-1].to_dict())


@contextmanager
def _system_proxy_guard(strategy_config: dict[str, Any]) -> Iterator[None]:
    if not get_bool(strategy_config, "data_quality.disable_system_proxy", True):
        yield
        return
    old_no_proxy = os.environ.get("NO_PROXY")
    old_no_proxy_lower = os.environ.get("no_proxy")
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    try:
        yield
    finally:
        _restore_env("NO_PROXY", old_no_proxy)
        _restore_env("no_proxy", old_no_proxy_lower)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def _akshare_market(symbol: str) -> str:
    if symbol.startswith(("6", "9")):
        return "sh"
    if symbol.startswith(("0", "2", "3")):
        return "sz"
    if symbol.startswith(("4", "8")):
        return "bj"
    return "sh"


def _pick_float(row: dict[str, Any], *names: str) -> float:
    for name in names:
        if name in row:
            return _to_float(row.get(name))
    for key, value in row.items():
        key_text = str(key)
        if all(part in key_text for part in names[0].split("-")):
            return _to_float(value)
    return 0.0


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None, "--", "-"):
            return default
        if isinstance(value, str):
            return float(value.replace(",", "").replace("%", ""))
        return float(value)
    except (TypeError, ValueError):
        return default


def _summary(status: str, requested: int, usable: int, error: str) -> dict[str, Any]:
    return {
        "source": AKSHARE_SOURCE,
        "status": status,
        "requested_symbols": requested,
        "usable_records": usable,
        "error": error,
    }
