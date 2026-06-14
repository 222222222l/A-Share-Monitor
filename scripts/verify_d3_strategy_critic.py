#!/usr/bin/env python
"""Verify D3 deterministic strategy-critic guardrails."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from a_share_monitor.reporting import build_latest_fixture_report
from a_share_monitor.reporting import review_structured_report


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    report = build_latest_fixture_report()
    valid_review = review_structured_report(report)
    check(valid_review["status"] == "pass", "valid report should pass")

    low_rr = copy.deepcopy(report)
    low_rr["recommendations"][0]["risk_reward"] = 1.2
    low_rr_review = review_structured_report(low_rr)
    check(
        "688001.SH:risk_reward_below_threshold" in low_rr_review["findings"],
        "critic missed low risk-reward",
    )

    missing_exit = copy.deepcopy(report)
    missing_exit["recommendations"][0]["technical_exit_price"] = None
    missing_exit_review = review_structured_report(missing_exit)
    check(
        "688001.SH:missing_technical_exit_price" in missing_exit_review["findings"],
        "critic missed missing technical exit",
    )

    watchlist_plan = copy.deepcopy(report)
    watchlist_plan["selection_summary"]["planned_symbols"].append("600001.SH")
    watchlist_plan_review = review_structured_report(watchlist_plan)
    check(
        "watchlist_symbol_has_buy_plan" in watchlist_plan_review["findings"],
        "critic missed watchlist buy plan",
    )

    real_trading = copy.deepcopy(report)
    real_trading["decision_boundary"]["real_trading_enabled"] = True
    real_trading_review = review_structured_report(real_trading)
    check(
        "real_trading_boundary_missing" in real_trading_review["findings"],
        "critic missed real trading boundary",
    )

    config = PACKAGE_ROOT / "creatures" / "strategy-critic" / "config.yaml"
    prompt = PACKAGE_ROOT / "creatures" / "strategy-critic" / "prompts" / "system.md"
    check(config.exists(), "strategy-critic config missing")
    check(prompt.exists(), "strategy-critic prompt missing")

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check(
        "`D3`" in blueprint_text and "critic" in blueprint_text, "blueprint missing D3"
    )

    return {
        "status": "PASS",
        "valid_status": valid_review["status"],
        "low_risk_reward_findings": low_rr_review["findings"],
        "missing_exit_findings": missing_exit_review["findings"],
        "watchlist_plan_findings": watchlist_plan_review["findings"],
        "real_trading_findings": real_trading_review["findings"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify D3 strategy critic.")
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
