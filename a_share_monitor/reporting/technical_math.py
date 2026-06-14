"""Small technical math helpers for real-market reports."""

from __future__ import annotations


def ema(values: list[float], window: int) -> float:
    alpha = 2 / (window + 1)
    result = values[0]
    for value in values[1:]:
        result = value * alpha + result * (1 - alpha)
    return result


def atr(
    highs: list[float], lows: list[float], closes: list[float], window: int
) -> float:
    ranges = []
    for index, high in enumerate(highs):
        low = lows[index]
        if index == 0:
            ranges.append(high - low)
            continue
        previous_close = closes[index - 1]
        ranges.append(
            max(high - low, abs(high - previous_close), abs(low - previous_close))
        )
    sample = ranges[-window:]
    return sum(sample) / len(sample)
