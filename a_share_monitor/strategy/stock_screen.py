"""Right-side stock screening for staged A-share workflows."""

from __future__ import annotations

from dataclasses import dataclass

from a_share_monitor.data import DailyBar
from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.data import OwnershipFlowSignal
from a_share_monitor.data import Security
from a_share_monitor.strategy.sector_strength import SectorStrengthReport
from a_share_monitor.strategy.sector_strength import (
    evaluate_latest_fixture_sector_strength,
)


@dataclass(frozen=True)
class StockScreenSignal:
    symbol: str
    name: str
    trade_date: str
    sector_id: str
    setup_type: str
    signal_status: str
    right_side_confirmed: bool
    rejection_reason: str
    evidence: dict[str, float | int | str | bool]


@dataclass(frozen=True)
class StockScreenReport:
    trade_date: str
    market_state: str
    buy_permission: str
    eligible_sector_ids: tuple[str, ...]
    signals: tuple[StockScreenSignal, ...]
    candidate_symbols: tuple[str, ...]
    watchlist_symbols: tuple[str, ...]
    rejected_symbols: tuple[str, ...]


def evaluate_latest_fixture_stock_screen(
    adapter: FixtureMarketDataAdapter | None = None,
) -> StockScreenReport:
    adapter = adapter or FixtureMarketDataAdapter()
    sector_report = evaluate_latest_fixture_sector_strength(adapter)
    securities = adapter.load_security_master()
    allowed_securities = _filter_securities_by_sector(
        securities, sector_report.eligible_sector_ids
    )
    symbols = tuple(item.symbol for item in allowed_securities)
    daily_bars = adapter.load_symbol_daily_bars(
        symbols, end_date=sector_report.trade_date, lookback=80
    )
    ownership_flows = adapter.load_ownership_flow_signals(symbols)
    return evaluate_stock_screen(
        sector_report=sector_report,
        securities=allowed_securities,
        daily_bars=daily_bars,
        ownership_flows=ownership_flows,
    )


def evaluate_stock_screen(
    *,
    sector_report: SectorStrengthReport,
    securities: tuple[Security, ...],
    daily_bars: tuple[DailyBar, ...],
    ownership_flows: tuple[OwnershipFlowSignal, ...],
) -> StockScreenReport:
    if not sector_report.eligible_sector_ids:
        return StockScreenReport(
            trade_date=sector_report.trade_date,
            market_state=sector_report.market_state,
            buy_permission=sector_report.buy_permission,
            eligible_sector_ids=sector_report.eligible_sector_ids,
            signals=(),
            candidate_symbols=(),
            watchlist_symbols=(),
            rejected_symbols=(),
        )

    ownership_by_symbol = {item.symbol: item for item in ownership_flows}
    bars_by_symbol = _group_bars(daily_bars)
    signals = tuple(
        _screen_security(
            security=security,
            rows=bars_by_symbol.get(security.symbol, ()),
            ownership=ownership_by_symbol.get(security.symbol),
            trade_date=sector_report.trade_date,
        )
        for security in securities
    )
    return StockScreenReport(
        trade_date=sector_report.trade_date,
        market_state=sector_report.market_state,
        buy_permission=sector_report.buy_permission,
        eligible_sector_ids=sector_report.eligible_sector_ids,
        signals=signals,
        candidate_symbols=tuple(
            item.symbol for item in signals if item.signal_status == "candidate"
        ),
        watchlist_symbols=tuple(
            item.symbol for item in signals if item.signal_status == "watchlist"
        ),
        rejected_symbols=tuple(
            item.symbol for item in signals if item.signal_status == "rejected"
        ),
    )


def _filter_securities_by_sector(
    securities: tuple[Security, ...], eligible_sector_ids: tuple[str, ...]
) -> tuple[Security, ...]:
    eligible = set(eligible_sector_ids)
    return tuple(
        item
        for item in securities
        if item.tradable
        and not item.bse_reference_only
        and not item.risk_flags
        and bool(eligible.intersection(item.sector_tags))
    )


def _screen_security(
    *,
    security: Security,
    rows: tuple[DailyBar, ...],
    ownership: OwnershipFlowSignal | None,
    trade_date: str,
) -> StockScreenSignal:
    if len(rows) < 60:
        return _rejected(security, trade_date, "insufficient_history", rows)

    latest = rows[-1]
    if latest.is_suspended or latest.is_st or latest.is_new_stock:
        return _rejected(security, trade_date, "basic_trading_state_risk", rows)
    if latest.amount < 5_000_000:
        return _rejected(security, trade_date, "insufficient_liquidity", rows)
    if ownership and ownership.counterparty_signal == "retail_institution_exit_risk":
        return _rejected(security, trade_date, "retail_crowding_institution_exit", rows)

    setup_type = _right_side_setup(rows)
    if setup_type == "none":
        return _watchlist(
            security,
            trade_date,
            "technical_signal_not_ready",
            rows,
            ownership,
        )

    return StockScreenSignal(
        symbol=security.symbol,
        name=security.name,
        trade_date=latest.trade_date,
        sector_id=_first_sector(security),
        setup_type=setup_type,
        signal_status="candidate",
        right_side_confirmed=True,
        rejection_reason="",
        evidence=_evidence(rows, ownership),
    )


def _right_side_setup(rows: tuple[DailyBar, ...]) -> str:
    latest = rows[-1]
    previous = rows[:-1]
    ma5 = _moving_average(rows, 5)
    ma10 = _moving_average(rows, 10)
    ma20 = _moving_average(rows, 20)
    ma60 = _moving_average(rows, 60)
    ma20_prev = _moving_average(rows[:-5], 20)
    prev_20_high = max(item.high for item in previous[-20:])
    volume_ratio = _amount_ratio(rows, 20)

    trend_aligned = latest.close > ma20 and ma20 >= ma60 * 0.995
    ma20_rising = ma20 >= ma20_prev
    short_reclaim = latest.close >= ma5 and latest.close >= ma10
    near_ma20 = abs(latest.close / ma20 - 1) <= 0.08

    if trend_aligned and ma20_rising and short_reclaim and near_ma20:
        return "trend_pullback"
    if (
        latest.close >= prev_20_high * 0.995
        and volume_ratio >= 0.95
        and latest.close > ma20
    ):
        return "platform_breakout"
    return "none"


def _rejected(
    security: Security, trade_date: str, reason: str, rows: tuple[DailyBar, ...]
) -> StockScreenSignal:
    return StockScreenSignal(
        symbol=security.symbol,
        name=security.name,
        trade_date=rows[-1].trade_date if rows else trade_date,
        sector_id=_first_sector(security),
        setup_type="none",
        signal_status="rejected",
        right_side_confirmed=False,
        rejection_reason=reason,
        evidence=_evidence(rows, None),
    )


def _watchlist(
    security: Security,
    trade_date: str,
    reason: str,
    rows: tuple[DailyBar, ...],
    ownership: OwnershipFlowSignal | None,
) -> StockScreenSignal:
    return StockScreenSignal(
        symbol=security.symbol,
        name=security.name,
        trade_date=rows[-1].trade_date if rows else trade_date,
        sector_id=_first_sector(security),
        setup_type="none",
        signal_status="watchlist",
        right_side_confirmed=False,
        rejection_reason=reason,
        evidence=_evidence(rows, ownership),
    )


def _group_bars(rows: tuple[DailyBar, ...]) -> dict[str, tuple[DailyBar, ...]]:
    grouped: dict[str, list[DailyBar]] = {}
    for row in rows:
        grouped.setdefault(row.symbol, []).append(row)
    return {
        symbol: tuple(sorted(items, key=lambda item: item.trade_date))
        for symbol, items in grouped.items()
    }


def _moving_average(rows: tuple[DailyBar, ...], window: int) -> float:
    sample = rows[-window:]
    if not sample:
        return 0.0
    return sum(item.close for item in sample) / len(sample)


def _amount_ratio(rows: tuple[DailyBar, ...], window: int) -> float:
    sample = rows[-window:]
    if not sample:
        return 0.0
    average = sum(item.amount for item in sample) / len(sample)
    if average == 0:
        return 0.0
    return rows[-1].amount / average


def _first_sector(security: Security) -> str:
    return security.sector_tags[0] if security.sector_tags else ""


def _evidence(
    rows: tuple[DailyBar, ...], ownership: OwnershipFlowSignal | None
) -> dict[str, float | int | str | bool]:
    if not rows:
        return {}
    latest = rows[-1]
    evidence: dict[str, float | int | str | bool] = {
        "close": round(latest.close, 4),
        "amount": round(latest.amount, 2),
        "ma5": round(_moving_average(rows, 5), 4),
        "ma10": round(_moving_average(rows, 10), 4),
        "ma20": round(_moving_average(rows, 20), 4),
        "ma60": round(_moving_average(rows, 60), 4),
        "amount_ratio_20d": round(_amount_ratio(rows, 20), 4),
        "right_side_only": True,
    }
    if ownership is not None:
        evidence["counterparty_signal"] = ownership.counterparty_signal
        evidence["retail_crowding_score"] = round(ownership.retail_crowding_score, 4)
        evidence["institutional_accumulation_score"] = round(
            ownership.institutional_accumulation_score, 4
        )
    return evidence
