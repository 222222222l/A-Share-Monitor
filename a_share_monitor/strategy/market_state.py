"""A-share market-state gate for staged screening."""

from __future__ import annotations

from dataclasses import dataclass

from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.data import MarketContext
from a_share_monitor.data import SectorBar


@dataclass(frozen=True)
class MarketStateSignal:
    trade_date: str
    market_state: str
    buy_permission: str
    liquidity_state: str
    breadth_state: str
    rotation_state: str
    policy_support_signal: str
    active_sector_ids: tuple[str, ...]
    weak_sector_ids: tuple[str, ...]
    evidence: dict[str, float | int | str | tuple[str, ...]]


def evaluate_latest_fixture_market_state(
    adapter: FixtureMarketDataAdapter | None = None,
) -> MarketStateSignal:
    """Evaluate the latest fixture market state without loading stock-level data."""
    adapter = adapter or FixtureMarketDataAdapter()
    return evaluate_market_state(adapter.load_market_context())


def evaluate_market_state(context: MarketContext) -> MarketStateSignal:
    breadth = context.market_breadth
    total_count = breadth.advancing_count + breadth.declining_count
    advancing_ratio = _safe_ratio(breadth.advancing_count, total_count)
    limit_down_pressure = _safe_ratio(breadth.limit_down_count, total_count)
    limit_up_strength = _safe_ratio(breadth.limit_up_count, total_count)
    new_high_low_ratio = _safe_ratio(
        breadth.new_high_20d_count + 1,
        breadth.new_low_20d_count + 1,
    )
    bse_breadth_ratio = _safe_ratio(
        breadth.bse_advancing_count or 0,
        (breadth.bse_advancing_count or 0) + (breadth.bse_declining_count or 0),
    )
    active_sectors = tuple(
        sector.sector_id for sector in context.sector_bars if _is_active_sector(sector)
    )
    weak_sectors = tuple(
        sector.sector_id for sector in context.sector_bars if sector.pct_change < -0.01
    )
    positive_sector_count = sum(
        1 for sector in context.sector_bars if sector.pct_change > 0
    )
    sector_diffusion_score = _safe_ratio(
        positive_sector_count, len(context.sector_bars)
    )

    liquidity_state = _liquidity_state(
        advancing_ratio=advancing_ratio,
        limit_down_pressure=limit_down_pressure,
        total_amount=breadth.total_amount,
    )
    breadth_state = _breadth_state(advancing_ratio, new_high_low_ratio)
    rotation_state = _rotation_state(
        active_sectors, weak_sectors, sector_diffusion_score
    )
    policy_support_signal = _policy_support_signal(
        advancing_ratio=advancing_ratio,
        bse_breadth_ratio=bse_breadth_ratio,
        index_count=len(context.index_bars),
    )
    market_state, buy_permission = _state_and_permission(
        liquidity_state=liquidity_state,
        breadth_state=breadth_state,
        rotation_state=rotation_state,
        policy_support_signal=policy_support_signal,
        active_sector_count=len(active_sectors),
        sector_diffusion_score=sector_diffusion_score,
        limit_up_strength=limit_up_strength,
    )

    return MarketStateSignal(
        trade_date=context.trade_date,
        market_state=market_state,
        buy_permission=buy_permission,
        liquidity_state=liquidity_state,
        breadth_state=breadth_state,
        rotation_state=rotation_state,
        policy_support_signal=policy_support_signal,
        active_sector_ids=active_sectors,
        weak_sector_ids=weak_sectors,
        evidence={
            "advancing_ratio": round(advancing_ratio, 4),
            "limit_down_pressure": round(limit_down_pressure, 4),
            "limit_up_strength": round(limit_up_strength, 4),
            "new_high_low_ratio": round(new_high_low_ratio, 4),
            "bse_breadth_ratio": round(bse_breadth_ratio, 4),
            "sector_diffusion_score": round(sector_diffusion_score, 4),
            "active_sector_count": len(active_sectors),
            "active_sector_ids": active_sectors,
            "weak_sector_ids": weak_sectors,
            "total_amount": round(breadth.total_amount, 2),
        },
    )


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _is_active_sector(sector: SectorBar) -> bool:
    return sector.pct_change > 0 and sector.amount > 0


def _liquidity_state(
    *, advancing_ratio: float, limit_down_pressure: float, total_amount: float
) -> str:
    if limit_down_pressure >= 0.03 or advancing_ratio < 0.25:
        return "stress"
    if total_amount <= 0 or advancing_ratio < 0.40:
        return "thin"
    if advancing_ratio > 0.58:
        return "expanding"
    return "adequate"


def _breadth_state(advancing_ratio: float, new_high_low_ratio: float) -> str:
    if advancing_ratio >= 0.58 and new_high_low_ratio >= 1.2:
        return "broad_improvement"
    if advancing_ratio < 0.35:
        return "broad_weakness"
    if new_high_low_ratio < 0.8:
        return "under_distribution"
    return "mixed"


def _rotation_state(
    active_sectors: tuple[str, ...],
    weak_sectors: tuple[str, ...],
    sector_diffusion_score: float,
) -> str:
    if active_sectors and sector_diffusion_score < 0.65:
        return "concentrated_rotation"
    if sector_diffusion_score >= 0.65:
        return "broad_sector_diffusion"
    if weak_sectors:
        return "sector_pressure"
    return "no_clear_leadership"


def _policy_support_signal(
    *, advancing_ratio: float, bse_breadth_ratio: float, index_count: int
) -> str:
    if index_count < 2:
        return "unknown"
    if advancing_ratio < 0.42 and bse_breadth_ratio < 0.45:
        return "possible_weight_support_not_confirmed"
    if advancing_ratio < 0.45 and bse_breadth_ratio >= 0.50:
        return "small_cap_risk_appetite_repair"
    return "none"


def _state_and_permission(
    *,
    liquidity_state: str,
    breadth_state: str,
    rotation_state: str,
    policy_support_signal: str,
    active_sector_count: int,
    sector_diffusion_score: float,
    limit_up_strength: float,
) -> tuple[str, str]:
    if liquidity_state == "stress":
        return "liquidity_crisis", "blocked"
    if policy_support_signal.startswith("possible_weight_support"):
        return "policy_support_rebound", "rebound_watch"
    if limit_up_strength > 0.03 and sector_diffusion_score > 0.80:
        return "overheated_chase_risk", "selective"
    if (
        breadth_state == "broad_improvement"
        and rotation_state == "broad_sector_diffusion"
    ):
        return "broad_risk_on", "normal"
    if active_sector_count > 0 and rotation_state == "concentrated_rotation":
        return "rotation_opportunity", "rotation_only"
    if liquidity_state in {"adequate", "expanding"}:
        return "mixed_chop", "selective"
    return "unknown", "selective"
