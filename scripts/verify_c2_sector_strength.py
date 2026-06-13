#!/usr/bin/env python
"""Verify the C2 staged sector-strength scoring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.strategy import evaluate_latest_fixture_sector_strength


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent


class StageGuardAdapter(FixtureMarketDataAdapter):
    """Guard that fails if C2 asks for stock-level data too early."""

    def load(self):  # noqa: ANN201
        raise AssertionError("C2 must not load the full dataset")

    def load_security_master(self):  # noqa: ANN201
        raise AssertionError("C2 must not load the stock pool")

    def load_symbol_daily_bars(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        raise AssertionError("C2 must not load symbol-level daily bars")

    def load_ownership_flow_signals(
        self, *args, **kwargs
    ):  # noqa: ANN002, ANN003, ANN201
        raise AssertionError("C2 must not load stock-level ownership flow")

    def load_fundamental_risk_events(
        self, *args, **kwargs
    ):  # noqa: ANN002, ANN003, ANN201
        raise AssertionError("C2 must not load stock-level risk events")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    report = evaluate_latest_fixture_sector_strength(StageGuardAdapter())
    check(report.trade_date, "trade_date is required")
    check(report.market_state == "rotation_opportunity", "fixture state mismatch")
    check(report.buy_permission == "rotation_only", "fixture permission mismatch")
    check(report.scores, "sector scores must not be empty")
    check(report.eligible_sector_ids, "eligible sectors must not be empty")
    check(
        report.eligible_sector_ids == ("advanced_manufacturing",),
        "fixture should allow only the active rotation sector",
    )

    top = report.scores[0]
    check(top.rank == 1, "top sector rank mismatch")
    check(top.score > 0, "top sector must have positive score")
    check(top.amount_ratio_20d > 0, "amount ratio must be positive")
    check(top.reason == "active_sector_confirmed_by_market_state", "reason mismatch")

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check(
        "`C2`" in blueprint_text and "板块强度" in blueprint_text,
        "blueprint missing C2",
    )

    return {
        "status": "PASS",
        "trade_date": report.trade_date,
        "market_state": report.market_state,
        "buy_permission": report.buy_permission,
        "eligible_sector_ids": list(report.eligible_sector_ids),
        "top_sector": {
            "sector_id": top.sector_id,
            "score": top.score,
            "relative_strength_5d": top.relative_strength_5d,
            "relative_strength_20d": top.relative_strength_20d,
            "amount_ratio_20d": top.amount_ratio_20d,
        },
        "staged_sector_context_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify C2 sector-strength scoring.")
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
