"""Small event-driven simulator for long-only recommendation plans."""

from __future__ import annotations

from dataclasses import dataclass

from a_share_monitor.data import DailyBar
from a_share_monitor.strategy import RiskManagedRecommendation


@dataclass(frozen=True)
class BacktestConfig:
    commission_bps: float = 3.0
    slippage_bps: float = 5.0


@dataclass(frozen=True)
class BacktestEvent:
    event_type: str
    trade_date: str
    symbol: str
    price: float
    quantity_fraction: float
    reason: str


@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    status: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    gross_return: float
    net_return: float
    max_adverse_excursion: float
    events: tuple[BacktestEvent, ...]


def simulate_long_plan(
    recommendation: RiskManagedRecommendation,
    future_bars: tuple[DailyBar, ...],
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Simulate a buy-ready long plan with T+1 and limit-price constraints."""
    config = config or BacktestConfig()
    events = [
        BacktestEvent(
            event_type="signal_generated",
            trade_date=recommendation.trade_date,
            symbol=recommendation.symbol,
            price=recommendation.entry_zone[1],
            quantity_fraction=recommendation.position_size,
            reason="buy-ready plan created by deterministic strategy",
        )
    ]
    relevant = tuple(
        row
        for row in sorted(future_bars, key=lambda item: item.trade_date)
        if row.symbol == recommendation.symbol
        and row.trade_date > recommendation.trade_date
    )
    if not relevant:
        return _pending(recommendation, tuple(events), "no future bars available")

    entry_bar = relevant[0]
    fill_price = _fill_price(recommendation, entry_bar, config)
    if fill_price is None:
        events.append(
            BacktestEvent(
                event_type="order_unfilled",
                trade_date=entry_bar.trade_date,
                symbol=recommendation.symbol,
                price=0.0,
                quantity_fraction=0.0,
                reason="entry zone not traded or limit-up liquidity blocked",
            )
        )
        return _pending(recommendation, tuple(events), "entry unfilled")

    events.append(
        BacktestEvent(
            event_type="order_filled",
            trade_date=entry_bar.trade_date,
            symbol=recommendation.symbol,
            price=fill_price,
            quantity_fraction=recommendation.position_size,
            reason="next-day entry filled with slippage",
        )
    )
    max_adverse = min(0.0, (entry_bar.low / fill_price) - 1)
    if entry_bar.low <= recommendation.technical_exit_price:
        events.append(
            BacktestEvent(
                event_type="stop_blocked_by_t1",
                trade_date=entry_bar.trade_date,
                symbol=recommendation.symbol,
                price=recommendation.technical_exit_price,
                quantity_fraction=recommendation.position_size,
                reason="T+1 prevents same-day exit after entry",
            )
        )

    for bar in relevant[1:]:
        max_adverse = min(max_adverse, (bar.low / fill_price) - 1)
        if bar.is_suspended:
            events.append(
                BacktestEvent(
                    event_type="exit_blocked",
                    trade_date=bar.trade_date,
                    symbol=recommendation.symbol,
                    price=0.0,
                    quantity_fraction=recommendation.position_size,
                    reason="suspended; cannot exit",
                )
            )
            continue
        if bar.low <= recommendation.technical_exit_price:
            return _closed(
                recommendation,
                tuple(events),
                fill_price,
                _sell_price(recommendation.technical_exit_price, config),
                bar.trade_date,
                max_adverse,
                "stop_loss",
                config,
            )
        if bar.high >= recommendation.target_1:
            return _closed(
                recommendation,
                tuple(events),
                fill_price,
                _sell_price(recommendation.target_1, config),
                bar.trade_date,
                max_adverse,
                "target_1",
                config,
            )

    last = relevant[-1]
    return _closed(
        recommendation,
        tuple(events),
        fill_price,
        _sell_price(last.close, config),
        last.trade_date,
        max_adverse,
        "mark_to_market",
        config,
    )


def _fill_price(
    recommendation: RiskManagedRecommendation,
    bar: DailyBar,
    config: BacktestConfig,
) -> float | None:
    lower, upper = recommendation.entry_zone
    if bar.open >= bar.limit_up * 0.995:
        return None
    if bar.high < lower or bar.low > upper:
        return None
    raw = min(max(bar.open, lower), upper)
    return round(raw * (1 + config.slippage_bps / 10_000), 4)


def _sell_price(price: float, config: BacktestConfig) -> float:
    return round(price * (1 - config.slippage_bps / 10_000), 4)


def _closed(
    recommendation: RiskManagedRecommendation,
    events: tuple[BacktestEvent, ...],
    entry_price: float,
    exit_price: float,
    exit_date: str,
    max_adverse: float,
    reason: str,
    config: BacktestConfig,
) -> BacktestResult:
    cost = (config.commission_bps * 2) / 10_000
    gross = (exit_price / entry_price) - 1
    net = gross - cost
    events = events + (
        BacktestEvent(
            event_type=reason,
            trade_date=exit_date,
            symbol=recommendation.symbol,
            price=exit_price,
            quantity_fraction=recommendation.position_size,
            reason=reason,
        ),
    )
    return BacktestResult(
        symbol=recommendation.symbol,
        status="closed",
        entry_date=events[1].trade_date,
        exit_date=exit_date,
        entry_price=entry_price,
        exit_price=exit_price,
        gross_return=round(gross, 6),
        net_return=round(net, 6),
        max_adverse_excursion=round(max_adverse, 6),
        events=events,
    )


def _pending(
    recommendation: RiskManagedRecommendation,
    events: tuple[BacktestEvent, ...],
    reason: str,
) -> BacktestResult:
    return BacktestResult(
        symbol=recommendation.symbol,
        status=reason,
        entry_date="",
        exit_date="",
        entry_price=0.0,
        exit_price=0.0,
        gross_return=0.0,
        net_return=0.0,
        max_adverse_excursion=0.0,
        events=events,
    )
