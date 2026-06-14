#!/usr/bin/env python
"""Verify E2 simple event-driven backtest behavior."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.backtest import BacktestConfig
from a_share_monitor.backtest import simulate_long_plan
from a_share_monitor.data import DailyBar
from a_share_monitor.strategy import evaluate_latest_fixture_risk_plan


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    risk_report = evaluate_latest_fixture_risk_plan()
    recommendation = risk_report.recommendations[0]
    future_bars = _future_path(recommendation)
    result = simulate_long_plan(
        recommendation,
        future_bars,
        BacktestConfig(commission_bps=3.0, slippage_bps=5.0),
    )
    event_types = [event.event_type for event in result.events]
    check(result.status == "closed", "backtest should close the position")
    check(result.entry_date == "2025-09-11", "entry must be next trading day")
    check("stop_blocked_by_t1" in event_types, "T+1 stop block not modeled")
    check(event_types[-1] == "target_1", "fixture path should hit target_1")
    check(result.net_return > 0, "target hit should produce positive net return")
    check(result.max_adverse_excursion < 0, "adverse excursion should be tracked")

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check(
        "`E2`" in blueprint_text and "event_backtest.py" in blueprint_text,
        "blueprint missing E2",
    )

    return {
        "status": "PASS",
        "symbol": result.symbol,
        "entry_date": result.entry_date,
        "exit_date": result.exit_date,
        "event_types": event_types,
        "net_return": result.net_return,
        "max_adverse_excursion": result.max_adverse_excursion,
    }


def _future_path(recommendation) -> tuple[DailyBar, ...]:  # noqa: ANN001
    entry_open = sum(recommendation.entry_zone) / 2
    return (
        DailyBar(
            symbol=recommendation.symbol,
            trade_date="2025-09-11",
            open=entry_open,
            high=max(entry_open * 1.01, recommendation.entry_zone[1]),
            low=recommendation.technical_exit_price * 0.995,
            close=entry_open * 1.005,
            volume=2_000_000,
            amount=entry_open * 2_000_000,
            adj_factor=1.0,
            is_suspended=False,
            limit_up=entry_open * 1.2,
            limit_down=entry_open * 0.8,
            is_st=False,
            is_new_stock=False,
        ),
        DailyBar(
            symbol=recommendation.symbol,
            trade_date="2025-09-12",
            open=entry_open * 1.01,
            high=recommendation.target_1 * 1.002,
            low=entry_open * 1.005,
            close=recommendation.target_1,
            volume=2_100_000,
            amount=recommendation.target_1 * 2_100_000,
            adj_factor=1.0,
            is_suspended=False,
            limit_up=entry_open * 1.2,
            limit_down=entry_open * 0.8,
            is_st=False,
            is_new_stock=False,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify E2 event backtest.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help="Repository root. Defaults to this script's repository.",
    )
    args = parser.parse_args()

    try:
        result = verify(args.repo_root.resolve())
    except AssertionError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2))
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
