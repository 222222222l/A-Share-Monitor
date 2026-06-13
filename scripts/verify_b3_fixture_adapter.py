#!/usr/bin/env python
"""Verify the B3 fixture data adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.data import load_fixture_dataset


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    dataset = load_fixture_dataset()
    check(dataset.dataset_id == "b2_minimal", "dataset id mismatch")
    check(dataset.source == "fixture", "dataset source mismatch")
    check(len(dataset.tradable_symbols) == 5, "expected five tradable symbols")
    check(dataset.reference_only_symbols == ("920001.BJ",), "BSE reference mismatch")
    check(len(dataset.trade_dates) == 180, "expected 180 trade dates")
    check(len(dataset.daily_bars) == 900, "expected 900 daily bars")
    check(len(dataset.index_bars) >= 360, "expected at least two index histories")
    check(len(dataset.sector_bars) >= 360, "expected two sector histories")
    check(dataset.market_breadth, "market breadth must be loaded")
    check(dataset.fundamental_risk_events, "risk events must be loaded")

    ownership_by_signal = {
        item.counterparty_signal for item in dataset.ownership_flow_signals
    }
    check(
        "retail_institution_exit_risk" in ownership_by_signal,
        "missing retail crowding / institution exit risk signal",
    )
    check(
        "retail_exit_institution_accumulation" in ownership_by_signal,
        "missing retail exit / institution accumulation signal",
    )

    tradable_set = set(dataset.tradable_symbols)
    ownership_symbols = {item.symbol for item in dataset.ownership_flow_signals}
    check(
        tradable_set <= ownership_symbols,
        "ownership flow signals must cover tradable symbols",
    )

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check(
        "`B3`" in blueprint_text and "adapter" in blueprint_text, "blueprint missing B3"
    )

    return {
        "status": "PASS",
        "dataset_id": dataset.dataset_id,
        "source": dataset.source,
        "tradable_symbols": list(dataset.tradable_symbols),
        "reference_only_symbols": list(dataset.reference_only_symbols),
        "trade_dates": len(dataset.trade_dates),
        "daily_bars": len(dataset.daily_bars),
        "ownership_flow_signals": len(dataset.ownership_flow_signals),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify B3 fixture adapter.")
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
