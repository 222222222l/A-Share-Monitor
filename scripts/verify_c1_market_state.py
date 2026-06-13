#!/usr/bin/env python
"""Verify the C1 staged market-state gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.strategy import evaluate_latest_fixture_market_state


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent

EXPECTED_STATES = {
    "liquidity_crisis",
    "policy_support_rebound",
    "rotation_opportunity",
    "broad_risk_on",
    "mixed_chop",
    "overheated_chase_risk",
    "unknown",
}

EXPECTED_PERMISSIONS = {
    "blocked",
    "selective",
    "rotation_only",
    "rebound_watch",
    "normal",
}


class StageGuardAdapter(FixtureMarketDataAdapter):
    """Guard that fails if C1 asks for later-stage stock-level data."""

    def load(self):  # noqa: ANN201
        raise AssertionError("C1 must not load the full dataset")

    def load_security_master(self):  # noqa: ANN201
        raise AssertionError("C1 must not load the stock pool")

    def load_symbol_daily_bars(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        raise AssertionError("C1 must not load symbol-level daily bars")

    def load_ownership_flow_signals(
        self, *args, **kwargs
    ):  # noqa: ANN002, ANN003, ANN201
        raise AssertionError("C1 must not load stock-level ownership flow")

    def load_fundamental_risk_events(
        self, *args, **kwargs
    ):  # noqa: ANN002, ANN003, ANN201
        raise AssertionError("C1 must not load stock-level risk events")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    signal = evaluate_latest_fixture_market_state(StageGuardAdapter())
    check(signal.market_state in EXPECTED_STATES, "unexpected market_state")
    check(signal.buy_permission in EXPECTED_PERMISSIONS, "unexpected buy_permission")
    check(signal.trade_date, "trade_date is required")
    check(signal.evidence["total_amount"] > 0, "total_amount evidence missing")
    check("advancing_ratio" in signal.evidence, "breadth evidence missing")
    check("active_sector_ids" in signal.evidence, "sector evidence missing")

    if signal.buy_permission == "blocked":
        check(signal.market_state == "liquidity_crisis", "blocked state mismatch")
    if signal.buy_permission == "rotation_only":
        check(signal.active_sector_ids, "rotation_only requires active sectors")

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check(
        "`C1`" in blueprint_text and "buy_permission" in blueprint_text,
        "blueprint missing C1",
    )

    return {
        "status": "PASS",
        "trade_date": signal.trade_date,
        "market_state": signal.market_state,
        "buy_permission": signal.buy_permission,
        "liquidity_state": signal.liquidity_state,
        "breadth_state": signal.breadth_state,
        "rotation_state": signal.rotation_state,
        "active_sector_ids": list(signal.active_sector_ids),
        "staged_market_context_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify C1 market-state gate.")
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
