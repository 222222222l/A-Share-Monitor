#!/usr/bin/env python
"""Verify the C0 candidate/watchlist-scoped technical indicators."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.strategy import evaluate_latest_fixture_technical_indicators


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent

REQUIRED_SYMBOLS = {"688001.SH", "600001.SH", "000001.SZ"}


class StageGuardAdapter(FixtureMarketDataAdapter):
    """Guard that blocks full-dataset and fundamental-risk loads in C0."""

    def load(self):  # noqa: ANN201
        raise AssertionError("C0 must not load the full dataset")

    def load_fundamental_risk_events(
        self, *args, **kwargs
    ):  # noqa: ANN002, ANN003, ANN201
        raise AssertionError("C0 must not load fundamental risk events")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    report = evaluate_latest_fixture_technical_indicators(StageGuardAdapter())
    check(report.scoped_to_c3_outputs, "C0 must be scoped to C3 outputs")
    check(set(report.symbols) == REQUIRED_SYMBOLS, "C0 symbol scope mismatch")
    check(len(report.snapshots) == len(REQUIRED_SYMBOLS), "snapshot count mismatch")
    check(len(report.divergences) == len(REQUIRED_SYMBOLS), "divergence count mismatch")

    for snapshot in report.snapshots:
        check(snapshot.symbol in REQUIRED_SYMBOLS, "unexpected snapshot symbol")
        check(snapshot.ema_20 > 0, "EMA20 must be positive")
        check(0 <= snapshot.rsi_14 <= 100, "RSI14 out of range")
        check(snapshot.atr_14 > 0, "ATR14 must be positive")
        check(snapshot.trade_date == report.trade_date, "snapshot date mismatch")

    for divergence in report.divergences:
        check(
            divergence.divergence
            in {"bullish_divergence", "bearish_divergence", "none"},
            "invalid divergence enum",
        )
        if divergence.divergence == "bullish_divergence":
            check(
                "observation only" in divergence.evidence,
                "bullish divergence must remain observation-only",
            )

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check("`C0`" in blueprint_text and "C3" in blueprint_text, "blueprint missing C0")

    return {
        "status": "PASS",
        "trade_date": report.trade_date,
        "symbols": list(report.symbols),
        "snapshot_count": len(report.snapshots),
        "divergence_count": len(report.divergences),
        "scoped_to_c3_outputs": True,
        "right_side_gate_preserved": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify C0 technical indicators.")
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
