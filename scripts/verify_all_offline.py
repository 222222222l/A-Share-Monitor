#!/usr/bin/env python
"""Run the minimal offline validation suite for the package."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent

VALIDATION_MODULES = (
    "scripts.verify_a1_package_skeleton",
    "scripts.verify_b1_market_data_schema",
    "scripts.verify_b2_offline_fixture",
    "scripts.verify_b3_fixture_adapter",
    "scripts.verify_c1_market_state",
    "scripts.verify_c2_sector_strength",
    "scripts.verify_c3_stock_screen",
    "scripts.verify_c0_technical_indicators",
    "scripts.verify_c4_risk_plan",
    "scripts.verify_c_group_technical_screening",
    "scripts.verify_d1_structured_report",
    "scripts.verify_d2_daily_monitor_terrarium",
    "scripts.verify_d3_strategy_critic",
    "scripts.verify_d4_real_market_default",
    "scripts.verify_e2_event_backtest",
    "scripts.verify_e3_paper_trading_log",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all offline validations.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help="Repository root. Defaults to this script's repository.",
    )
    args = parser.parse_args()

    results = []
    for module in VALIDATION_MODULES:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                module,
                "--repo-root",
                str(args.repo_root.resolve()),
            ],
            cwd=PACKAGE_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        results.append(
            {
                "module": module,
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
        )
        if completed.returncode != 0:
            print(
                json.dumps(
                    {"status": "FAIL", "failed_module": module, "results": results},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return completed.returncode

    print(
        json.dumps(
            {
                "status": "PASS",
                "suite": "offline_minimal",
                "module_count": len(results),
                "modules": [item["module"] for item in results],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
