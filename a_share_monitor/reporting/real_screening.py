"""Deterministic stock-level screening for real-market reports."""

from __future__ import annotations

from typing import Any

from a_share_monitor.config import get_float
from a_share_monitor.config import get_int
from a_share_monitor.reporting.technical_math import atr
from a_share_monitor.reporting.technical_math import ema


def technical_signal(
    quote: dict[str, Any],
    rows: list[dict[str, Any]],
    strategy_config: dict[str, Any],
) -> dict[str, Any]:
    closes = [float(row["close"]) for row in rows]
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    close = closes[-1]
    ema_fast_window = get_int(strategy_config, "technical.ema_fast", 5)
    ema_mid_window = get_int(strategy_config, "technical.ema_mid", 10)
    ema_trend_window = get_int(strategy_config, "technical.ema_trend", 20)
    ema_long_window = get_int(strategy_config, "technical.ema_long", 60)
    atr_window = get_int(strategy_config, "technical.atr_window", 14)
    ema_fast = ema(closes, ema_fast_window)
    ema_mid = ema(closes, ema_mid_window)
    ema_trend = ema(closes, ema_trend_window)
    ema_long = ema(closes, ema_long_window)
    atr_value = atr(highs, lows, closes, atr_window)
    ema_long_tolerance = get_float(
        strategy_config, "technical.ema_long_tolerance", 0.995
    )
    near_trend_ema_pct = get_float(
        strategy_config, "technical.near_trend_ema_pct", 0.08
    )
    entry_atr_buffer = get_float(strategy_config, "technical.entry_atr_buffer", 0.2)
    stop_atr_buffer = get_float(strategy_config, "technical.stop_atr_buffer", 0.35)
    stop_lookback_days = get_int(strategy_config, "technical.stop_lookback_days", 10)
    target_lookback_days = get_int(
        strategy_config, "technical.target_lookback_days", 20
    )
    target_risk_multiple = get_float(
        strategy_config, "technical.target_risk_multiple", 1.6
    )
    min_price_risk_pct = get_float(
        strategy_config, "technical.min_price_risk_pct", 0.01
    )
    min_risk_reward = get_float(strategy_config, "risk_preference.min_risk_reward", 1.5)

    trend_checks = [
        _check("close_above_trend_ema", close, ">", ema_trend, close > ema_trend),
        _check(
            "trend_ema_aligned_with_long_ema",
            ema_trend,
            ">=",
            ema_long * ema_long_tolerance,
            ema_trend >= ema_long * ema_long_tolerance,
        ),
        _check("close_above_fast_ema", close, ">=", ema_fast, close >= ema_fast),
        _check("close_above_mid_ema", close, ">=", ema_mid, close >= ema_mid),
    ]
    unmet = [item for item in trend_checks if not item["passed"]]
    if unmet:
        return _watch_or_reject(
            quote,
            close,
            ema_trend,
            ema_long,
            "technical_signal_not_ready",
            unmet,
            strategy_config,
        )

    stop = round(
        max(min(lows[-stop_lookback_days:]), ema_trend - atr_value * stop_atr_buffer),
        2,
    )
    entry_upper = round(close + atr_value * entry_atr_buffer, 2)
    risk = max(entry_upper - stop, close * min_price_risk_pct)
    target = round(
        max(
            max(highs[-target_lookback_days:]),
            entry_upper + risk * target_risk_multiple,
        ),
        2,
    )
    risk_reward = round((target - entry_upper) / risk, 4)
    distance_to_trend = abs(close / ema_trend - 1)
    setup_checks = [
        _check(
            "risk_reward_above_minimum",
            risk_reward,
            ">",
            min_risk_reward,
            risk_reward > min_risk_reward,
        ),
        _check(
            "near_trend_ema",
            distance_to_trend,
            "<=",
            near_trend_ema_pct,
            distance_to_trend <= near_trend_ema_pct,
        ),
    ]
    unmet = [item for item in setup_checks if not item["passed"]]
    if unmet:
        return _watch_or_reject(
            quote,
            close,
            ema_trend,
            ema_long,
            "risk_reward_or_entry_not_ready",
            unmet,
            strategy_config,
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
        "entry_zone": [round(close - atr_value * entry_atr_buffer, 2), entry_upper],
        "technical_exit_price": stop,
        "technical_exit_reason": "exit if price closes below the stop or loses EMA20 support",
        "fundamental_exit_trigger": "review and exit on material negative announcements, earnings downgrade, or regulatory risk",
        "ownership_flow_risk": ownership_flow_note(quote),
        "time_exit_rule": "if no upside confirmation within 3-5 trading days, move to watchlist",
        "target_1": target,
        "risk_reward": risk_reward,
        "technical_reason": (
            f"close>{ema_trend:.2f} EMA{ema_trend_window} and "
            f"EMA{ema_trend_window} aligns with EMA{ema_long_window} {ema_long:.2f}"
        ),
    }


def ownership_flow_note(quote: dict[str, Any]) -> str:
    inflow = float(quote.get("main_net_inflow") or 0.0)
    if inflow < 0:
        return "main net inflow is negative; watch for institution exit against retail crowding"
    if inflow > 0:
        return "main net inflow is positive in the public quote snapshot"
    return "ownership flow data is incomplete; user should verify institution/retail positioning"


def _watch_or_reject(
    quote: dict[str, Any],
    close: float,
    ema20: float,
    ema60: float,
    reason: str,
    unmet_conditions: list[dict[str, Any]],
    strategy_config: dict[str, Any],
) -> dict[str, Any]:
    watchlist_min_amount = get_float(
        strategy_config, "quote_screen.watchlist_min_amount", 120_000_000
    )
    if quote["amount"] < watchlist_min_amount:
        return {"status": "rejected", "symbol": quote["symbol"], "reason": "liquidity"}
    return {
        "status": "watchlist",
        "symbol": quote["symbol"],
        "name": quote["name"],
        "close": close,
        "pct_change": quote["pct_change"],
        "amount": round(quote["amount"], 2),
        "reason": reason,
        "unmet_conditions": unmet_conditions,
        "ema20": round(ema20, 4),
        "ema60": round(ema60, 4),
    }


def _check(
    code: str,
    actual: float,
    operator: str,
    threshold: float,
    passed: bool,
) -> dict[str, Any]:
    return {
        "code": code,
        "actual": round(actual, 4),
        "operator": operator,
        "threshold": round(threshold, 4),
        "passed": passed,
    }
