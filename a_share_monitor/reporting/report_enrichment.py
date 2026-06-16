"""Enrich real-market reports with fund flow and sector crowding signals."""

from __future__ import annotations

from typing import Any, Callable

from a_share_monitor.config import get_bool
from a_share_monitor.config import get_float
from a_share_monitor.reporting.fund_flow import fetch_symbol_fund_flows
from a_share_monitor.reporting.sector_crowding import fetch_industry_board_crowding


def fetch_sector_crowding(
    strategy_config: dict[str, Any],
    progress: Callable[[str, dict[str, Any]], None] | None,
    get_json,
) -> dict[str, Any]:
    if not get_bool(strategy_config, "sector_crowding.enabled", True):
        return _empty_sector_crowding("skipped")
    _progress(progress, "sector_crowding_start", {"source": "eastmoney_industry_board"})
    result = fetch_industry_board_crowding(get_json, strategy_config)
    _progress(
        progress,
        "sector_crowding_done",
        {
            "source": result["source"],
            "status": result["status"],
            "board_count": result["board_count"],
            "extreme_count": len(result.get("extreme_crowding") or []),
        },
    )
    return result


def attach_ownership_and_crowding(
    rows: list[dict[str, Any]],
    sector_crowding: dict[str, Any],
    strategy_config: dict[str, Any],
    progress: Callable[[str, dict[str, Any]], None] | None,
    get_json,
) -> dict[str, Any]:
    symbols = [str(row["symbol"]) for row in rows]
    if get_bool(strategy_config, "ownership_flow.enabled", True):
        _progress(
            progress,
            "ownership_flow_start",
            {
                "source": "mixed_order_size_fund_flow",
                "primary_source": "eastmoney_order_size_fund_flow",
                "fallback_source": "akshare_stock_individual_fund_flow",
                "symbols": len(symbols),
            },
        )
        fund_flows, summary = fetch_symbol_fund_flows(
            symbols, get_json, strategy_config
        )
    else:
        fund_flows, summary = {}, _empty_ownership_flow(len(symbols))
    by_industry = sector_crowding.get("by_industry_name") or {}
    for row in rows:
        flow = fund_flows.get(str(row["symbol"]))
        if flow:
            _attach_flow(row, flow, by_industry, strategy_config)
    _progress(
        progress,
        "ownership_flow_done",
        {
            "source": summary["source"],
            "status": summary["status"],
            "usable_records": summary["usable_records"],
            "source_counts": summary.get("source_counts", {}),
        },
    )
    return summary


def demote_extreme_crowding(
    row: dict[str, Any],
    crowding: dict[str, Any],
    strategy_config: dict[str, Any],
) -> None:
    if row.get("status") != "candidate":
        return
    if not get_bool(strategy_config, "sector_crowding.avoid_extreme_crowding", True):
        return
    if crowding.get("crowding_state") != "extreme_crowding":
        return
    threshold = get_float(strategy_config, "sector_crowding.extreme_score", 0.85)
    row["status"] = "watchlist"
    row["decision"] = "watch"
    row["reason"] = "sector_extreme_crowding"
    row.setdefault("unmet_conditions", []).append(
        {
            "code": "sector_crowding_below_extreme",
            "actual": crowding["crowding_score"],
            "operator": "<",
            "threshold": threshold,
            "passed": False,
        }
    )


def public_sector_crowding(sector_crowding: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": sector_crowding.get("source", ""),
        "status": sector_crowding.get("status", "unknown"),
        "board_count": sector_crowding.get("board_count", 0),
        "relative_warming_standard": sector_crowding.get(
            "relative_warming_standard", ""
        ),
        "top_relative_warming": [
            public_crowding_item(item)
            for item in sector_crowding.get("top_relative_warming", [])
        ],
        "extreme_crowding": [
            public_crowding_item(item)
            for item in sector_crowding.get("extreme_crowding", [])
        ],
        "error": sector_crowding.get("error", ""),
    }


def public_crowding_item(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "board_code",
        "industry_name",
        "pct_change",
        "turnover_rate",
        "amount",
        "main_net_inflow",
        "crowding_score",
        "relative_warming_score",
        "crowding_state",
        "relative_warming",
        "leader_name",
        "leader_symbol",
        "leader_pct_change",
    )
    return {key: item.get(key) for key in keys}


def _attach_flow(
    row: dict[str, Any],
    flow: dict[str, Any],
    by_industry: dict[str, Any],
    strategy_config: dict[str, Any],
) -> None:
    row["ownership_flow"] = flow
    row["main_net_inflow"] = flow["main_net_inflow"]
    row["ownership_flow_risk"] = flow["risk_note"]
    row["industry_name"] = flow["industry_name"]
    row["concept_tags"] = flow["concept_tags"]
    crowding = by_industry.get(flow["industry_name"])
    if crowding:
        row["sector_crowding"] = public_crowding_item(crowding)
        demote_extreme_crowding(row, crowding, strategy_config)


def _empty_sector_crowding(status: str) -> dict[str, Any]:
    return {
        "source": "eastmoney_industry_board",
        "status": status,
        "board_count": 0,
        "error": "",
        "top_relative_warming": [],
        "extreme_crowding": [],
        "by_industry_name": {},
    }


def _empty_ownership_flow(symbol_count: int) -> dict[str, Any]:
    return {
        "source": "mixed_order_size_fund_flow",
        "status": "skipped",
        "requested_symbols": symbol_count,
        "usable_records": 0,
        "source_counts": {},
        "error": "",
    }


def _progress(
    callback: Callable[[str, dict[str, Any]], None] | None,
    stage: str,
    payload: dict[str, Any],
) -> None:
    if callback is not None:
        callback(stage, payload)
