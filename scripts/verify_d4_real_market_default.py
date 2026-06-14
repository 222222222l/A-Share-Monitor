#!/usr/bin/env python
"""Verify that Web UI reports default to real-market mode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.reporting import build_unavailable_real_snapshot
from a_share_monitor.reporting import resolve_market_date

SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    tool_path = (
        PACKAGE_ROOT / "creatures" / "lab-runner" / "tools" / "a_share_report.py"
    )
    tool_text = tool_path.read_text(encoding="utf-8")
    check('"default": "real"' in tool_text, "tool must default to real mode")
    check("build_real_snapshot_report" in tool_text, "real snapshot builder missing")
    check("build_unavailable_real_snapshot" in tool_text, "unavailable report missing")
    check("build_latest_fixture_report()" in tool_text, "fixture mode path missing")
    real_snapshot_text = (
        PACKAGE_ROOT / "a_share_monitor" / "reporting" / "real_snapshot.py"
    ).read_text(encoding="utf-8")
    check(
        "fetch_tencent_universe_quotes" in real_snapshot_text,
        "Tencent batch quote must be the primary quote source",
    )
    tencent_adapter = (
        PACKAGE_ROOT / "a_share_monitor" / "reporting" / "tencent_quote.py"
    )
    check(tencent_adapter.exists(), "Tencent quote adapter missing")

    lab_prompt = PACKAGE_ROOT / "creatures" / "lab-runner" / "prompts" / "system.md"
    lab_text = lab_prompt.read_text(encoding="utf-8")
    check("mode: real" in lab_text, "lab prompt must instruct real mode")
    check("DATA_UNAVAILABLE" in lab_text, "lab prompt must guard data failures")

    data_prompt = PACKAGE_ROOT / "terrariums" / "daily-monitor" / "prompts" / "data.md"
    data_text = data_prompt.read_text(encoding="utf-8")
    check("Default to real-market data" in data_text, "data node must default real")
    check("using fixture data" in data_text, "data node must forbid fixture fallback")

    unavailable = build_unavailable_real_snapshot(
        error="test market data failure",
        requested_trade_date="2026-06-12",
        user_intent="unit test",
    )
    check(unavailable["status"] == "DATA_UNAVAILABLE", "status mismatch")
    check(
        unavailable["data_freshness"]["mode"] == "real",
        "unavailable report must remain real mode",
    )
    check(
        unavailable["data_freshness"]["fallback_to_fixture"] is False,
        "must not silently fall back to fixture",
    )
    acquisition = unavailable["data_acquisition"]
    check(acquisition["quote_count"] == 0, "unavailable quote count must be zero")
    check(
        acquisition["quality_state"] == "unavailable",
        "unavailable quality state mismatch",
    )
    check(
        acquisition["failure_action"] == "return_control_to_root_and_user",
        "failure must return control to root/user",
    )
    check(
        acquisition["retry_policy"]["fixture_fallback"] is False,
        "fixture fallback must be disabled",
    )
    check(
        acquisition["retry_policy"]["http_attempts_per_request"] == 2,
        "HTTP retry policy should fail fast",
    )
    check(
        acquisition["retry_policy"]["fallback_probe_limit"] == 3,
        "fallback probe limit should stay bounded",
    )
    check(acquisition["channels"], "data acquisition channels must be explicit")
    check(resolve_market_date("2026-06-12") == "2026-06-12", "date passthrough")

    return {
        "status": "PASS",
        "default_mode": "real",
        "unavailable_status": unavailable["status"],
        "fallback_to_fixture": unavailable["data_freshness"]["fallback_to_fixture"],
        "failure_action": acquisition["failure_action"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify D4 real-market default.")
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
