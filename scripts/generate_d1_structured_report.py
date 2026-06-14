#!/usr/bin/env python
"""Generate the D1 offline structured analysis report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.reporting import build_latest_fixture_report


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_OUTPUT = PACKAGE_ROOT / "reports" / "d1_structured_report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate D1 structured report.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output JSON path. Defaults to reports/d1_structured_report.json.",
    )
    args = parser.parse_args()

    report = build_latest_fixture_report()
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(output_path),
                "trade_date": report["trade_date"],
                "planned_symbols": report["selection_summary"]["planned_symbols"],
                "critic_status": report["critic_review"]["status"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
