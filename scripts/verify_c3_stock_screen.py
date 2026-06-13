#!/usr/bin/env python
"""Verify the C3 right-side stock screening stage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.strategy import evaluate_latest_fixture_stock_screen


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent

RIGHT_SIDE_SETUPS = {"trend_pullback", "platform_breakout"}


class StageGuardAdapter(FixtureMarketDataAdapter):
    """Guard that blocks full-dataset and fundamental-risk loads in C3."""

    def load(self):  # noqa: ANN201
        raise AssertionError("C3 must not load the full dataset")

    def load_fundamental_risk_events(
        self, *args, **kwargs
    ):  # noqa: ANN002, ANN003, ANN201
        raise AssertionError("C3 must not load fundamental risk events")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    report = evaluate_latest_fixture_stock_screen(StageGuardAdapter())
    check(report.trade_date, "trade_date is required")
    check(report.buy_permission == "rotation_only", "fixture permission mismatch")
    check(
        report.eligible_sector_ids == ("advanced_manufacturing",),
        "sector scope mismatch",
    )
    check(report.signals, "stock signals must not be empty")
    check(
        report.watchlist_symbols, "watchlist should contain technically pending symbols"
    )

    for signal in report.signals:
        check(
            signal.sector_id in report.eligible_sector_ids,
            "signal outside eligible sector",
        )
        if signal.signal_status == "candidate":
            check(
                signal.setup_type in RIGHT_SIDE_SETUPS, "candidate must be right-side"
            )
            check(
                signal.right_side_confirmed, "candidate missing right-side confirmation"
            )
            check(
                signal.evidence.get("right_side_only") is True,
                "right-side evidence missing",
            )
        if signal.setup_type == "oversold_reversal":
            raise AssertionError("C3 must not emit oversold_reversal buy setups")
        if signal.signal_status == "watchlist":
            check(signal.setup_type == "none", "watchlist must not emit buy setup")
            check(
                signal.rejection_reason == "technical_signal_not_ready",
                "watchlist reason mismatch",
            )

    rejected_reasons = {item.rejection_reason for item in report.signals}
    check(
        "retail_crowding_institution_exit" in rejected_reasons
        or "technical_signal_not_ready" in rejected_reasons,
        "expected at least one risk rejection or watchlist reason",
    )

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check("`C3`" in blueprint_text and "右侧" in blueprint_text, "blueprint missing C3")

    return {
        "status": "PASS",
        "trade_date": report.trade_date,
        "buy_permission": report.buy_permission,
        "eligible_sector_ids": list(report.eligible_sector_ids),
        "candidate_symbols": list(report.candidate_symbols),
        "watchlist_symbols": list(report.watchlist_symbols),
        "rejected_symbols": list(report.rejected_symbols),
        "signal_count": len(report.signals),
        "right_side_only": True,
        "incremental_watchlist": True,
        "fundamental_risk_as_final_warning_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify C3 right-side stock screen.")
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
