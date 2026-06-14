#!/usr/bin/env python
"""Verify E3 paper-trading log format."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.backtest import build_paper_trade_log
from a_share_monitor.reporting import build_latest_fixture_report


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    report = build_latest_fixture_report()
    log = build_paper_trade_log(report)
    check(log["schema_version"] == "a-share-monitor.paper-log.v1", "schema mismatch")
    check(log["real_trading_enabled"] is False, "real trading must stay disabled")
    check(log["entries"], "paper log must contain entries")
    entry = log["entries"][0]
    for field in (
        "signal_id",
        "symbol",
        "planned_order",
        "fill_assumption",
        "risk_controls",
        "position",
        "exit_review",
        "audit",
    ):
        check(field in entry and entry[field], f"missing {field}")
    check(entry["planned_order"]["real_order_enabled"] is False, "real order enabled")
    check(entry["fill_assumption"]["t_plus_one"] is True, "T+1 missing")
    check(entry["position"]["state"] == "planned", "position state mismatch")
    check(
        entry["audit"]["final_decision_owner"] == "user",
        "user decision owner missing",
    )

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check(
        "`E3`" in blueprint_text and "paper_trading.py" in blueprint_text,
        "blueprint missing E3",
    )

    return {
        "status": "PASS",
        "schema_version": log["schema_version"],
        "entry_count": len(log["entries"]),
        "symbols": [item["symbol"] for item in log["entries"]],
        "real_trading_enabled": log["real_trading_enabled"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify E3 paper trading log.")
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
