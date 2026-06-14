#!/usr/bin/env python
"""Run a C-group system test for technical screening effectiveness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.strategy import evaluate_latest_fixture_risk_plan
from a_share_monitor.strategy import evaluate_latest_fixture_stock_screen
from a_share_monitor.strategy import evaluate_latest_fixture_technical_indicators


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    adapter = FixtureMarketDataAdapter()
    stock_report = evaluate_latest_fixture_stock_screen(adapter)
    technical_report = evaluate_latest_fixture_technical_indicators(adapter)
    risk_report = evaluate_latest_fixture_risk_plan(adapter)

    check(stock_report.candidate_symbols == ("688001.SH",), "candidate mismatch")
    check(
        set(stock_report.watchlist_symbols) == {"600001.SH", "000001.SZ"},
        "watchlist mismatch",
    )
    check(
        not set(stock_report.watchlist_symbols).intersection(
            risk_report.planned_symbols
        ),
        "watchlist symbols must not receive buy plans",
    )
    check(
        set(technical_report.symbols)
        == set(stock_report.candidate_symbols + stock_report.watchlist_symbols),
        "technical indicators must be scoped to C3 outputs",
    )
    check(
        risk_report.planned_symbols == stock_report.candidate_symbols,
        "C4 plans must be candidate-only",
    )

    signal_by_symbol = {item.symbol: item for item in stock_report.signals}
    candidate = signal_by_symbol["688001.SH"]
    check(candidate.right_side_confirmed, "candidate lacks right-side confirmation")
    check(
        candidate.setup_type in {"trend_pullback", "platform_breakout"},
        "candidate setup is not right-side",
    )
    check(candidate.evidence["close"] > candidate.evidence["ma20"], "close <= MA20")
    check(
        candidate.evidence["ma20"] >= candidate.evidence["ma60"] * 0.995,
        "MA20 is not aligned with MA60",
    )
    check(
        candidate.evidence["amount_ratio_20d"] >= 0.95,
        "candidate volume confirmation is weak",
    )

    for symbol in stock_report.watchlist_symbols:
        signal = signal_by_symbol[symbol]
        check(not signal.right_side_confirmed, "watchlist has right-side signal")
        check(signal.setup_type == "none", "watchlist emitted a buy setup")
        check(
            signal.rejection_reason == "technical_signal_not_ready",
            "watchlist reason mismatch",
        )

    snapshots = {item.symbol: item for item in technical_report.snapshots}
    candidate_snapshot = snapshots["688001.SH"]
    check(candidate_snapshot.atr_14 > 0, "candidate ATR missing")
    check(0 <= candidate_snapshot.rsi_14 <= 100, "candidate RSI out of range")
    check(
        candidate_snapshot.ema_20 > candidate_snapshot.ema_60 * 0.995, "EMA trend weak"
    )

    for recommendation in risk_report.recommendations:
        check(recommendation.decision == "buy_ready", "recommendation not buy_ready")
        check(
            recommendation.risk_reward > risk_report.min_risk_reward,
            "risk-reward threshold failed",
        )
        check(
            recommendation.technical_exit_price < recommendation.entry_zone[0],
            "technical exit is not below entry",
        )

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check(
        "任务组 C" in blueprint_text and "`C4`" in blueprint_text,
        "blueprint missing C group",
    )

    return {
        "status": "PASS",
        "trade_date": stock_report.trade_date,
        "candidate_symbols": list(stock_report.candidate_symbols),
        "watchlist_symbols": list(stock_report.watchlist_symbols),
        "planned_symbols": list(risk_report.planned_symbols),
        "technical_snapshot_count": len(technical_report.snapshots),
        "candidate_setup": candidate.setup_type,
        "candidate_risk_reward": risk_report.recommendations[0].risk_reward,
        "screening_effective": True,
        "watchlist_excluded_from_buy_plan": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the C-group technical screening system."
    )
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
