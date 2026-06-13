"""Technical indicator calculations for C3 candidate/watchlist symbols."""

from __future__ import annotations

from dataclasses import dataclass

from a_share_monitor.data import DailyBar
from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.strategy.stock_screen import evaluate_latest_fixture_stock_screen


@dataclass(frozen=True)
class TechnicalIndicatorSnapshot:
    symbol: str
    trade_date: str
    ema_5: float
    ema_10: float
    ema_20: float
    ema_60: float
    ema_12: float
    ema_26: float
    rsi_6: float
    rsi_14: float
    macd_dif: float
    macd_dea: float
    macd_hist: float
    kdj_k: float
    kdj_d: float
    kdj_j: float
    atr_14: float
    relative_strength_20d: float


@dataclass(frozen=True)
class DivergenceEvidence:
    symbol: str
    trade_date: str
    divergence: str
    indicator_name: str
    price_swing_a: float
    price_swing_b: float
    indicator_swing_a: float
    indicator_swing_b: float
    evidence: str


@dataclass(frozen=True)
class TechnicalAnalysisReport:
    trade_date: str
    symbols: tuple[str, ...]
    snapshots: tuple[TechnicalIndicatorSnapshot, ...]
    divergences: tuple[DivergenceEvidence, ...]
    scoped_to_c3_outputs: bool


def evaluate_latest_fixture_technical_indicators(
    adapter: FixtureMarketDataAdapter | None = None,
) -> TechnicalAnalysisReport:
    adapter = adapter or FixtureMarketDataAdapter()
    stock_report = evaluate_latest_fixture_stock_screen(adapter)
    symbols = tuple(
        dict.fromkeys(stock_report.candidate_symbols + stock_report.watchlist_symbols)
    )
    daily_bars = adapter.load_symbol_daily_bars(
        symbols, end_date=stock_report.trade_date, lookback=80
    )
    return evaluate_technical_indicators(
        trade_date=stock_report.trade_date,
        symbols=symbols,
        daily_bars=daily_bars,
    )


def evaluate_technical_indicators(
    *, trade_date: str, symbols: tuple[str, ...], daily_bars: tuple[DailyBar, ...]
) -> TechnicalAnalysisReport:
    grouped = _group_bars(daily_bars)
    snapshots = []
    divergences = []
    benchmark_return = _benchmark_return(grouped, symbols, 20)
    for symbol in symbols:
        rows = grouped.get(symbol, ())
        if len(rows) < 60:
            continue
        snapshot = _snapshot(symbol, rows, benchmark_return)
        snapshots.append(snapshot)
        divergences.append(_divergence(symbol, rows, snapshot))
    return TechnicalAnalysisReport(
        trade_date=trade_date,
        symbols=symbols,
        snapshots=tuple(snapshots),
        divergences=tuple(divergences),
        scoped_to_c3_outputs=True,
    )


def _snapshot(
    symbol: str, rows: tuple[DailyBar, ...], benchmark_return: float
) -> TechnicalIndicatorSnapshot:
    closes = [item.close for item in rows]
    highs = [item.high for item in rows]
    lows = [item.low for item in rows]
    ema12_series = _ema_series(closes, 12)
    ema26_series = _ema_series(closes, 26)
    dif_series = [fast - slow for fast, slow in zip(ema12_series, ema26_series)]
    dea_series = _ema_series(dif_series, 9)
    k_values, d_values, j_values = _kdj(rows)
    return_20d = _window_return(rows, 20)
    return TechnicalIndicatorSnapshot(
        symbol=symbol,
        trade_date=rows[-1].trade_date,
        ema_5=round(_ema(closes, 5), 6),
        ema_10=round(_ema(closes, 10), 6),
        ema_20=round(_ema(closes, 20), 6),
        ema_60=round(_ema(closes, 60), 6),
        ema_12=round(ema12_series[-1], 6),
        ema_26=round(ema26_series[-1], 6),
        rsi_6=round(_rsi(closes, 6), 6),
        rsi_14=round(_rsi(closes, 14), 6),
        macd_dif=round(dif_series[-1], 6),
        macd_dea=round(dea_series[-1], 6),
        macd_hist=round((dif_series[-1] - dea_series[-1]) * 2, 6),
        kdj_k=round(k_values[-1], 6),
        kdj_d=round(d_values[-1], 6),
        kdj_j=round(j_values[-1], 6),
        atr_14=round(_atr(highs, lows, closes, 14), 6),
        relative_strength_20d=round(return_20d - benchmark_return, 6),
    )


def _divergence(
    symbol: str, rows: tuple[DailyBar, ...], snapshot: TechnicalIndicatorSnapshot
) -> DivergenceEvidence:
    if len(rows) < 30:
        return _no_divergence(symbol, rows[-1].trade_date)
    first_window = rows[-30:-15]
    second_window = rows[-15:]
    first_high = max(item.high for item in first_window)
    second_high = max(item.high for item in second_window)
    first_low = min(item.low for item in first_window)
    second_low = min(item.low for item in second_window)
    rsi_series = _rolling_rsi([item.close for item in rows], 14)
    first_rsi = max(rsi_series[-30:-15])
    second_rsi = max(rsi_series[-15:])
    first_rsi_low = min(rsi_series[-30:-15])
    second_rsi_low = min(rsi_series[-15:])
    if second_high > first_high and second_rsi < first_rsi:
        return DivergenceEvidence(
            symbol=symbol,
            trade_date=rows[-1].trade_date,
            divergence="bearish_divergence",
            indicator_name="rsi_14",
            price_swing_a=round(first_high, 6),
            price_swing_b=round(second_high, 6),
            indicator_swing_a=round(first_rsi, 6),
            indicator_swing_b=round(second_rsi, 6),
            evidence="price higher high with RSI lower high",
        )
    if second_low < first_low and second_rsi_low > first_rsi_low:
        return DivergenceEvidence(
            symbol=symbol,
            trade_date=rows[-1].trade_date,
            divergence="bullish_divergence",
            indicator_name="rsi_14",
            price_swing_a=round(first_low, 6),
            price_swing_b=round(second_low, 6),
            indicator_swing_a=round(first_rsi_low, 6),
            indicator_swing_b=round(second_rsi_low, 6),
            evidence="price lower low with RSI higher low; observation only",
        )
    return _no_divergence(symbol, rows[-1].trade_date, snapshot.rsi_14)


def _no_divergence(
    symbol: str, trade_date: str, indicator_value: float = 0.0
) -> DivergenceEvidence:
    return DivergenceEvidence(
        symbol=symbol,
        trade_date=trade_date,
        divergence="none",
        indicator_name="rsi_14",
        price_swing_a=0.0,
        price_swing_b=0.0,
        indicator_swing_a=indicator_value,
        indicator_swing_b=indicator_value,
        evidence="no two-window RSI divergence detected",
    )


def _group_bars(rows: tuple[DailyBar, ...]) -> dict[str, tuple[DailyBar, ...]]:
    grouped: dict[str, list[DailyBar]] = {}
    for row in rows:
        grouped.setdefault(row.symbol, []).append(row)
    return {
        symbol: tuple(sorted(items, key=lambda item: item.trade_date))
        for symbol, items in grouped.items()
    }


def _ema(values: list[float], window: int) -> float:
    return _ema_series(values, window)[-1]


def _ema_series(values: list[float], window: int) -> list[float]:
    if not values:
        return [0.0]
    alpha = 2 / (window + 1)
    series = [values[0]]
    for value in values[1:]:
        series.append(value * alpha + series[-1] * (1 - alpha))
    return series


def _rsi(closes: list[float], window: int) -> float:
    return _rolling_rsi(closes, window)[-1]


def _rolling_rsi(closes: list[float], window: int) -> list[float]:
    if len(closes) < 2:
        return [50.0]
    values = []
    for index in range(len(closes)):
        if index == 0:
            values.append(50.0)
            continue
        start = max(1, index - window + 1)
        gains = []
        losses = []
        for cursor in range(start, index + 1):
            change = closes[cursor] - closes[cursor - 1]
            if change >= 0:
                gains.append(change)
            else:
                losses.append(abs(change))
        average_gain = sum(gains) / window if gains else 0.0
        average_loss = sum(losses) / window if losses else 0.0
        if average_loss == 0:
            values.append(100.0 if average_gain > 0 else 50.0)
        else:
            rs_value = average_gain / average_loss
            values.append(100 - (100 / (1 + rs_value)))
    return values


def _kdj(rows: tuple[DailyBar, ...]) -> tuple[list[float], list[float], list[float]]:
    k_values = []
    d_values = []
    j_values = []
    k = 50.0
    d = 50.0
    for index, row in enumerate(rows):
        sample = rows[max(0, index - 8) : index + 1]
        low = min(item.low for item in sample)
        high = max(item.high for item in sample)
        rsv = 50.0 if high == low else ((row.close - low) / (high - low)) * 100
        k = (2 / 3) * k + (1 / 3) * rsv
        d = (2 / 3) * d + (1 / 3) * k
        j = (3 * k) - (2 * d)
        k_values.append(k)
        d_values.append(d)
        j_values.append(j)
    return k_values, d_values, j_values


def _atr(
    highs: list[float], lows: list[float], closes: list[float], window: int
) -> float:
    true_ranges = []
    for index, high in enumerate(highs):
        low = lows[index]
        if index == 0:
            true_ranges.append(high - low)
            continue
        previous_close = closes[index - 1]
        true_ranges.append(
            max(high - low, abs(high - previous_close), abs(low - previous_close))
        )
    sample = true_ranges[-window:]
    return sum(sample) / len(sample) if sample else 0.0


def _window_return(rows: tuple[DailyBar, ...], window: int) -> float:
    if len(rows) < 2:
        return 0.0
    start_index = max(0, len(rows) - window)
    start = rows[start_index].close
    if start == 0:
        return 0.0
    return (rows[-1].close / start) - 1


def _benchmark_return(
    grouped: dict[str, tuple[DailyBar, ...]], symbols: tuple[str, ...], window: int
) -> float:
    returns = [_window_return(grouped.get(symbol, ()), window) for symbol in symbols]
    returns = [value for value in returns if value != 0]
    if not returns:
        return 0.0
    return sum(returns) / len(returns)
