#!/usr/bin/env python
"""Run the compact offline validation suite for the package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from a_share_monitor.backtest import build_paper_trade_log
from a_share_monitor.config import load_strategy_config
from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.data import load_fixture_dataset
from a_share_monitor.reporting import build_agent_packet
from a_share_monitor.reporting import build_latest_fixture_report
from a_share_monitor.reporting import build_unavailable_real_snapshot
from a_share_monitor.strategy import evaluate_latest_fixture_market_state
from a_share_monitor.strategy import evaluate_latest_fixture_risk_plan
from a_share_monitor.strategy import evaluate_latest_fixture_sector_strength
from a_share_monitor.strategy import evaluate_latest_fixture_stock_screen
from a_share_monitor.strategy import evaluate_latest_fixture_technical_indicators

SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run compact offline validation.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help="Repository root. Defaults to this script's repository.",
    )
    args = parser.parse_args()
    result = verify(args.repo_root.resolve())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def verify(repo_root: Path) -> dict[str, Any]:
    manifest = yaml.safe_load((PACKAGE_ROOT / "kohaku.yaml").read_text("utf-8"))
    check(manifest["name"] == "a-share-monitor", "manifest name mismatch")
    check(manifest["terrariums"][0]["name"] == "daily-monitor", "terrarium missing")
    _verify_daily_monitor_wiring()

    config = load_strategy_config(PACKAGE_ROOT / "config" / "strategy.yaml")
    check(config["gm"]["enabled"] is True, "GM source should be enabled")
    check(config["gm"]["prefer_for_quotes"] is True, "GM quotes should be preferred")
    check(
        config["tonghuashun"]["prefer_for_ownership_flow"] is True,
        "10jqka fund-flow fallback should be enabled",
    )
    check(
        config["data_quality"]["disable_system_proxy"] is True,
        "public data should bypass system proxy by default",
    )

    dataset = load_fixture_dataset()
    check(len(dataset.securities) >= 6, "fixture securities are missing")
    check(len(dataset.daily_bars) >= 60, "fixture daily bars are missing")
    check(dataset.ownership_flow_signals, "fixture ownership signals are missing")

    adapter = FixtureMarketDataAdapter()
    market = evaluate_latest_fixture_market_state(adapter)
    sector = evaluate_latest_fixture_sector_strength(adapter)
    technical = evaluate_latest_fixture_technical_indicators(adapter)
    screen = evaluate_latest_fixture_stock_screen(adapter)
    risk = evaluate_latest_fixture_risk_plan(adapter)
    check(market.market_state, "market state missing")
    check(sector.scores, "sector scores missing")
    check(technical.snapshots, "technical indicators missing")
    check(screen.signals, "stock screen signals missing")
    check(risk.watchlist_symbols, "risk plan watchlist missing")

    report = build_latest_fixture_report(adapter)
    check(report["schema_version"] == "a-share-monitor.report.v1", "report schema")
    check(report["critic_review"]["status"] in {"pass", "revise"}, "critic status")
    packet = build_agent_packet(report)
    check(
        packet["schema_version"] == "a-share-monitor.agent-packet.v1",
        "agent packet schema mismatch",
    )
    check(
        "deterministic_user_report_zh" not in packet,
        "default agent packet must omit verbose user report",
    )
    paper_log = build_paper_trade_log(report)
    check(paper_log["real_trading_enabled"] is False, "paper trading boundary")

    unavailable = build_unavailable_real_snapshot(
        error="test market data failure",
        requested_trade_date="2026-06-12",
        user_intent="offline validation",
    )
    check(unavailable["status"] == "DATA_UNAVAILABLE", "unavailable status")
    check(
        unavailable["data_freshness"]["fallback_to_fixture"] is False,
        "real mode must not fall back to fixtures",
    )
    acquisition = unavailable["data_acquisition"]
    check(
        acquisition["failure_action"] == "return_control_to_root_and_user",
        "data failures must return control",
    )
    unavailable_packet = build_agent_packet(unavailable)
    check(
        "deterministic_user_report_zh" not in unavailable_packet,
        "unavailable packet should stay compact by default",
    )
    unavailable_verbose_packet = build_agent_packet(
        unavailable, include_user_report=True
    )
    check(
        "deterministic_user_report_zh" in unavailable_verbose_packet,
        "include_user_report should expose deterministic user report on demand",
    )

    tool_text = (
        PACKAGE_ROOT / "creatures" / "lab-runner" / "tools" / "a_share_report.py"
    ).read_text("utf-8")
    check('"default": "real"' in tool_text, "tool must default to real mode")
    check("build_agent_packet" in tool_text, "tool must use compact agent packet")
    real_snapshot_text = (
        PACKAGE_ROOT / "a_share_monitor" / "reporting" / "real_snapshot.py"
    ).read_text("utf-8")
    check("fetch_gm_universe_quotes" in real_snapshot_text, "GM quote hook missing")
    check(
        "fetch_tencent_universe_quotes" in real_snapshot_text,
        "Tencent fallback missing",
    )
    fund_flow_text = (
        PACKAGE_ROOT / "a_share_monitor" / "reporting" / "fund_flow.py"
    ).read_text("utf-8")
    check(
        "fetch_ths_symbol_fund_flows" in fund_flow_text, "10jqka fund-flow hook missing"
    )

    return {
        "status": "PASS",
        "suite": "compact_offline",
        "repo_root": str(repo_root),
        "fixture": {
            "securities": len(dataset.securities),
            "daily_bars": len(dataset.daily_bars),
            "ownership_flow_signals": len(dataset.ownership_flow_signals),
        },
        "strategy": {
            "market_state": market.market_state,
            "sector_scores": len(sector.scores),
            "screen_signals": len(screen.signals),
            "risk_recommendations": len(risk.recommendations),
        },
        "real_mode_boundary": unavailable["status"],
    }


def _verify_daily_monitor_wiring() -> None:
    config_path = PACKAGE_ROOT / "terrariums" / "daily-monitor" / "terrarium.yaml"
    config = yaml.safe_load(config_path.read_text("utf-8"))
    creatures = config["terrarium"]["creatures"]
    by_name = {creature["name"]: creature for creature in creatures}

    expected_first_targets = {
        "data": "regime",
        "regime": "screen",
        "screen": "risk",
        "risk": "recommendation",
        "recommendation": "critic",
        "critic": "root",
    }
    for name, target in expected_first_targets.items():
        wiring = by_name[name].get("output_wiring", [])
        check(wiring, f"{name} output_wiring missing")
        first = wiring[0] if isinstance(wiring[0], dict) else {"to": wiring[0]}
        check(first.get("to") == target, f"{name} must route first to {target}")

    for name in ("data", "regime", "screen", "risk", "recommendation"):
        wiring = by_name[name].get("output_wiring", [])
        root_edges = [
            edge
            for edge in wiring
            if isinstance(edge, dict) and edge.get("to") == "root"
        ]
        check(root_edges, f"{name} must emit a root status ping")
        check(
            all(edge.get("with_content") is False for edge in root_edges),
            f"{name} root edge must be metadata-only",
        )

    root_prompt = (
        PACKAGE_ROOT / "terrariums" / "daily-monitor" / "prompts" / "root.md"
    ).read_text("utf-8")
    forbidden = ("Forward the packet", "Forward the packet once per stage")
    check(
        not any(text in root_prompt for text in forbidden),
        "root prompt must not broker packets",
    )


if __name__ == "__main__":
    raise SystemExit(main())
