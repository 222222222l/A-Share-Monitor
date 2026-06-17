"""Compact packets for model-stable terrarium handoffs."""

from __future__ import annotations

from typing import Any

PACKET_SCHEMA_VERSION = "a-share-monitor.agent-packet.v1"
MAX_SECTOR_ITEMS = 3


def build_agent_packet(
    report: dict[str, Any],
    *,
    include_user_report: bool = False,
) -> dict[str, Any]:
    """Build the small contract shared by Web UI terrarium nodes.

    The full report can contain raw source summaries and verbose diagnostics.
    Pipeline nodes only need deterministic gate fields, candidate facts, and the
    final package-authored Chinese report. Keeping this packet small reduces
    model-dependent repair loops and token usage.
    """
    diagnostics = report.get("screening_diagnostics") or {}
    buy_ready = [_candidate_packet(item) for item in report.get("recommendations", [])]
    watchlist = [_watchlist_packet(item) for item in diagnostics.get("watchlist", [])]
    if not watchlist:
        watchlist = [_watchlist_packet(item) for item in report.get("watchlist", [])]

    packet = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "status": report.get("status", "UNKNOWN"),
        "trade_date": report.get("trade_date", ""),
        "generated_at": report.get("generated_at", ""),
        "data_freshness": report.get("data_freshness", {}),
        "decision_boundary": report.get("decision_boundary", {}),
        "data_quality": _data_quality_packet(report.get("data_acquisition") or {}),
        "market_context": _market_context_packet(report),
        "sector_context": _sector_context_packet(report.get("sector_crowding") or {}),
        "ownership_flow": _ownership_summary_packet(report.get("ownership_flow") or {}),
        "screening": {
            "recommendation_count": len(buy_ready),
            "watchlist_count": len(watchlist),
            "min_risk_reward": (report.get("selection_summary") or {}).get(
                "min_risk_reward"
            ),
            "buy_ready": buy_ready,
            "watchlist": watchlist,
        },
        "critic_contract": _critic_contract(report, buy_ready, watchlist),
    }
    if include_user_report:
        packet["deterministic_user_report_zh"] = report.get(
            "deterministic_user_report_zh", ""
        )
    return packet


def _data_quality_packet(acquisition: dict[str, Any]) -> dict[str, Any]:
    quality_state = acquisition.get("quality_state", "unknown")
    packet = {
        "quality_state": quality_state,
        "quote_count": acquisition.get("quote_count", 0),
        "minimum_full_market_quotes": acquisition.get("minimum_full_market_quotes", 0),
        "kline_attempt_count": acquisition.get("kline_attempt_count", 0),
        "kline_success_count": acquisition.get("kline_success_count", 0),
        "channels": _channel_packets(acquisition.get("channels", []), quality_state),
        "error": acquisition.get("error", ""),
    }
    if quality_state != "usable":
        packet["retry_policy"] = acquisition.get("retry_policy", {})
        packet["failure_action"] = acquisition.get("failure_action", "")
    return _compact(packet)


def _channel_packets(
    channels: list[dict[str, Any]], quality_state: str
) -> list[dict[str, Any]]:
    packets = [_channel_packet(item) for item in channels]
    if quality_state != "usable":
        return packets
    return [item for item in packets if _channel_has_signal(item)]


def _channel_packet(channel: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "name",
        "status",
        "usable_records",
        "attempted_symbols",
        "successful_symbols",
        "requested_symbols",
        "source_counts",
        "error",
    )
    return {key: channel.get(key) for key in keys if channel.get(key) not in (None, "")}


def _channel_has_signal(channel: dict[str, Any]) -> bool:
    if int(channel.get("usable_records") or 0) > 0:
        return True
    if int(channel.get("successful_symbols") or 0) > 0:
        return True
    if channel.get("source_counts"):
        return True
    status = str(channel.get("status") or "")
    return status not in {"", "unknown", "skipped", "unavailable"}


def _market_context_packet(report: dict[str, Any]) -> dict[str, Any]:
    market = report.get("market") or {}
    market_state = report.get("market_state") or {}
    sector_scope = report.get("sector_scope") or {}
    return _compact(
        {
            "universe_size": market.get("universe_size"),
            "advancing_ratio": market.get("advancing_ratio"),
            "total_amount": market.get("total_amount"),
            "market_regime": market_state.get("market_regime"),
            "buy_permission": market_state.get("buy_permission"),
            "liquidity_state": market_state.get("liquidity_state"),
            "breadth_state": market_state.get("breadth_state"),
            "index_average_pct_change": market_state.get("index_average_pct_change"),
            "positive_index_count": market_state.get("positive_index_count"),
            "sector_scope": {
                "scope": sector_scope.get("scope"),
                "reason": sector_scope.get("reason"),
                "leading_styles": sector_scope.get("leading_styles", []),
            },
        }
    )


def _sector_context_packet(sector_crowding: dict[str, Any]) -> dict[str, Any]:
    return _compact(
        {
            "source": sector_crowding.get("source", ""),
            "status": sector_crowding.get("status", "unknown"),
            "board_count": sector_crowding.get("board_count", 0),
            "relative_warming_standard": sector_crowding.get(
                "relative_warming_standard", ""
            ),
            "top_relative_warming": [
                _sector_item_packet(item)
                for item in (sector_crowding.get("top_relative_warming") or [])[
                    :MAX_SECTOR_ITEMS
                ]
            ],
            "extreme_crowding": [
                _sector_item_packet(item)
                for item in (sector_crowding.get("extreme_crowding") or [])[
                    :MAX_SECTOR_ITEMS
                ]
            ],
            "error": sector_crowding.get("error", ""),
        }
    )


def _sector_item_packet(item: dict[str, Any]) -> dict[str, Any]:
    return _compact(
        {
            "industry_name": item.get("industry_name", ""),
            "pct_change": item.get("pct_change"),
            "relative_warming_score": item.get("relative_warming_score"),
            "crowding_score": item.get("crowding_score"),
            "crowding_state": item.get("crowding_state"),
            "leader_name": item.get("leader_name"),
            "leader_symbol": item.get("leader_symbol"),
        }
    )


def _ownership_summary_packet(summary: dict[str, Any]) -> dict[str, Any]:
    return _compact(
        {
            "source": summary.get("source", ""),
            "status": summary.get("status", "unknown"),
            "requested_symbols": summary.get("requested_symbols", 0),
            "usable_records": summary.get("usable_records", 0),
            "source_counts": summary.get("source_counts", {}),
            "proxy_note": (
                "large orders approximate institutional flow; medium/small orders "
                "approximate retail flow"
            ),
            "error": summary.get("error", ""),
        }
    )


def _candidate_packet(item: dict[str, Any]) -> dict[str, Any]:
    return _compact(
        {
            "symbol": item.get("symbol", ""),
            "name": item.get("name", ""),
            "industry_name": item.get("industry_name", ""),
            "close": item.get("close"),
            "pct_change": item.get("pct_change"),
            "amount": item.get("amount"),
            "entry_zone": item.get("entry_zone"),
            "technical_exit_price": item.get("technical_exit_price"),
            "technical_exit_reason": _short_exit_reason(
                item.get("technical_exit_reason")
            ),
            "target_1": item.get("target_1"),
            "risk_reward": item.get("risk_reward"),
            "fundamental_exit_trigger": _short_fundamental_exit(
                item.get("fundamental_exit_trigger")
            ),
            "time_exit_rule": _short_time_exit(item.get("time_exit_rule")),
            "ownership_flow": _ownership_item_packet(item.get("ownership_flow") or {}),
            "sector_crowding": _sector_item_packet(item.get("sector_crowding") or {}),
        }
    )


def _watchlist_packet(item: dict[str, Any]) -> dict[str, Any]:
    return _compact(
        {
            "symbol": item.get("symbol", ""),
            "name": item.get("name", ""),
            "industry_name": item.get("industry_name", ""),
            "close": item.get("close"),
            "pct_change": item.get("pct_change"),
            "reason": item.get("reason", ""),
            "failed_conditions": _condition_packets(
                item.get("failed_conditions") or item.get("unmet_conditions") or []
            ),
            "ownership_flow": _ownership_item_packet(item.get("ownership_flow") or {}),
            "sector_crowding": _sector_item_packet(item.get("sector_crowding") or {}),
        }
    )


def _ownership_item_packet(flow: dict[str, Any]) -> dict[str, Any]:
    return _compact(
        {
            "source": flow.get("source", ""),
            "counterparty_signal": flow.get("counterparty_signal", "unknown"),
            "main_net_inflow": flow.get("main_net_inflow"),
            "institutional_proxy_net": flow.get("institutional_proxy_net"),
            "retail_proxy_net": flow.get("retail_proxy_net"),
        }
    )


def _condition_packets(conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _compact(
            {
                "code": condition.get("code"),
                "actual": condition.get("actual"),
                "operator": condition.get("operator"),
                "threshold": condition.get("threshold"),
            }
        )
        for condition in conditions
    ]


def _critic_contract(
    report: dict[str, Any],
    buy_ready: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
) -> dict[str, Any]:
    missing = []
    for item in buy_ready:
        for field in (
            "technical_exit_price",
            "target_1",
            "risk_reward",
            "fundamental_exit_trigger",
            "time_exit_rule",
        ):
            if item.get(field) in (None, ""):
                missing.append(f"{item.get('symbol', 'unknown')}:missing_{field}")
    return {
        "packet_complete": not missing,
        "missing_fields": missing,
        "critic_review_status": (report.get("critic_review") or {}).get("status"),
        "no_buy_is_valid": not buy_ready and bool(watchlist),
        "must_preserve_watchlist": True,
    }


def _short_exit_reason(value: Any) -> str:
    if not value:
        return ""
    return "close_below_stop_or_lost_ema20"


def _short_fundamental_exit(value: Any) -> str:
    if not value:
        return ""
    return "material_negative_or_earnings_or_regulatory_risk"


def _short_time_exit(value: Any) -> str:
    if not value:
        return ""
    return "3-5_sessions_no_upside_confirmation_then_watchlist"


def _compact(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", [], {})}
