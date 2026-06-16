#!/usr/bin/env python
"""Verify that Web UI reports default to real-market mode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from a_share_monitor.config import load_strategy_config
from a_share_monitor.reporting import build_agent_packet
from a_share_monitor.reporting import build_unavailable_real_snapshot
from a_share_monitor.reporting import resolve_market_date
from a_share_monitor.reporting.akshare_fund_flow import (
    normalize_akshare_individual_fund_flow,
)
from a_share_monitor.reporting.deterministic_output import attach_deterministic_outputs
from a_share_monitor.reporting.fund_flow import normalize_fund_flow
from a_share_monitor.reporting.real_screening import technical_signal
from a_share_monitor.reporting.report_enrichment import demote_extreme_crowding
from a_share_monitor.reporting.sector_crowding import fetch_industry_board_crowding

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
    check(
        '"default": "agent_packet"' in tool_text,
        "tool must default to compact agent packet output",
    )
    check("build_agent_packet" in tool_text, "compact agent packet builder missing")
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
    check(
        "build_market_environment" in real_snapshot_text,
        "real reports must build explicit market environment fields",
    )
    check(
        "load_strategy_config" in real_snapshot_text,
        "real reports must load user strategy configuration",
    )
    tencent_adapter = (
        PACKAGE_ROOT / "a_share_monitor" / "reporting" / "tencent_quote.py"
    )
    check(tencent_adapter.exists(), "Tencent quote adapter missing")
    environment_adapter = (
        PACKAGE_ROOT / "a_share_monitor" / "reporting" / "market_environment.py"
    )
    check(environment_adapter.exists(), "market environment adapter missing")
    environment_text = environment_adapter.read_text(encoding="utf-8")
    check(
        "fetch_tencent_index_quotes" in environment_text,
        "market environment must use Tencent index quotes",
    )

    lab_prompt = PACKAGE_ROOT / "creatures" / "lab-runner" / "prompts" / "system.md"
    lab_text = lab_prompt.read_text(encoding="utf-8")
    check("mode: real" in lab_text, "lab prompt must instruct real mode")
    check("DATA_UNAVAILABLE" in lab_text, "lab prompt must guard data failures")

    data_prompt = PACKAGE_ROOT / "terrariums" / "daily-monitor" / "prompts" / "data.md"
    data_text = data_prompt.read_text(encoding="utf-8")
    check("Default to real-market data" in data_text, "data node must default real")
    check("using fixture data" in data_text, "data node must forbid fixture fallback")
    check(
        "final response must be only the exact JSON object" in data_text,
        "data node must forward raw compact JSON instead of summaries",
    )
    check(
        "Do not call `send_channel`" in data_text,
        "data node must rely on output wiring instead of short manual channel sends",
    )
    check(
        "screening.watchlist" in data_text,
        "data node must forward deterministic watchlist diagnostics",
    )
    check("ownership_flow" in data_text, "data node must forward ownership flow")
    check("sector_context" in data_text, "data node must forward sector context")

    root_prompt = PACKAGE_ROOT / "terrariums" / "daily-monitor" / "prompts" / "root.md"
    root_text = root_prompt.read_text(encoding="utf-8")
    check(
        "data_handoff_contract_failed" in root_text,
        "root must report malformed data handoffs instead of asking the user for fields",
    )

    unavailable = build_unavailable_real_snapshot(
        error="test market data failure",
        requested_trade_date="2026-06-12",
        user_intent="unit test",
    )
    strategy_config = load_strategy_config()
    check(
        strategy_config["risk_preference"]["min_risk_reward"] == 1.5,
        "default strategy config risk-reward mismatch",
    )
    check(
        strategy_config["data_quality"]["disable_system_proxy"] is True,
        "market data requests must bypass system VPN/proxy by default",
    )
    check(
        strategy_config["ownership_flow"]["akshare_enabled"] is True,
        "AkShare fund-flow fallback must be enabled by default",
    )
    check(unavailable["status"] == "DATA_UNAVAILABLE", "status mismatch")
    check(unavailable["strategy_config"]["profile"], "strategy profile missing")
    check(
        "deterministic_user_report_zh" in unavailable,
        "unavailable report missing deterministic user report",
    )
    unavailable_packet = build_agent_packet(unavailable)
    check(
        unavailable_packet["schema_version"] == "a-share-monitor.agent-packet.v1",
        "agent packet schema mismatch",
    )
    check(
        unavailable_packet["data_quality"]["quality_state"] == "unavailable",
        "agent packet must expose unavailable data quality",
    )
    check(
        unavailable["data_freshness"]["mode"] == "real",
        "unavailable report must remain real mode",
    )
    check(
        unavailable["data_freshness"]["fallback_to_fixture"] is False,
        "must not silently fall back to fixture",
    )
    acquisition = unavailable["data_acquisition"]
    check(unavailable["market_state"], "unavailable report must include market_state")
    check(unavailable["sector_scope"], "unavailable report must include sector_scope")
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
    watch_item = _sample_watchlist_signal(strategy_config)
    check(watch_item["status"] == "watchlist", "sample must produce watchlist")
    check(watch_item["unmet_conditions"], "watchlist must expose unmet conditions")
    sample_report = {
        "status": "PASS",
        "trade_date": "2026-06-12",
        "data_freshness": {"mode": "real"},
        "market": {"universe_size": 1, "advancing_ratio": 0.0, "total_amount": 1},
        "market_state": {"market_regime": "mixed_chop", "buy_permission": "selective"},
        "recommendations": [],
        "watchlist": [watch_item],
    }
    attach_deterministic_outputs(sample_report)
    sample_packet = build_agent_packet(sample_report)
    check(
        sample_report["screening_diagnostics"]["watchlist"][0]["failed_condition_text"],
        "deterministic diagnostics must render failed condition text",
    )
    check(
        sample_packet["screening"]["watchlist"][0]["failed_condition_text"],
        "agent packet must keep complete watchlist condition text",
    )
    flow = _sample_fund_flow(strategy_config)
    check(
        flow["counterparty_signal"] == "retail_crowding_institution_exit_risk",
        "fund-flow proxy must detect institution-exit retail-crowding risk",
    )
    akshare_flow = _sample_akshare_fund_flow(strategy_config)
    check(
        akshare_flow["source"] == "akshare_stock_individual_fund_flow",
        "AkShare fund-flow adapter source mismatch",
    )
    check(
        akshare_flow["counterparty_signal"]
        == "retail_exit_institution_accumulation_opportunity",
        "AkShare fund-flow adapter must map order-size fields",
    )
    crowding = _sample_sector_crowding(strategy_config)
    check(crowding["status"] == "usable", "sector crowding sample must be usable")
    check(
        crowding["extreme_crowding"],
        "sector crowding must identify extreme crowded boards",
    )
    candidate = {"status": "candidate", "unmet_conditions": []}
    demote_extreme_crowding(candidate, crowding["extreme_crowding"][0], strategy_config)
    check(
        candidate["status"] == "watchlist",
        "extreme crowding must demote candidates to watchlist",
    )
    enriched_report = _sample_enriched_report(strategy_config)
    enriched_packet = build_agent_packet(enriched_report)
    first_candidate = enriched_packet["screening"]["buy_ready"][0]
    check(first_candidate["industry_name"], "candidate packet missing industry")
    check(
        first_candidate["ownership_flow"]["counterparty_signal"],
        "candidate packet missing ownership-flow signal",
    )
    check(
        first_candidate["sector_crowding"]["crowding_state"],
        "candidate packet missing sector crowding state",
    )

    return {
        "status": "PASS",
        "default_mode": "real",
        "unavailable_status": unavailable["status"],
        "fallback_to_fixture": unavailable["data_freshness"]["fallback_to_fixture"],
        "failure_action": acquisition["failure_action"],
    }


def _sample_watchlist_signal(strategy_config: dict) -> dict:
    rows = []
    for index in range(60):
        close = 100.0 if index < 59 else 99.0
        rows.append(
            {
                "date": f"2026-04-{(index % 28) + 1:02d}",
                "open": 100.0,
                "close": close,
                "high": 101.0,
                "low": 98.0,
                "volume": 1_000_000,
                "amount": 150_000_000,
                "pct_change": -1.0,
            }
        )
    quote = {
        "symbol": "600001",
        "name": "Sample",
        "close": 99.0,
        "pct_change": -1.0,
        "amount": 150_000_000,
        "main_net_inflow": 0.0,
    }
    return technical_signal(quote, rows, strategy_config)


def _sample_fund_flow(strategy_config: dict) -> dict:
    return normalize_fund_flow(
        {
            "f12": "600001",
            "f14": "Sample",
            "f62": -20_000_000,
            "f184": -2.0,
            "f66": -15_000_000,
            "f69": -1.5,
            "f72": -5_000_000,
            "f75": -0.5,
            "f78": 12_000_000,
            "f81": 1.2,
            "f84": 3_000_000,
            "f87": 0.3,
            "f100": "通信设备",
            "f103": "CPO概念,通信技术",
        },
        strategy_config,
    )


def _sample_akshare_fund_flow(strategy_config: dict) -> dict:
    return normalize_akshare_individual_fund_flow(
        {
            "日期": "2026-06-12",
            "收盘价": 10.0,
            "涨跌幅": 1.0,
            "主力净流入-净额": 18_000_000,
            "主力净流入-净占比": 3.0,
            "超大单净流入-净额": 12_000_000,
            "超大单净流入-净占比": 2.0,
            "大单净流入-净额": 8_000_000,
            "大单净流入-净占比": 1.0,
            "中单净流入-净额": -3_000_000,
            "中单净流入-净占比": -0.5,
            "小单净流入-净额": -4_000_000,
            "小单净流入-净占比": -0.6,
        },
        "600001",
        strategy_config,
    )


def _sample_sector_crowding(strategy_config: dict) -> dict:
    rows = [
        {
            "f12": "BK1",
            "f14": "通信设备",
            "f2": 100,
            "f3": 8.0,
            "f5": 10_000,
            "f6": 80_000_000_000,
            "f8": 12.0,
            "f62": 3_000_000_000,
            "f128": "Leader",
            "f136": 10.0,
            "f140": "600001",
        },
        {
            "f12": "BK2",
            "f14": "低位回暖",
            "f2": 100,
            "f3": 1.5,
            "f5": 5_000,
            "f6": 20_000_000_000,
            "f8": 3.0,
            "f62": 200_000_000,
            "f128": "Warm",
            "f136": 3.0,
            "f140": "600002",
        },
        {
            "f12": "BK3",
            "f14": "弱势行业",
            "f2": 100,
            "f3": -1.0,
            "f5": 1_000,
            "f6": 3_000_000_000,
            "f8": 0.8,
            "f62": -100_000_000,
            "f128": "Weak",
            "f136": -2.0,
            "f140": "600003",
        },
    ]

    def fake_get_json(url: str, **_: object) -> dict:  # noqa: ARG001
        return {"data": {"total": len(rows), "diff": rows}}

    return fetch_industry_board_crowding(fake_get_json, strategy_config)


def _sample_enriched_report(strategy_config: dict) -> dict:  # noqa: ARG001
    report = {
        "status": "PASS",
        "trade_date": "2026-06-12",
        "generated_at": "2026-06-12T16:00:00+08:00",
        "data_freshness": {"mode": "real", "fallback_to_fixture": False},
        "data_acquisition": {
            "quality_state": "usable",
            "quote_count": 5280,
            "minimum_full_market_quotes": 500,
            "kline_attempt_count": 12,
            "kline_success_count": 12,
            "channels": [],
        },
        "market": {
            "universe_size": 5280,
            "advancing_ratio": 0.5,
            "total_amount": 3_050_000_000_000,
        },
        "market_state": {
            "market_regime": "rotation_opportunity",
            "buy_permission": "rotation_only",
        },
        "sector_scope": {"scope": "rotation"},
        "sector_crowding": {
            "source": "eastmoney_industry_board",
            "status": "usable",
            "board_count": 496,
            "relative_warming_standard": "cross-sectional percentile",
            "top_relative_warming": [],
            "extreme_crowding": [],
        },
        "ownership_flow": {
            "source": "eastmoney_order_size_fund_flow",
            "status": "usable",
            "requested_symbols": 1,
            "usable_records": 1,
        },
        "selection_summary": {"min_risk_reward": 1.5},
        "recommendations": [
            {
                "symbol": "300476",
                "name": "Sample Tech",
                "industry_name": "通信设备",
                "concept_tags": ["CPO概念"],
                "close": 350.55,
                "entry_zone": [350.55, 360.41],
                "technical_exit_price": 336.12,
                "technical_exit_reason": "break stop or EMA20",
                "target_1": 402.6,
                "risk_reward": 1.74,
                "fundamental_exit_trigger": "earnings warning",
                "ownership_flow_risk": "order-size proxy available",
                "time_exit_rule": "exit if target not reached in 5 sessions",
                "ownership_flow": {
                    "source": "eastmoney_order_size_fund_flow",
                    "trade_date": "2026-06-12",
                    "counterparty_signal": "institutional_accumulation",
                    "institutional_proxy_net": 20_000_000,
                    "retail_proxy_net": -5_000_000,
                    "risk_note": "institutional proxy inflow",
                },
                "sector_crowding": {
                    "industry_name": "通信设备",
                    "crowding_state": "normal",
                    "crowding_score": 0.62,
                    "relative_warming_score": 0.71,
                    "leader_name": "Leader",
                },
            }
        ],
        "watchlist": [],
    }
    attach_deterministic_outputs(report)
    return report


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
