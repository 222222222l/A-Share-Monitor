"""Risk-reward planning for C3 right-side candidates."""

from __future__ import annotations

from dataclasses import dataclass

from a_share_monitor.config import get_float
from a_share_monitor.config import get_int
from a_share_monitor.config import load_strategy_config
from a_share_monitor.data import DailyBar
from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.data import FundamentalRiskEvent
from a_share_monitor.data import OwnershipFlowSignal
from a_share_monitor.strategy.stock_screen import StockScreenReport
from a_share_monitor.strategy.stock_screen import StockScreenSignal
from a_share_monitor.strategy.stock_screen import evaluate_latest_fixture_stock_screen
from a_share_monitor.strategy.technical_indicators import DivergenceEvidence
from a_share_monitor.strategy.technical_indicators import TechnicalAnalysisReport
from a_share_monitor.strategy.technical_indicators import TechnicalIndicatorSnapshot
from a_share_monitor.strategy.technical_indicators import evaluate_technical_indicators


@dataclass(frozen=True)
class RiskPlanConfig:
    min_risk_reward: float = 1.5
    account_risk_fraction: float = 0.01
    max_position_fraction: float = 0.2
    time_exit_days: int = 10
    target_2_lookback_days: int = 60
    target_2_risk_multiple: float = 2.4
    target_2_extension_multiple: float = 0.6
    thin_liquidity_amount: float = 20_000_000


def default_risk_plan_config() -> RiskPlanConfig:
    """Build the C4 risk plan config from the package strategy config."""
    strategy_config = load_strategy_config()
    return RiskPlanConfig(
        min_risk_reward=get_float(
            strategy_config, "risk_preference.min_risk_reward", 1.5
        ),
        account_risk_fraction=get_float(
            strategy_config, "risk_preference.account_risk_fraction", 0.01
        ),
        max_position_fraction=get_float(
            strategy_config, "risk_preference.max_position_fraction", 0.2
        ),
        time_exit_days=get_int(strategy_config, "risk_preference.time_exit_days", 10),
        target_2_lookback_days=get_int(
            strategy_config, "risk_preference.target_2_lookback_days", 60
        ),
        target_2_risk_multiple=get_float(
            strategy_config, "risk_preference.target_2_risk_multiple", 2.4
        ),
        target_2_extension_multiple=get_float(
            strategy_config, "risk_preference.target_2_extension_multiple", 0.6
        ),
        thin_liquidity_amount=get_float(
            strategy_config, "risk_preference.thin_liquidity_amount", 20_000_000
        ),
    )


@dataclass(frozen=True)
class RiskManagedRecommendation:
    symbol: str
    name: str
    decision: str
    trade_date: str
    next_action_date: str
    setup_type: str
    entry_zone: tuple[float, float]
    stop_loss: float
    technical_exit_price: float
    technical_exit_reason: str
    fundamental_exit_trigger: str
    time_exit_rule: str
    target_1: float
    target_2: float
    risk_reward: float
    position_size: float
    holding_period: str
    invalidation: str
    market_regime: str
    sector_reason: str
    technical_reason: str
    technical_indicators: dict[str, float]
    divergence: dict[str, float | str]
    fundamental_risk: tuple[str, ...]
    liquidity_risk: str
    ownership_flow_risk: str
    data_quality: str
    confidence: float
    audit_notes: tuple[str, ...]


@dataclass(frozen=True)
class RiskPlanReport:
    trade_date: str
    min_risk_reward: float
    recommendations: tuple[RiskManagedRecommendation, ...]
    rejected_symbols: tuple[str, ...]
    planned_symbols: tuple[str, ...]
    watchlist_symbols: tuple[str, ...]


def evaluate_latest_fixture_risk_plan(
    adapter: FixtureMarketDataAdapter | None = None,
    config: RiskPlanConfig | None = None,
) -> RiskPlanReport:
    adapter = adapter or FixtureMarketDataAdapter()
    config = config or default_risk_plan_config()
    stock_report = evaluate_latest_fixture_stock_screen(adapter)
    candidate_symbols = stock_report.candidate_symbols
    daily_bars = adapter.load_symbol_daily_bars(
        candidate_symbols,
        end_date=stock_report.trade_date,
        lookback=80,
    )
    technical_report = evaluate_technical_indicators(
        trade_date=stock_report.trade_date,
        symbols=candidate_symbols,
        daily_bars=daily_bars,
    )
    ownership_flows = adapter.load_ownership_flow_signals(candidate_symbols)
    fundamental_events = adapter.load_fundamental_risk_events(candidate_symbols)
    return evaluate_risk_plan(
        stock_report=stock_report,
        technical_report=technical_report,
        daily_bars=daily_bars,
        ownership_flows=ownership_flows,
        fundamental_events=fundamental_events,
        config=config,
    )


def evaluate_risk_plan(
    *,
    stock_report: StockScreenReport,
    technical_report: TechnicalAnalysisReport,
    daily_bars: tuple[DailyBar, ...],
    ownership_flows: tuple[OwnershipFlowSignal, ...],
    fundamental_events: tuple[FundamentalRiskEvent, ...],
    config: RiskPlanConfig,
) -> RiskPlanReport:
    signal_by_symbol = {
        item.symbol: item
        for item in stock_report.signals
        if item.signal_status == "candidate"
    }
    rows_by_symbol = _group_bars(daily_bars)
    snapshot_by_symbol = {item.symbol: item for item in technical_report.snapshots}
    divergence_by_symbol = {item.symbol: item for item in technical_report.divergences}
    ownership_by_symbol = {item.symbol: item for item in ownership_flows}
    events_by_symbol = _group_fundamental_events(fundamental_events)

    recommendations = []
    rejected_symbols = []
    for symbol in stock_report.candidate_symbols:
        signal = signal_by_symbol.get(symbol)
        rows = rows_by_symbol.get(symbol, ())
        snapshot = snapshot_by_symbol.get(symbol)
        if signal is None or snapshot is None or len(rows) < 60:
            rejected_symbols.append(symbol)
            continue
        recommendation = _build_recommendation(
            signal=signal,
            market_regime=stock_report.market_state,
            rows=rows,
            snapshot=snapshot,
            divergence=divergence_by_symbol.get(symbol),
            ownership=ownership_by_symbol.get(symbol),
            events=events_by_symbol.get(symbol, ()),
            config=config,
        )
        if (
            recommendation.decision in {"buy_ready", "buy_watch"}
            and recommendation.risk_reward <= config.min_risk_reward
        ):
            rejected_symbols.append(symbol)
            continue
        recommendations.append(recommendation)

    return RiskPlanReport(
        trade_date=stock_report.trade_date,
        min_risk_reward=config.min_risk_reward,
        recommendations=tuple(recommendations),
        rejected_symbols=tuple(rejected_symbols),
        planned_symbols=tuple(item.symbol for item in recommendations),
        watchlist_symbols=stock_report.watchlist_symbols,
    )


def _build_recommendation(
    *,
    signal: StockScreenSignal,
    market_regime: str,
    rows: tuple[DailyBar, ...],
    snapshot: TechnicalIndicatorSnapshot,
    divergence: DivergenceEvidence | None,
    ownership: OwnershipFlowSignal | None,
    events: tuple[FundamentalRiskEvent, ...],
    config: RiskPlanConfig,
) -> RiskManagedRecommendation:
    latest = rows[-1]
    atr = max(snapshot.atr_14, latest.close * 0.015)
    entry_zone = _entry_zone(latest.close, atr)
    stop_loss = _technical_stop(rows, snapshot, atr, entry_zone[0])
    planned_entry = entry_zone[1]
    risk_per_share = max(planned_entry - stop_loss, latest.close * 0.01)
    target_1 = _target_1(rows, planned_entry, risk_per_share)
    target_2 = _target_2(rows, planned_entry, risk_per_share, target_1, config)
    risk_reward = round((target_1 - planned_entry) / risk_per_share, 4)
    decision = "buy_ready" if risk_reward > config.min_risk_reward else "reject"

    return RiskManagedRecommendation(
        symbol=signal.symbol,
        name=signal.name,
        decision=decision,
        trade_date=signal.trade_date,
        next_action_date=f"next_trading_day_after_{signal.trade_date}",
        setup_type=signal.setup_type,
        entry_zone=entry_zone,
        stop_loss=stop_loss,
        technical_exit_price=stop_loss,
        technical_exit_reason=_technical_exit_reason(signal, snapshot, atr),
        fundamental_exit_trigger=_fundamental_exit_trigger(events),
        time_exit_rule=(
            "review if price fails to reach 1R within 5 trading days; "
            f"exit review after {config.time_exit_days} trading days"
        ),
        target_1=target_1,
        target_2=target_2,
        risk_reward=risk_reward,
        position_size=_position_fraction(planned_entry, risk_per_share, config),
        holding_period="5-15 trading days",
        invalidation=(
            "right-side setup is invalid if price closes below the technical "
            "exit price or sector buy permission is withdrawn"
        ),
        market_regime=market_regime,
        sector_reason=f"sector scope: {signal.sector_id}",
        technical_reason=_technical_reason(signal, snapshot),
        technical_indicators=_technical_indicator_payload(snapshot),
        divergence=_divergence_payload(divergence),
        fundamental_risk=_fundamental_risk_payload(events),
        liquidity_risk=_liquidity_risk(latest, config),
        ownership_flow_risk=_ownership_flow_risk(ownership),
        data_quality="offline synthetic fixture; verify with live data before use",
        confidence=_confidence(signal, snapshot, divergence, ownership, risk_reward),
        audit_notes=(
            "recommendation is a user-review plan, not an automatic order",
            "fundamental risk is surfaced as a final warning, not a screening filter",
        ),
    )


def _entry_zone(close: float, atr: float) -> tuple[float, float]:
    lower = close - (atr * 0.2)
    upper = close + (atr * 0.2)
    return (round(lower, 2), round(upper, 2))


def _technical_stop(
    rows: tuple[DailyBar, ...],
    snapshot: TechnicalIndicatorSnapshot,
    atr: float,
    entry_lower: float,
) -> float:
    latest = rows[-1]
    swing_low = min(item.low for item in rows[-10:])
    ema20_band = snapshot.ema_20 - (atr * 0.35)
    signal_low = latest.low - (atr * 0.1)
    candidates = [swing_low, ema20_band, signal_low]
    valid = [item for item in candidates if item < entry_lower]
    stop = max(valid) if valid else entry_lower - atr
    return round(max(stop, 0.01), 2)


def _target_1(
    rows: tuple[DailyBar, ...], planned_entry: float, risk_per_share: float
) -> float:
    recent_high = max(item.high for item in rows[-20:])
    r_multiple_target = planned_entry + (risk_per_share * 1.6)
    return round(max(recent_high, r_multiple_target), 2)


def _target_2(
    rows: tuple[DailyBar, ...],
    planned_entry: float,
    risk_per_share: float,
    target_1: float,
    config: RiskPlanConfig,
) -> float:
    recent_high = max(item.high for item in rows[-config.target_2_lookback_days :])
    r_multiple_target = planned_entry + (risk_per_share * config.target_2_risk_multiple)
    extension_target = target_1 + (risk_per_share * config.target_2_extension_multiple)
    return round(max(recent_high, r_multiple_target, extension_target), 2)


def _position_fraction(
    planned_entry: float, risk_per_share: float, config: RiskPlanConfig
) -> float:
    risk_fraction = risk_per_share / planned_entry
    if risk_fraction <= 0:
        return 0.0
    position = config.account_risk_fraction / risk_fraction
    return round(min(position, config.max_position_fraction), 4)


def _technical_exit_reason(
    signal: StockScreenSignal, snapshot: TechnicalIndicatorSnapshot, atr: float
) -> str:
    return (
        f"{signal.setup_type} invalidation near EMA20/10-day swing support; "
        f"ATR14={snapshot.atr_14:.2f}, risk band={atr:.2f}"
    )


def _technical_reason(
    signal: StockScreenSignal, snapshot: TechnicalIndicatorSnapshot
) -> str:
    return (
        f"{signal.setup_type} with EMA20={snapshot.ema_20:.2f}, "
        f"EMA60={snapshot.ema_60:.2f}, RSI14={snapshot.rsi_14:.2f}, "
        f"MACD_hist={snapshot.macd_hist:.4f}"
    )


def _technical_indicator_payload(
    snapshot: TechnicalIndicatorSnapshot,
) -> dict[str, float]:
    return {
        "ema_5": snapshot.ema_5,
        "ema_10": snapshot.ema_10,
        "ema_20": snapshot.ema_20,
        "ema_60": snapshot.ema_60,
        "rsi_6": snapshot.rsi_6,
        "rsi_14": snapshot.rsi_14,
        "macd_dif": snapshot.macd_dif,
        "macd_dea": snapshot.macd_dea,
        "macd_hist": snapshot.macd_hist,
        "kdj_k": snapshot.kdj_k,
        "kdj_d": snapshot.kdj_d,
        "kdj_j": snapshot.kdj_j,
        "atr_14": snapshot.atr_14,
        "relative_strength_20d": snapshot.relative_strength_20d,
    }


def _divergence_payload(
    divergence: DivergenceEvidence | None,
) -> dict[str, float | str]:
    if divergence is None:
        return {"divergence": "none", "evidence": "not calculated"}
    return {
        "divergence": divergence.divergence,
        "indicator_name": divergence.indicator_name,
        "price_swing_a": divergence.price_swing_a,
        "price_swing_b": divergence.price_swing_b,
        "indicator_swing_a": divergence.indicator_swing_a,
        "indicator_swing_b": divergence.indicator_swing_b,
        "evidence": divergence.evidence,
    }


def _fundamental_exit_trigger(events: tuple[FundamentalRiskEvent, ...]) -> str:
    if not events:
        return "review new announcements before order; no fixture event found"
    severe = ", ".join(f"{item.event_type}:{item.severity}" for item in events)
    return f"user review required if new or unresolved event remains: {severe}"


def _fundamental_risk_payload(
    events: tuple[FundamentalRiskEvent, ...],
) -> tuple[str, ...]:
    if not events:
        return ("no candidate-specific fixture fundamental risk event",)
    return tuple(
        f"{item.announcement_date} {item.event_type} {item.severity}: {item.summary}"
        for item in events
    )


def _liquidity_risk(latest: DailyBar, config: RiskPlanConfig) -> str:
    if latest.amount < config.thin_liquidity_amount:
        return "thin liquidity; reduce size or reject"
    if latest.close >= latest.limit_up * 0.995:
        return "near limit-up; avoid chasing if no executable entry"
    if latest.close <= latest.limit_down * 1.005:
        return "near limit-down; liquidity exit risk"
    return "adequate fixture liquidity"


def _ownership_flow_risk(ownership: OwnershipFlowSignal | None) -> str:
    if ownership is None:
        return "ownership flow unavailable"
    if ownership.counterparty_signal == "retail_institution_exit_risk":
        return "retail crowding with institutional exit risk"
    if (
        ownership.counterparty_signal
        == "retail_exit_institution_accumulation_opportunity"
    ):
        return "retail exit with institutional accumulation support"
    return f"{ownership.counterparty_signal}; require continued flow confirmation"


def _confidence(
    signal: StockScreenSignal,
    snapshot: TechnicalIndicatorSnapshot,
    divergence: DivergenceEvidence | None,
    ownership: OwnershipFlowSignal | None,
    risk_reward: float,
) -> float:
    score = 0.55
    if signal.setup_type == "trend_pullback":
        score += 0.08
    if snapshot.relative_strength_20d > 0:
        score += 0.05
    if snapshot.macd_hist > 0:
        score += 0.04
    if risk_reward > 1.8:
        score += 0.04
    if divergence and divergence.divergence == "bearish_divergence":
        score -= 0.12
    if ownership and ownership.counterparty_signal == "retail_institution_exit_risk":
        score -= 0.15
    return round(max(0.0, min(score, 0.9)), 4)


def _group_bars(rows: tuple[DailyBar, ...]) -> dict[str, tuple[DailyBar, ...]]:
    grouped: dict[str, list[DailyBar]] = {}
    for row in rows:
        grouped.setdefault(row.symbol, []).append(row)
    return {
        symbol: tuple(sorted(items, key=lambda item: item.trade_date))
        for symbol, items in grouped.items()
    }


def _group_fundamental_events(
    events: tuple[FundamentalRiskEvent, ...],
) -> dict[str, tuple[FundamentalRiskEvent, ...]]:
    grouped: dict[str, list[FundamentalRiskEvent]] = {}
    for event in events:
        grouped.setdefault(event.symbol, []).append(event)
    return {symbol: tuple(items) for symbol, items in grouped.items()}
