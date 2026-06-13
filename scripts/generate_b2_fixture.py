#!/usr/bin/env python
"""Generate deterministic B2 offline fixtures for a-share-monitor."""

from __future__ import annotations

import csv
import json
import math
from datetime import date, timedelta
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
FIXTURE_ROOT = PACKAGE_ROOT / "fixtures" / "b2_minimal"

TRADE_DAY_COUNT = 180
START_DATE = date(2025, 1, 2)

SECURITIES = [
    {
        "symbol": "600001.SH",
        "exchange": "sse",
        "name": "Fixture Main Alpha",
        "market_board": "sse_main",
        "sector_id": "advanced_manufacturing",
        "base": 18.40,
        "drift": 0.018,
        "limit_pct": 0.10,
    },
    {
        "symbol": "000001.SZ",
        "exchange": "szse",
        "name": "Fixture Main Beta",
        "market_board": "szse_main",
        "sector_id": "advanced_manufacturing",
        "base": 12.20,
        "drift": 0.006,
        "limit_pct": 0.10,
    },
    {
        "symbol": "002001.SZ",
        "exchange": "szse",
        "name": "Fixture SME Gamma",
        "market_board": "szse_main",
        "sector_id": "consumer_recovery",
        "base": 9.60,
        "drift": -0.002,
        "limit_pct": 0.10,
    },
    {
        "symbol": "300001.SZ",
        "exchange": "szse",
        "name": "Fixture Growth Delta",
        "market_board": "chinext",
        "sector_id": "consumer_recovery",
        "base": 24.80,
        "drift": 0.014,
        "limit_pct": 0.20,
    },
    {
        "symbol": "688001.SH",
        "exchange": "sse",
        "name": "Fixture Star Epsilon",
        "market_board": "star",
        "sector_id": "advanced_manufacturing",
        "base": 31.50,
        "drift": 0.010,
        "limit_pct": 0.20,
    },
]

BSE_REFERENCE = {
    "symbol": "920001.BJ",
    "exchange": "bse",
    "name": "Fixture BSE Reference",
    "market_board": "bse",
}

INDEXES = [
    {"index_symbol": "000300.SH", "index_name": "CSI 300 Fixture", "base": 3600.0},
    {"index_symbol": "000852.SH", "index_name": "CSI 1000 Fixture", "base": 5600.0},
    {"index_symbol": "899050.BJ", "index_name": "BSE 50 Fixture", "base": 980.0},
]

SECTORS = [
    {
        "sector_id": "advanced_manufacturing",
        "sector_name": "Advanced Manufacturing Fixture",
        "base": 1000.0,
    },
    {
        "sector_id": "consumer_recovery",
        "sector_name": "Consumer Recovery Fixture",
        "base": 880.0,
    },
]


def business_days(start: date, count: int) -> list[date]:
    days = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def fmt(value: float) -> str:
    return f"{value:.4f}"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def price_curve(base: float, drift: float, day_index: int, phase: float) -> float:
    wave = math.sin(day_index / 7.0 + phase) * 0.025
    pulse = math.sin(day_index / 19.0 + phase / 2.0) * 0.018
    return base * (1 + drift * day_index / TRADE_DAY_COUNT + wave + pulse)


def generate_security_master() -> list[dict[str, object]]:
    rows = []
    for security in SECURITIES:
        rows.append(
            {
                "symbol": security["symbol"],
                "exchange": security["exchange"],
                "name": security["name"],
                "list_date": "2020-01-02",
                "market_board": security["market_board"],
                "tradable": "true",
                "bse_reference_only": "false",
                "industry": "fixture-industry",
                "sector_tags": security["sector_id"],
                "delist_date": "",
                "risk_flags": "",
            }
        )
    rows.append(
        {
            "symbol": BSE_REFERENCE["symbol"],
            "exchange": BSE_REFERENCE["exchange"],
            "name": BSE_REFERENCE["name"],
            "list_date": "2021-11-15",
            "market_board": BSE_REFERENCE["market_board"],
            "tradable": "false",
            "bse_reference_only": "true",
            "industry": "fixture-reference",
            "sector_tags": "small_cap_reference",
            "delist_date": "",
            "risk_flags": "reference_only",
        }
    )
    return rows


def generate_daily_bars(days: list[date]) -> list[dict[str, object]]:
    rows = []
    for security_index, security in enumerate(SECURITIES):
        prev_close = float(security["base"])
        phase = security_index * 1.7
        for day_index, trade_day in enumerate(days):
            close = price_curve(
                float(security["base"]), float(security["drift"]), day_index, phase
            )
            open_price = (prev_close * 0.55) + (close * 0.45)
            spread = 0.015 + abs(math.sin(day_index / 5.0 + phase)) * 0.01
            high = max(open_price, close) * (1 + spread)
            low = min(open_price, close) * (1 - spread * 0.85)
            volume = int(1_200_000 + security_index * 180_000 + day_index * 3_100)
            amount = close * volume
            rows.append(
                {
                    "symbol": security["symbol"],
                    "trade_date": trade_day.isoformat(),
                    "open": fmt(open_price),
                    "high": fmt(high),
                    "low": fmt(low),
                    "close": fmt(close),
                    "volume": volume,
                    "amount": fmt(amount),
                    "adj_factor": "1.0000",
                    "is_suspended": "false",
                    "limit_up": fmt(prev_close * (1 + float(security["limit_pct"]))),
                    "limit_down": fmt(prev_close * (1 - float(security["limit_pct"]))),
                    "is_st": "false",
                    "is_new_stock": "false",
                    "turnover_rate": fmt(1.2 + security_index * 0.2),
                    "amplitude": fmt((high - low) / prev_close),
                    "prev_close": fmt(prev_close),
                    "free_float_market_cap": fmt(close * 200_000_000),
                }
            )
            prev_close = close
    return rows


def generate_index_bars(days: list[date]) -> list[dict[str, object]]:
    rows = []
    for index, item in enumerate(INDEXES):
        prev_close = float(item["base"])
        for day_index, trade_day in enumerate(days):
            close = price_curve(
                float(item["base"]), 0.008 - index * 0.002, day_index, index
            )
            open_price = (prev_close * 0.60) + (close * 0.40)
            high = max(open_price, close) * 1.008
            low = min(open_price, close) * 0.992
            rows.append(
                {
                    "index_symbol": item["index_symbol"],
                    "trade_date": trade_day.isoformat(),
                    "open": fmt(open_price),
                    "high": fmt(high),
                    "low": fmt(low),
                    "close": fmt(close),
                    "volume": int(90_000_000 + day_index * 100_000),
                    "amount": fmt(close * (90_000_000 + day_index * 100_000)),
                    "index_name": item["index_name"],
                    "reference_market": (
                        "bse" if item["index_symbol"].endswith(".BJ") else "a_share"
                    ),
                }
            )
            prev_close = close
    return rows


def generate_sector_bars(days: list[date]) -> list[dict[str, object]]:
    rows = []
    for sector_index, sector in enumerate(SECTORS):
        prev_close = float(sector["base"])
        for day_index, trade_day in enumerate(days):
            close = price_curve(
                float(sector["base"]),
                0.012 - sector_index * 0.006,
                day_index,
                sector_index,
            )
            pct_change = (close - prev_close) / prev_close if day_index else 0.0
            rows.append(
                {
                    "sector_id": sector["sector_id"],
                    "sector_name": sector["sector_name"],
                    "trade_date": trade_day.isoformat(),
                    "close": fmt(close),
                    "pct_change": fmt(pct_change),
                    "amount": fmt(18_000_000_000 + day_index * 24_000_000),
                    "constituent_count": 3 if sector_index == 0 else 2,
                    "provider": "fixture",
                    "industry_level": "L1",
                    "concept_tags": "fixture",
                }
            )
            prev_close = close
    return rows


def generate_market_breadth(days: list[date]) -> list[dict[str, object]]:
    rows = []
    for day_index, trade_day in enumerate(days):
        advancing = 2600 + int(math.sin(day_index / 8.0) * 450)
        declining = 5000 - advancing
        rows.append(
            {
                "trade_date": trade_day.isoformat(),
                "universe": "a_share_fixture",
                "advancing_count": advancing,
                "declining_count": declining,
                "limit_up_count": 42 + day_index % 18,
                "limit_down_count": 8 + day_index % 7,
                "new_high_20d_count": 150 + day_index % 40,
                "new_low_20d_count": 70 + day_index % 30,
                "total_amount": fmt(820_000_000_000 + day_index * 900_000_000),
                "bse_amount": fmt(12_000_000_000 + day_index * 30_000_000),
                "bse_advancing_count": 120 + day_index % 25,
                "bse_declining_count": 80 + day_index % 20,
            }
        )
    return rows


def generate_fundamental_events(days: list[date]) -> list[dict[str, object]]:
    return [
        {
            "symbol": "002001.SZ",
            "event_date": days[-45].isoformat(),
            "announcement_date": days[-44].isoformat(),
            "event_type": "cashflow_warning",
            "severity": "medium",
            "summary": "Synthetic fixture event for risk-filter validation.",
            "source": "fixture",
            "source_url": "",
            "numeric_impact": "",
            "related_report_period": "2025Q2",
        }
    ]


def generate_ownership_flow(days: list[date]) -> list[dict[str, object]]:
    rows = []
    trade_day = days[-1].isoformat()
    signals = [
        ("600001.SH", 22, 78, 12, "retail_exit_institution_accumulation"),
        ("000001.SZ", 48, 51, 28, "mixed"),
        ("002001.SZ", 83, 18, 76, "retail_institution_exit_risk"),
        ("300001.SZ", 36, 66, 20, "retail_exit_institution_accumulation"),
        ("688001.SH", 58, 44, 39, "mixed"),
    ]
    for index, (
        symbol,
        retail_score,
        accumulation_score,
        exit_score,
        signal,
    ) in enumerate(signals):
        rows.append(
            {
                "symbol": symbol,
                "trade_date": trade_day,
                "retail_crowding_score": retail_score,
                "institutional_accumulation_score": accumulation_score,
                "institutional_exit_score": exit_score,
                "counterparty_signal": signal,
                "evidence": "synthetic proxy evidence for counterparty-flow validation",
                "shareholder_count_change_pct": fmt(0.08 - index * 0.035),
                "avg_holding_per_account_change_pct": fmt(-0.04 + index * 0.025),
                "northbound_holding_change_pct": fmt(0.03 - index * 0.01),
                "margin_balance_change_pct": fmt(0.06 - index * 0.015),
                "margin_buy_ratio": fmt(0.52 + index * 0.03),
                "dragon_tiger_institution_net_buy": fmt(12_000_000 - index * 4_000_000),
                "block_trade_discount_rate": fmt(-0.02 + index * 0.006),
                "block_trade_net_amount": fmt(8_000_000 - index * 2_000_000),
                "fund_holding_change_pct": fmt(0.015 - index * 0.006),
                "etf_flow_proxy": fmt(5_000_000 - index * 1_000_000),
                "insider_reduction_amount": fmt(index * 1_500_000),
                "data_lag_days": 15,
            }
        )
    return rows


def write_manifest(days: list[date], counts: dict[str, int]) -> None:
    manifest = {
        "dataset_id": "b2_minimal",
        "version": 1,
        "synthetic": True,
        "purpose": "offline validation fixture for A-share daily monitoring",
        "price_mode": "qfq",
        "volume_unit": "shares",
        "currency": "CNY",
        "start_date": days[0].isoformat(),
        "end_date": days[-1].isoformat(),
        "trading_day_count": len(days),
        "tradable_symbol_count": len(SECURITIES),
        "reference_only_markets": ["bse"],
        "files": counts,
        "safety_note": "Synthetic deterministic data; not investment advice.",
    }
    (FIXTURE_ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> int:
    days = business_days(START_DATE, TRADE_DAY_COUNT)
    FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)

    security_rows = generate_security_master()
    daily_rows = generate_daily_bars(days)
    index_rows = generate_index_bars(days)
    sector_rows = generate_sector_bars(days)
    breadth_rows = generate_market_breadth(days)
    event_rows = generate_fundamental_events(days)
    ownership_rows = generate_ownership_flow(days)

    write_csv(
        FIXTURE_ROOT / "security_master.csv",
        [
            "symbol",
            "exchange",
            "name",
            "list_date",
            "market_board",
            "tradable",
            "bse_reference_only",
            "industry",
            "sector_tags",
            "delist_date",
            "risk_flags",
        ],
        security_rows,
    )
    write_csv(
        FIXTURE_ROOT / "daily_bars.csv",
        [
            "symbol",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "adj_factor",
            "is_suspended",
            "limit_up",
            "limit_down",
            "is_st",
            "is_new_stock",
            "turnover_rate",
            "amplitude",
            "prev_close",
            "free_float_market_cap",
        ],
        daily_rows,
    )
    write_csv(
        FIXTURE_ROOT / "index_bars.csv",
        [
            "index_symbol",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "index_name",
            "reference_market",
        ],
        index_rows,
    )
    write_csv(
        FIXTURE_ROOT / "sector_bars.csv",
        [
            "sector_id",
            "sector_name",
            "trade_date",
            "close",
            "pct_change",
            "amount",
            "constituent_count",
            "provider",
            "industry_level",
            "concept_tags",
        ],
        sector_rows,
    )
    write_csv(
        FIXTURE_ROOT / "market_breadth.csv",
        [
            "trade_date",
            "universe",
            "advancing_count",
            "declining_count",
            "limit_up_count",
            "limit_down_count",
            "new_high_20d_count",
            "new_low_20d_count",
            "total_amount",
            "bse_amount",
            "bse_advancing_count",
            "bse_declining_count",
        ],
        breadth_rows,
    )
    write_csv(
        FIXTURE_ROOT / "fundamental_risk_events.csv",
        [
            "symbol",
            "event_date",
            "announcement_date",
            "event_type",
            "severity",
            "summary",
            "source",
            "source_url",
            "numeric_impact",
            "related_report_period",
        ],
        event_rows,
    )
    write_csv(
        FIXTURE_ROOT / "ownership_flow_signals.csv",
        [
            "symbol",
            "trade_date",
            "retail_crowding_score",
            "institutional_accumulation_score",
            "institutional_exit_score",
            "counterparty_signal",
            "evidence",
            "shareholder_count_change_pct",
            "avg_holding_per_account_change_pct",
            "northbound_holding_change_pct",
            "margin_balance_change_pct",
            "margin_buy_ratio",
            "dragon_tiger_institution_net_buy",
            "block_trade_discount_rate",
            "block_trade_net_amount",
            "fund_holding_change_pct",
            "etf_flow_proxy",
            "insider_reduction_amount",
            "data_lag_days",
        ],
        ownership_rows,
    )
    write_manifest(
        days,
        {
            "security_master.csv": len(security_rows),
            "daily_bars.csv": len(daily_rows),
            "index_bars.csv": len(index_rows),
            "sector_bars.csv": len(sector_rows),
            "market_breadth.csv": len(breadth_rows),
            "fundamental_risk_events.csv": len(event_rows),
            "ownership_flow_signals.csv": len(ownership_rows),
        },
    )
    print(f"Generated B2 fixture at {FIXTURE_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
