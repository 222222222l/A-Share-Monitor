"""Build real-market environment context from stable public quote sources."""

from __future__ import annotations

from typing import Any, Callable

from a_share_monitor.config import DEFAULT_STRATEGY_CONFIG
from a_share_monitor.config import get_float
from a_share_monitor.reporting.tencent_quote import fetch_tencent_index_quotes

INDEX_GROUPS = {
    "000001": {
        "group_id": "broad_market",
        "group_name": "Shanghai Composite breadth proxy",
    },
    "399001": {
        "group_id": "broad_market",
        "group_name": "Shenzhen Component breadth proxy",
    },
    "399006": {
        "group_id": "growth_style",
        "group_name": "ChiNext growth proxy",
    },
    "000688": {
        "group_id": "star_innovation",
        "group_name": "STAR innovation proxy",
    },
    "000300": {
        "group_id": "large_cap_core",
        "group_name": "CSI 300 large-cap proxy",
    },
    "399905": {
        "group_id": "mid_small_cap",
        "group_name": "CSI 500 mid/small-cap proxy",
    },
}


def build_market_environment(
    quotes: list[dict[str, Any]],
    trade_date: str,
    *,
    progress: Callable[[str, dict[str, Any]], None] | None = None,
    strategy_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build market-state and sector-scope fields for downstream gates."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    _progress(progress, "market_environment_start", {"source": "tencent_index_quote"})
    index_quotes: list[dict[str, Any]] = []
    index_error = ""
    try:
        index_quotes = fetch_tencent_index_quotes(progress=progress)
    except RuntimeError as exc:
        index_error = str(exc)
        _progress(
            progress,
            "market_environment_source_failed",
            {"source": "tencent_index_quote", "error": index_error},
        )

    breadth = _breadth_summary(quotes)
    indices = _index_summary(index_quotes)
    regime = _classify_market_regime(breadth, indices, strategy_config)
    sector_scope = _build_sector_scope(indices, regime, strategy_config)
    market_state = {
        "trade_date": trade_date,
        "source": "tencent_index_quote+tencent_batch_quote",
        "market_regime": regime["market_regime"],
        "buy_permission": regime["buy_permission"],
        "liquidity_state": regime["liquidity_state"],
        "breadth_state": regime["breadth_state"],
        "rotation_state": regime["rotation_state"],
        "evidence": {
            **breadth,
            "index_average_pct_change": regime["index_average_pct_change"],
            "positive_index_count": regime["positive_index_count"],
            "active_sector_ids": sector_scope["active_sector_ids"],
            "weak_sector_ids": sector_scope["weak_sector_ids"],
        },
        "indices": indices,
    }
    return {
        "market_state": market_state,
        "sector_scope": sector_scope,
        "source_summary": {
            "index_source": "tencent_index_quote",
            "index_count": len(index_quotes),
            "index_error": index_error,
            "sector_source": "tencent_index_style_proxy",
            "sector_source_status": sector_scope["status"],
        },
    }


def unavailable_market_environment(trade_date: str, error: str) -> dict[str, Any]:
    """Return explicit unavailable market environment fields."""
    return {
        "market_state": {
            "trade_date": trade_date,
            "source": "unavailable",
            "market_regime": "unknown",
            "buy_permission": "blocked",
            "liquidity_state": "unknown",
            "breadth_state": "unknown",
            "rotation_state": "unknown",
            "evidence": {"error": error},
            "indices": [],
        },
        "sector_scope": {
            "source": "unavailable",
            "status": "unavailable",
            "scope_type": "none",
            "eligible_sector_ids": [],
            "active_sector_ids": [],
            "weak_sector_ids": [],
            "top_groups": [],
            "note": "market environment data unavailable; return control to root/user",
        },
        "source_summary": {
            "index_source": "tencent_index_quote",
            "index_count": 0,
            "index_error": error,
            "sector_source": "tencent_index_style_proxy",
            "sector_source_status": "unavailable",
        },
    }


def _breadth_summary(quotes: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(quotes)
    advancing = sum(1 for row in quotes if float(row["pct_change"]) > 0)
    declining = sum(1 for row in quotes if float(row["pct_change"]) < 0)
    limit_up = sum(1 for row in quotes if float(row["pct_change"]) >= 9.8)
    limit_down = sum(1 for row in quotes if float(row["pct_change"]) <= -9.8)
    total_amount = sum(float(row["amount"]) for row in quotes)
    return {
        "universe_size": total,
        "advancing_count": advancing,
        "declining_count": declining,
        "advancing_ratio": round(advancing / max(total, 1), 4),
        "declining_ratio": round(declining / max(total, 1), 4),
        "limit_up_count": limit_up,
        "limit_down_count": limit_down,
        "total_amount": round(total_amount, 2),
    }


def _index_summary(index_quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indices = []
    for quote in index_quotes:
        group = INDEX_GROUPS.get(str(quote["symbol"]), {})
        indices.append(
            {
                "symbol": quote["symbol"],
                "name": quote["name"],
                "close": quote["close"],
                "pct_change": quote["pct_change"],
                "amount": quote["amount"],
                "group_id": group.get("group_id", "unknown"),
                "group_name": group.get("group_name", quote["name"]),
            }
        )
    return sorted(indices, key=lambda item: float(item["pct_change"]), reverse=True)


def _classify_market_regime(
    breadth: dict[str, Any],
    indices: list[dict[str, Any]],
    strategy_config: dict[str, Any],
) -> dict[str, Any]:
    index_changes = [float(item["pct_change"]) for item in indices]
    index_average = sum(index_changes) / max(len(index_changes), 1)
    positive_indices = sum(1 for value in index_changes if value > 0)
    advancing_ratio = float(breadth["advancing_ratio"])
    declining_ratio = float(breadth["declining_ratio"])
    limit_down = int(breadth["limit_down_count"])
    limit_up = int(breadth["limit_up_count"])

    liquidity_crisis_declining_ratio = get_float(
        strategy_config, "market_gate.liquidity_crisis_declining_ratio", 0.72
    )
    limit_down_min = get_float(
        strategy_config, "market_gate.liquidity_crisis_limit_down_min", 20
    )
    limit_down_multiplier = get_float(
        strategy_config,
        "market_gate.liquidity_crisis_limit_down_vs_up_multiplier",
        2.0,
    )
    broad_advancing_ratio = get_float(
        strategy_config, "market_gate.broad_risk_on_advancing_ratio", 0.65
    )
    broad_index_change = get_float(
        strategy_config, "market_gate.broad_risk_on_index_average_pct_change", 0.3
    )
    rotation_advancing_ratio = get_float(
        strategy_config, "market_gate.rotation_advancing_ratio", 0.5
    )
    policy_support_index_change = get_float(
        strategy_config, "market_gate.policy_support_index_average_pct_change", 0.0
    )
    policy_support_max_advancing_ratio = get_float(
        strategy_config, "market_gate.policy_support_max_advancing_ratio", 0.45
    )

    if declining_ratio >= liquidity_crisis_declining_ratio and limit_down > max(
        limit_up * limit_down_multiplier, limit_down_min
    ):
        state = "liquidity_crisis"
        permission = "blocked"
    elif (
        advancing_ratio >= broad_advancing_ratio and index_average >= broad_index_change
    ):
        state = "broad_risk_on"
        permission = "selective"
    elif advancing_ratio >= rotation_advancing_ratio and positive_indices >= max(
        len(indices) // 2, 1
    ):
        state = "rotation_opportunity"
        permission = "rotation_only"
    elif (
        index_average > policy_support_index_change
        and advancing_ratio < policy_support_max_advancing_ratio
    ):
        state = "policy_support_rebound"
        permission = "rebound_watch"
    else:
        state = "mixed_chop"
        permission = "rotation_only" if indices else "blocked"

    return {
        "market_regime": state,
        "buy_permission": permission,
        "liquidity_state": _liquidity_state(
            float(breadth["total_amount"]), strategy_config
        ),
        "breadth_state": _breadth_state(advancing_ratio, strategy_config),
        "rotation_state": "active" if permission == "rotation_only" else state,
        "index_average_pct_change": round(index_average, 4),
        "positive_index_count": positive_indices,
    }


def _build_sector_scope(
    indices: list[dict[str, Any]],
    regime: dict[str, Any],
    strategy_config: dict[str, Any],
) -> dict[str, Any]:
    top_groups = _group_index_styles(indices)
    active_style_change = get_float(
        strategy_config, "market_gate.active_style_pct_change", 0.3
    )
    weak_style_change = get_float(
        strategy_config, "market_gate.weak_style_pct_change", -0.3
    )
    active = [
        item["sector_id"]
        for item in top_groups
        if float(item["avg_pct_change"]) >= active_style_change
    ]
    weak = [
        item["sector_id"]
        for item in top_groups
        if float(item["avg_pct_change"]) <= weak_style_change
    ]
    if not active and top_groups and regime["buy_permission"] != "blocked":
        active = [top_groups[0]["sector_id"]]
    eligible = [] if regime["buy_permission"] == "blocked" else active
    status = "proxy_usable" if indices else "unavailable"
    return {
        "source": "tencent_index_style_proxy",
        "status": status,
        "scope_type": "index_style_proxy",
        "eligible_sector_ids": eligible,
        "active_sector_ids": active,
        "weak_sector_ids": weak,
        "top_groups": top_groups[:5],
        "note": (
            "Industry-board source is not a hard dependency. This scope uses "
            "major index/style proxies for the market gate; individual entries "
            "still require right-side stock-level confirmation."
        ),
    }


def _group_index_styles(indices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in indices:
        grouped.setdefault(str(item["group_id"]), []).append(item)
    result = []
    for group_id, rows in grouped.items():
        avg_change = sum(float(item["pct_change"]) for item in rows) / len(rows)
        result.append(
            {
                "sector_id": group_id,
                "sector_name": str(rows[0]["group_name"]),
                "avg_pct_change": round(avg_change, 4),
                "constituent_indices": [str(item["symbol"]) for item in rows],
            }
        )
    return sorted(result, key=lambda item: item["avg_pct_change"], reverse=True)


def _liquidity_state(total_amount: float, strategy_config: dict[str, Any]) -> str:
    high_liquidity = get_float(
        strategy_config, "market_gate.high_liquidity_amount", 1_500_000_000_000
    )
    normal_liquidity = get_float(
        strategy_config, "market_gate.normal_liquidity_amount", 800_000_000_000
    )
    if total_amount >= high_liquidity:
        return "high_liquidity"
    if total_amount >= normal_liquidity:
        return "normal_liquidity"
    if total_amount > 0:
        return "low_liquidity"
    return "unknown"


def _breadth_state(advancing_ratio: float, strategy_config: dict[str, Any]) -> str:
    broad_positive = get_float(
        strategy_config, "market_gate.breadth_broad_positive_ratio", 0.65
    )
    positive_rotation = get_float(
        strategy_config, "market_gate.breadth_positive_rotation_ratio", 0.5
    )
    mixed = get_float(strategy_config, "market_gate.breadth_mixed_ratio", 0.35)
    if advancing_ratio >= broad_positive:
        return "broad_positive"
    if advancing_ratio >= positive_rotation:
        return "positive_rotation"
    if advancing_ratio >= mixed:
        return "mixed"
    return "broad_negative"


def _progress(
    callback: Callable[[str, dict[str, Any]], None] | None,
    stage: str,
    payload: dict[str, Any],
) -> None:
    if callback is not None:
        callback(stage, payload)
