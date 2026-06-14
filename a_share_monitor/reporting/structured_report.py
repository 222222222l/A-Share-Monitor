"""Build structured analysis reports from the staged offline strategy chain."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from a_share_monitor.data import FixtureMarketDataAdapter
from a_share_monitor.strategy import RiskPlanConfig
from a_share_monitor.strategy import RiskPlanReport
from a_share_monitor.strategy import evaluate_latest_fixture_risk_plan


def build_latest_fixture_report(
    adapter: FixtureMarketDataAdapter | None = None,
    config: RiskPlanConfig | None = None,
) -> dict[str, Any]:
    """Build the default offline structured analysis report."""
    adapter = adapter or FixtureMarketDataAdapter()
    risk_report = evaluate_latest_fixture_risk_plan(adapter, config)
    return build_structured_report(risk_report)


def build_structured_report(risk_report: RiskPlanReport) -> dict[str, Any]:
    """Convert a C4 risk plan into a portable structured report dict."""
    recommendations = [
        _recommendation_payload(item) for item in risk_report.recommendations
    ]
    report = {
        "schema_version": "a-share-monitor.report.v1",
        "trade_date": risk_report.trade_date,
        "decision_boundary": {
            "real_trading_enabled": False,
            "final_decision_owner": "user",
            "disclaimer": (
                "Research output only. This package does not place real orders "
                "and does not provide personalized financial advice."
            ),
        },
        "selection_summary": {
            "min_risk_reward": risk_report.min_risk_reward,
            "planned_symbols": list(risk_report.planned_symbols),
            "watchlist_symbols": list(risk_report.watchlist_symbols),
            "rejected_symbols": list(risk_report.rejected_symbols),
            "recommendation_count": len(recommendations),
        },
        "recommendations": recommendations,
        "critic_review": {},
    }
    report["critic_review"] = review_structured_report(report)
    return report


def review_structured_report(report: dict[str, Any]) -> dict[str, Any]:
    """Deterministically review a structured report against D3 guardrails."""
    findings = []
    recommendations = report.get("recommendations") or []
    min_risk_reward = float(
        report.get("selection_summary", {}).get("min_risk_reward", 1.5)
    )
    planned_symbols = set(
        report.get("selection_summary", {}).get("planned_symbols", [])
    )
    watchlist_symbols = set(
        report.get("selection_summary", {}).get("watchlist_symbols", [])
    )
    if planned_symbols.intersection(watchlist_symbols):
        findings.append("watchlist_symbol_has_buy_plan")
    if report.get("decision_boundary", {}).get("real_trading_enabled") is not False:
        findings.append("real_trading_boundary_missing")
    for item in recommendations:
        findings.extend(_review_recommendation(item, min_risk_reward))
    status = "pass" if not findings else "revise"
    return {
        "status": status,
        "findings": findings,
        "requirements_checked": [
            "risk_reward_threshold",
            "technical_exit_price",
            "fundamental_exit_trigger",
            "ownership_flow_risk",
            "time_exit_rule",
            "user_decision_boundary",
            "watchlist_excluded_from_buy_plan",
        ],
        "confidence": "high" if status == "pass" else "medium",
    }


def _recommendation_payload(item: Any) -> dict[str, Any]:
    payload = asdict(item)
    payload["entry_zone"] = list(item.entry_zone)
    payload["fundamental_risk"] = list(item.fundamental_risk)
    payload["audit_notes"] = list(item.audit_notes)
    return payload


def _review_recommendation(item: dict[str, Any], min_risk_reward: float) -> list[str]:
    findings = []
    decision = str(item.get("decision", ""))
    symbol = str(item.get("symbol", "unknown"))
    risk_reward = float(item.get("risk_reward") or 0.0)
    if decision in {"buy_ready", "buy_watch"} and risk_reward <= min_risk_reward:
        findings.append(f"{symbol}:risk_reward_below_threshold")
    if decision in {"buy_ready", "buy_watch"}:
        for field in (
            "technical_exit_price",
            "technical_exit_reason",
            "fundamental_exit_trigger",
            "ownership_flow_risk",
            "time_exit_rule",
        ):
            if not item.get(field):
                findings.append(f"{symbol}:missing_{field}")
    entry_zone = item.get("entry_zone") or []
    if len(entry_zone) == 2 and item.get("technical_exit_price") is not None:
        if float(item["technical_exit_price"]) >= float(entry_zone[0]):
            findings.append(f"{symbol}:technical_exit_not_below_entry")
    return findings
