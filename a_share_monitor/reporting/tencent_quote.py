"""Tencent batch quote adapter for A-share universe snapshots."""

from __future__ import annotations

import http.client
import time
import urllib.error
import urllib.request
from typing import Any, Callable

HTTP_ATTEMPTS = 2
HTTP_TIMEOUT_SECONDS = 12
TENCENT_BATCH_SIZE = 800
TENCENT_INDEX_SYMBOLS = [
    "sh000001",
    "sz399001",
    "sz399006",
    "sh000688",
    "sh000300",
    "sz399905",
]


def fetch_tencent_universe_quotes(
    *, progress: Callable[[str, dict[str, Any]], None] | None = None
) -> list[dict[str, Any]]:
    """Fetch a broad A-share quote universe through Tencent batch quote."""
    symbols = _candidate_symbols()
    quotes: list[dict[str, Any]] = []
    for batch_index, batch in enumerate(_chunks(symbols, TENCENT_BATCH_SIZE), start=1):
        text = _fetch_quote_batch(batch)
        parsed = [_parse_quote_line(line) for line in text.split(";")]
        valid = [row for row in parsed if row is not None and _is_usable_quote(row)]
        quotes.extend(valid)
        if batch_index == 1 or batch_index % 5 == 0:
            _progress(
                progress,
                "quote_batch",
                {
                    "source": "tencent_batch_quote",
                    "batch": batch_index,
                    "symbols_checked": min(
                        batch_index * TENCENT_BATCH_SIZE, len(symbols)
                    ),
                    "usable_quotes": len(quotes),
                    "candidate_symbols": len(symbols),
                },
            )
    if not quotes:
        raise RuntimeError("tencent batch quote returned no usable A-share quotes")
    return quotes


def fetch_tencent_index_quotes(
    *, progress: Callable[[str, dict[str, Any]], None] | None = None
) -> list[dict[str, Any]]:
    """Fetch major A-share index quotes through Tencent batch quote."""
    text = _fetch_quote_batch(TENCENT_INDEX_SYMBOLS)
    parsed = [
        _parse_quote_line(line, source="tencent_index_quote")
        for line in text.split(";")
    ]
    quotes = [row for row in parsed if row is not None and float(row["close"]) > 0]
    _progress(
        progress,
        "index_source_done",
        {"source": "tencent_index_quote", "usable_indices": len(quotes)},
    )
    if not quotes:
        raise RuntimeError("tencent index quote returned no usable A-share indices")
    return quotes


def _candidate_symbols() -> list[str]:
    symbols: list[str] = []
    symbols.extend(f"sz{code:06d}" for code in range(1, 4000))
    symbols.extend(f"sz{code:06d}" for code in range(300000, 302000))
    symbols.extend(f"sh{code:06d}" for code in range(600000, 606000))
    symbols.extend(f"sh{code:06d}" for code in range(688000, 690000))
    return symbols


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _fetch_quote_batch(symbols: list[str]) -> str:
    url = "https://web.sqt.gtimg.cn/q=" + ",".join(symbols)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AShareMonitor/0.1",
            "Accept": "*/*",
            "Referer": "https://stockapp.finance.qq.com/",
        },
    )
    last_error: Exception | None = None
    for attempt in range(1, HTTP_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(
                request, timeout=HTTP_TIMEOUT_SECONDS
            ) as response:
                return response.read().decode("gbk", errors="ignore")
        except (urllib.error.URLError, http.client.RemoteDisconnected) as exc:
            last_error = exc
            time.sleep(0.5 * attempt)
    raise RuntimeError(f"tencent quote request failed after retries: {last_error}")


def _parse_quote_line(
    line: str, *, source: str = "tencent_batch_quote"
) -> dict[str, Any] | None:
    if '="' not in line:
        return None
    body = line.split('="', 1)[1].rstrip('"')
    parts = body.split("~")
    if len(parts) < 38 or not parts[1] or not parts[2]:
        return None
    amount = _to_float(parts[37]) * 10_000
    amount_raw = parts[35].split("/")
    if len(amount_raw) >= 3:
        amount = _to_float(amount_raw[2], default=amount)
    return {
        "symbol": parts[2],
        "name": parts[1],
        "close": _to_float(parts[3]),
        "pct_change": _to_float(parts[32]),
        "volume": _to_float(parts[36]),
        "amount": amount,
        "high": _to_float(parts[33]),
        "low": _to_float(parts[34]),
        "open": _to_float(parts[5]),
        "prev_close": _to_float(parts[4]),
        "float_market_cap": 0.0,
        "main_net_inflow": 0.0,
        "source": source,
    }


def _is_usable_quote(row: dict[str, Any]) -> bool:
    name = str(row.get("name") or "")
    close = float(row.get("close") or 0.0)
    amount = float(row.get("amount") or 0.0)
    return close > 0 and amount > 0 and "ST" not in name.upper()


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
