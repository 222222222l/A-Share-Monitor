#!/usr/bin/env python
"""Verify the C4 risk-reward and exit-risk planning stage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.strategy import evaluate_latest_fixture_risk_plan


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent


class StageGuardAdapter(FixtureMarketDataAdapter):
    """Guard that blocks full-dataset loads and records final risk calls."""

    def __init__(self) -> None:
        super().__init__()
        self.fundamental_symbol_calls: list[tuple[str, ...]] = []

    def load(self):  # noqa: ANN201
        raise AssertionError("C4 must not load the full dataset")

    def load_fundamental_risk_events(
        self, symbols, *args, **kwargs
    ):  # noqa: ANN002, ANN003, ANN201
        symbol_tuple = tuple(symbols)
        self.fundamental_symbol_calls.append(symbol_tuple)
        return super().load_fundamental_risk_events(symbol_tuple)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    adapter = StageGuardAdapter()
    report = evaluate_latest_fixture_risk_plan(adapter)
    check(report.trade_date, "trade_date is required")
    check(report.min_risk_reward == 1.5, "default risk-reward threshold mismatch")
    check(report.recommendations, "C4 must produce at least one recommendation")
    check(report.planned_symbols == ("688001.SH",), "fixture planned symbol mismatch")
    check("600001.SH" in report.watchlist_symbols, "watchlist must be preserved")
    check(
        adapter.fundamental_symbol_calls == [("688001.SH",)],
        "fundamental risk must be loaded only for C3 candidates",
    )
    for item in report.recommendations:
        check(item.decision == "buy_ready", "fixture candidate should be buy_ready")
        check(
            item.risk_reward > report.min_risk_reward,
            "buy recommendation below risk-reward threshold",
        )
        check(item.entry_zone[0] < item.entry_zone[1], "entry zone is invalid")
        check(item.technical_exit_price == item.stop_loss, "exit/stop mismatch")
        check(
            item.technical_exit_price < item.entry_zone[0],
            "technical exit must be below entry zone",
        )
        check(item.target_1 > item.entry_zone[1], "target_1 must exceed entry")
        check(item.target_2 > item.target_1, "target_2 must exceed target_1")
        check(0 < item.position_size <= 0.2, "position size outside configured cap")
        check(item.fundamental_exit_trigger, "fundamental trigger is required")
        check(item.ownership_flow_risk, "ownership risk is required")
        check(item.time_exit_rule, "time exit rule is required")
        check(
            item.technical_indicators["atr_14"] > 0,
            "ATR must be present in technical payload",
        )
        check(
            "not an automatic order" in " ".join(item.audit_notes),
            "audit notes must preserve user decision boundary",
        )

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check(
        "`C4`" in blueprint_text and "risk_plan.py" in blueprint_text,
        "blueprint missing C4",
    )

    return {
        "status": "PASS",
        "trade_date": report.trade_date,
        "planned_symbols": list(report.planned_symbols),
        "watchlist_symbols": list(report.watchlist_symbols),
        "recommendation_count": len(report.recommendations),
        "min_risk_reward": report.min_risk_reward,
        "risk_rewards": {
            item.symbol: item.risk_reward for item in report.recommendations
        },
        "candidate_only_final_risk_load": True,
        "watchlist_has_no_buy_plan": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify C4 risk plan.")
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
