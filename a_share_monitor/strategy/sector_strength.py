"""Sector strength scoring for staged A-share screening."""

from __future__ import annotations

from dataclasses import dataclass

from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.data import SectorBar
from a_share_monitor.strategy.market_state import MarketStateSignal
from a_share_monitor.strategy.market_state import evaluate_market_state


@dataclass(frozen=True)
class SectorStrengthScore:
    sector_id: str
    sector_name: str
    trade_date: str
    relative_strength_5d: float
    relative_strength_20d: float
    amount_ratio_20d: float
    daily_pct_change: float
    rotation_bonus: float
    score: float
    rank: int
    eligible: bool
    reason: str


@dataclass(frozen=True)
class SectorStrengthReport:
    trade_date: str
    market_state: str
    buy_permission: str
    scores: tuple[SectorStrengthScore, ...]
    eligible_sector_ids: tuple[str, ...]


def evaluate_latest_fixture_sector_strength(
    adapter: FixtureMarketDataAdapter | None = None,
) -> SectorStrengthReport:
    adapter = adapter or FixtureMarketDataAdapter()
    context = adapter.load_market_context()
    market_signal = evaluate_market_state(context)
    history = adapter.load_sector_history(end_date=context.trade_date, lookback=20)
    return evaluate_sector_strength(market_signal, history)


def evaluate_sector_strength(
    market_signal: MarketStateSignal,
    sector_history: tuple[SectorBar, ...],
) -> SectorStrengthReport:
    if market_signal.buy_permission == "blocked":
        return SectorStrengthReport(
            trade_date=market_signal.trade_date,
            market_state=market_signal.market_state,
            buy_permission=market_signal.buy_permission,
            scores=(),
            eligible_sector_ids=(),
        )

    grouped = _group_by_sector(sector_history)
    raw_scores = []
    returns_5d = {
        sector_id: _window_return(rows, 5) for sector_id, rows in grouped.items()
    }
    returns_20d = {
        sector_id: _window_return(rows, 20) for sector_id, rows in grouped.items()
    }
    median_5d = _median(tuple(returns_5d.values()))
    median_20d = _median(tuple(returns_20d.values()))

    for sector_id, rows in grouped.items():
        latest = rows[-1]
        relative_5d = returns_5d[sector_id] - median_5d
        relative_20d = returns_20d[sector_id] - median_20d
        amount_ratio = _amount_ratio(rows, 20)
        rotation_bonus = _rotation_bonus(market_signal, sector_id)
        score = (
            relative_5d * 40
            + relative_20d * 25
            + min(amount_ratio, 2.0) * 15
            + latest.pct_change * 20
            + rotation_bonus
        )
        eligible = _eligible(market_signal, sector_id, score, amount_ratio, latest)
        raw_scores.append(
            SectorStrengthScore(
                sector_id=sector_id,
                sector_name=latest.sector_name,
                trade_date=latest.trade_date,
                relative_strength_5d=round(relative_5d, 6),
                relative_strength_20d=round(relative_20d, 6),
                amount_ratio_20d=round(amount_ratio, 6),
                daily_pct_change=round(latest.pct_change, 6),
                rotation_bonus=round(rotation_bonus, 6),
                score=round(score, 6),
                rank=0,
                eligible=eligible,
                reason=_reason(market_signal, sector_id, eligible),
            )
        )

    ranked = tuple(
        _with_rank(item, rank)
        for rank, item in enumerate(
            sorted(raw_scores, key=lambda item: item.score, reverse=True), start=1
        )
    )
    return SectorStrengthReport(
        trade_date=market_signal.trade_date,
        market_state=market_signal.market_state,
        buy_permission=market_signal.buy_permission,
        scores=ranked,
        eligible_sector_ids=tuple(item.sector_id for item in ranked if item.eligible),
    )


def _group_by_sector(
    sector_history: tuple[SectorBar, ...]
) -> dict[str, tuple[SectorBar, ...]]:
    grouped: dict[str, list[SectorBar]] = {}
    for row in sector_history:
        grouped.setdefault(row.sector_id, []).append(row)
    return {
        sector_id: tuple(sorted(rows, key=lambda item: item.trade_date))
        for sector_id, rows in grouped.items()
        if rows
    }


def _window_return(rows: tuple[SectorBar, ...], window: int) -> float:
    if len(rows) < 2:
        return 0.0
    start_index = max(0, len(rows) - window)
    start = rows[start_index].close
    end = rows[-1].close
    if start == 0:
        return 0.0
    return (end / start) - 1


def _amount_ratio(rows: tuple[SectorBar, ...], window: int) -> float:
    if not rows:
        return 0.0
    latest = rows[-1].amount
    sample = rows[-window:]
    average = sum(row.amount for row in sample) / len(sample)
    if average == 0:
        return 0.0
    return latest / average


def _median(values: tuple[float, ...]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def _rotation_bonus(signal: MarketStateSignal, sector_id: str) -> float:
    if sector_id in signal.active_sector_ids:
        return 0.4
    if sector_id in signal.weak_sector_ids:
        return -0.25
    return 0.0


def _eligible(
    signal: MarketStateSignal,
    sector_id: str,
    score: float,
    amount_ratio: float,
    latest: SectorBar,
) -> bool:
    if signal.buy_permission == "rotation_only":
        return sector_id in signal.active_sector_ids and score > 0
    if signal.buy_permission == "rebound_watch":
        return sector_id in signal.active_sector_ids and amount_ratio >= 0.95
    if signal.buy_permission == "selective":
        return score > 0 and latest.pct_change >= 0
    if signal.buy_permission == "normal":
        return score > -0.1
    return False


def _reason(signal: MarketStateSignal, sector_id: str, eligible: bool) -> str:
    if not eligible:
        return "not_in_allowed_rotation_scope"
    if sector_id in signal.active_sector_ids:
        return "active_sector_confirmed_by_market_state"
    return "sector_strength_passed"


def _with_rank(item: SectorStrengthScore, rank: int) -> SectorStrengthScore:
    return SectorStrengthScore(
        sector_id=item.sector_id,
        sector_name=item.sector_name,
        trade_date=item.trade_date,
        relative_strength_5d=item.relative_strength_5d,
        relative_strength_20d=item.relative_strength_20d,
        amount_ratio_20d=item.amount_ratio_20d,
        daily_pct_change=item.daily_pct_change,
        rotation_bonus=item.rotation_bonus,
        score=item.score,
        rank=rank,
        eligible=item.eligible,
        reason=item.reason,
    )
