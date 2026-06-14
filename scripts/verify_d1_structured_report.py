#!/usr/bin/env python
"""Verify D1 structured report generation and lab-runner wiring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.reporting import build_latest_fixture_report


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    report = build_latest_fixture_report()
    check(report["schema_version"] == "a-share-monitor.report.v1", "schema mismatch")
    check(report["trade_date"] == "2025-09-10", "fixture trade date mismatch")
    check(
        report["selection_summary"]["planned_symbols"] == ["688001.SH"],
        "planned symbol mismatch",
    )
    check(
        report["selection_summary"]["watchlist_symbols"]
        == [
            "600001.SH",
            "000001.SZ",
        ],
        "watchlist mismatch",
    )
    check(report["critic_review"]["status"] == "pass", "critic review failed")
    check(
        report["decision_boundary"]["real_trading_enabled"] is False,
        "unsafe trading boundary",
    )
    recommendation = report["recommendations"][0]
    for field in (
        "entry_zone",
        "technical_exit_price",
        "technical_exit_reason",
        "fundamental_exit_trigger",
        "ownership_flow_risk",
        "time_exit_rule",
        "risk_reward",
    ):
        check(field in recommendation and recommendation[field], f"missing {field}")

    tool_path = (
        PACKAGE_ROOT / "creatures" / "lab-runner" / "tools" / "a_share_report.py"
    )
    tool_text = tool_path.read_text(encoding="utf-8")
    check("class AShareReportTool" in tool_text, "tool class missing")
    check('return "generate_a_share_report"' in tool_text, "tool name mismatch")

    config = PACKAGE_ROOT / "creatures" / "lab-runner" / "config.yaml"
    config_text = config.read_text(encoding="utf-8")
    check("generate_a_share_report" in config_text, "lab-runner tool not wired")

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check(
        "`D1`" in blueprint_text and "a-share-monitor.report.v1" in blueprint_text,
        "blueprint missing D1",
    )

    return {
        "status": "PASS",
        "trade_date": report["trade_date"],
        "planned_symbols": report["selection_summary"]["planned_symbols"],
        "watchlist_symbols": report["selection_summary"]["watchlist_symbols"],
        "recommendation_count": len(report["recommendations"]),
        "critic_status": report["critic_review"]["status"],
        "tool": "generate_a_share_report",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify D1 structured report.")
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
