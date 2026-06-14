"""Paper-trading log serialization for recommendation reports."""

from __future__ import annotations

from typing import Any


def build_paper_trade_log(report: dict[str, Any]) -> dict[str, Any]:
    """Build an auditable paper-trading log from a structured report."""
    entries = []
    for item in report.get("recommendations") or []:
        entries.append(
            {
                "signal_id": f"{report['trade_date']}:{item['symbol']}",
                "symbol": item["symbol"],
                "name": item["name"],
                "trade_date": report["trade_date"],
                "decision": item["decision"],
                "planned_order": {
                    "side": "buy",
                    "order_type": "paper_limit",
                    "entry_zone": item["entry_zone"],
                    "position_fraction": item["position_size"],
                    "real_order_enabled": False,
                },
                "fill_assumption": {
                    "status": "not_submitted",
                    "slippage_bps": 5,
                    "commission_bps": 3,
                    "t_plus_one": True,
                },
                "risk_controls": {
                    "technical_exit_price": item["technical_exit_price"],
                    "technical_exit_reason": item["technical_exit_reason"],
                    "time_exit_rule": item["time_exit_rule"],
                    "fundamental_exit_trigger": item["fundamental_exit_trigger"],
                    "ownership_flow_risk": item["ownership_flow_risk"],
                },
                "position": {
                    "state": "planned",
                    "quantity": 0,
                    "average_cost": 0.0,
                    "market_value": 0.0,
                },
                "exit_review": {
                    "status": "not_started",
                    "exit_reason": "",
                    "realized_return": 0.0,
                },
                "audit": {
                    "final_decision_owner": "user",
                    "source_schema": report["schema_version"],
                    "critic_status": report["critic_review"]["status"],
                },
            }
        )
    return {
        "schema_version": "a-share-monitor.paper-log.v1",
        "trade_date": report["trade_date"],
        "real_trading_enabled": False,
        "entries": entries,
    }
