"""Industry-board relative warmth and crowding risk from public board quotes."""

from __future__ import annotations

from typing import Any

from a_share_monitor.config import DEFAULT_STRATEGY_CONFIG
from a_share_monitor.config import get_float
from a_share_monitor.config import get_int

EASTMONEY_UT = "bd1d9ddb04089700cf9c27f6f7426281"
BOARD_FIELDS = "f12,f14,f2,f3,f5,f6,f8,f62,f128,f136,f140"


def fetch_industry_board_crowding(
    get_json,
    strategy_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch industry board quotes and calculate relative warmth/crowding."""
    strategy_config = strategy_config or DEFAULT_STRATEGY_CONFIG
    page_size = get_int(strategy_config, "sector_crowding.page_size", 100)
    max_pages = get_int(strategy_config, "sector_crowding.max_pages", 6)
    rows: list[dict[str, Any]] = []
    last_error = ""
    try:
        first = get_json(_board_url(1, page_size), strategy_config=strategy_config)
        total = int(first.get("data", {}).get("total") or 0)
        rows.extend(first.get("data", {}).get("diff") or [])
        for page in range(2, min((total // page_size) + 2, max_pages + 1)):
            payload = get_json(
                _board_url(page, page_size), strategy_config=strategy_config
            )
            rows.extend(payload.get("data", {}).get("diff") or [])
            if len(rows) >= total:
                break
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        last_error = str(exc)
    boards = [_normalize_board(row) for row in rows]
    boards = [row for row in boards if row is not None]
    scored = _score_boards(boards, strategy_config)
    by_name = {row["industry_name"]: row for row in scored}
    return {
        "source": "eastmoney_industry_board",
        "status": "usable" if scored else "unavailable",
        "board_count": len(scored),
        "error": last_error,
        "relative_warming_standard": (
            "relative percentile of industry boards using pct_change, turnover, "
            "amount, and main net inflow"
        ),
        "top_relative_warming": scored[
            : get_int(strategy_config, "sector_crowding.top_n", 20)
        ],
        "extreme_crowding": [
            row for row in scored if row["crowding_state"] == "extreme_crowding"
        ][: get_int(strategy_config, "sector_crowding.top_n", 20)],
        "by_industry_name": by_name,
    }


def _score_boards(
    boards: list[dict[str, Any]], strategy_config: dict[str, Any]
) -> list[dict[str, Any]]:
    pct_values = [row["pct_change"] for row in boards]
    turnover_values = [row["turnover_rate"] for row in boards]
    amount_values = [row["amount"] for row in boards]
    inflow_values = [row["main_net_inflow"] for row in boards]
    high_threshold = get_float(strategy_config, "sector_crowding.high_score", 0.75)
    extreme_threshold = get_float(
        strategy_config, "sector_crowding.extreme_score", 0.85
    )
    relative_warming_threshold = get_float(
        strategy_config, "sector_crowding.relative_warming_score", 0.55
    )
    for row in boards:
        pct_rank = _percentile(row["pct_change"], pct_values)
        turnover_rank = _percentile(row["turnover_rate"], turnover_values)
        amount_rank = _percentile(row["amount"], amount_values)
        inflow_rank = _percentile(row["main_net_inflow"], inflow_values)
        crowding_score = (
            turnover_rank * 0.35
            + pct_rank * 0.25
            + amount_rank * 0.25
            + inflow_rank * 0.15
        )
        warmth_score = pct_rank * 0.45 + amount_rank * 0.30 + inflow_rank * 0.25
        row.update(
            {
                "pct_change_percentile": round(pct_rank, 4),
                "turnover_percentile": round(turnover_rank, 4),
                "amount_percentile": round(amount_rank, 4),
                "main_net_inflow_percentile": round(inflow_rank, 4),
                "crowding_score": round(crowding_score, 4),
                "relative_warming_score": round(warmth_score, 4),
                "crowding_state": _crowding_state(
                    crowding_score, high_threshold, extreme_threshold
                ),
                "relative_warming": warmth_score >= relative_warming_threshold,
            }
        )
    return sorted(
        boards,
        key=lambda item: (item["relative_warming_score"], item["crowding_score"]),
        reverse=True,
    )


def _crowding_state(
    score: float, high_threshold: float, extreme_threshold: float
) -> str:
    if score >= extreme_threshold:
        return "extreme_crowding"
    if score >= high_threshold:
        return "high_crowding"
    return "normal"


def _percentile(value: float, values: list[float]) -> float:
    if not values:
        return 0.0
    lower_or_equal = sum(1 for item in values if item <= value)
    return lower_or_equal / len(values)


def _board_url(page: int, page_size: int) -> str:
    return (
        "https://push2.eastmoney.com/api/qt/clist/get?"
        f"pn={page}&pz={page_size}&po=1&np=1&ut={EASTMONEY_UT}"
        f"&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields={BOARD_FIELDS}"
    )


def _normalize_board(row: dict[str, Any]) -> dict[str, Any] | None:
    name = str(row.get("f14") or "")
    if not name:
        return None
    return {
        "board_code": str(row.get("f12") or ""),
        "industry_name": name,
        "close": _to_float(row.get("f2")),
        "pct_change": _to_float(row.get("f3")),
        "volume": _to_float(row.get("f5")),
        "amount": _to_float(row.get("f6")),
        "turnover_rate": _to_float(row.get("f8")),
        "main_net_inflow": _to_float(row.get("f62")),
        "leader_name": str(row.get("f128") or ""),
        "leader_symbol": str(row.get("f140") or ""),
        "leader_pct_change": _to_float(row.get("f136")),
    }


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None, "--"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
