"""Deterministic user-facing summaries for model-stable Web UI output."""

from __future__ import annotations

from typing import Any

CONDITION_LABELS = {
    "close_above_trend_ema": "收盘价高于趋势均线",
    "trend_ema_aligned_with_long_ema": "趋势均线不弱于长期均线",
    "close_above_fast_ema": "收盘价收复短期快线",
    "close_above_mid_ema": "收盘价收复中期均线",
    "risk_reward_above_minimum": "盈亏比高于最低要求",
    "near_trend_ema": "入场价格靠近趋势均线",
    "sector_crowding_below_extreme": "板块拥挤度低于极端拥挤阈值",
}


def attach_deterministic_outputs(report: dict[str, Any]) -> None:
    """Attach diagnostics and a Chinese summary that models should not rewrite."""
    diagnostics = build_screening_diagnostics(report)
    report["screening_diagnostics"] = diagnostics
    report["deterministic_user_report_zh"] = build_user_report_zh(report, diagnostics)


def build_screening_diagnostics(report: dict[str, Any]) -> dict[str, Any]:
    watchlist = [_watchlist_item(item) for item in report.get("watchlist", [])]
    recommendations = [
        {
            "symbol": item.get("symbol", ""),
            "name": item.get("name", ""),
            "risk_reward": item.get("risk_reward"),
            "technical_exit_price": item.get("technical_exit_price"),
        }
        for item in report.get("recommendations", [])
    ]
    return {
        "deterministic": True,
        "model_instruction": (
            "Use this complete list verbatim. Do not replace it with examples "
            "or infer missing indicators."
        ),
        "recommendation_count": len(recommendations),
        "watchlist_count": len(watchlist),
        "watchlist_scope": "complete_report_watchlist",
        "recommendations": recommendations,
        "watchlist": watchlist,
    }


def build_user_report_zh(report: dict[str, Any], diagnostics: dict[str, Any]) -> str:
    lines = [
        f"根据最新市场数据监控（{report.get('trade_date', 'unknown')}），筛选结果如下：",
        "",
        "市场环境摘要",
    ]
    market = report.get("market") or {}
    market_state = report.get("market_state") or {}
    lines.extend(
        [
            f"- 数据状态：{report.get('status', 'UNKNOWN')}，"
            f"{report.get('data_freshness', {}).get('mode', 'unknown')} 模式",
            f"- 有效报价：{market.get('universe_size', 0)} 只",
            f"- 上涨占比：{market.get('advancing_ratio', 0)}，"
            f"成交额：{market.get('total_amount', 0)}",
            f"- 市场状态：{market_state.get('market_regime', 'unknown')}，"
            f"买入权限：{market_state.get('buy_permission', 'unknown')}",
            _sector_crowding_summary(report),
            "",
            "股票推荐结论",
        ]
    )
    recommendations = report.get("recommendations") or []
    if recommendations:
        lines.append("当前存在符合全部买入条件的候选：")
        for index, item in enumerate(recommendations, start=1):
            ownership = item.get("ownership_flow") or {}
            crowding = item.get("sector_crowding") or {}
            lines.append(
                f"{index}. {item.get('name')}（{item.get('symbol')}）："
                f"板块 {item.get('industry_name') or crowding.get('industry_name', 'unknown')}，"
                f"盈亏比 {item.get('risk_reward')}，"
                f"技术止损 {item.get('technical_exit_price')}，"
                f"目标价 {item.get('target_1')}，"
                f"资金流 {ownership.get('counterparty_signal', 'unknown')}"
                f"（机构代理净额 {ownership.get('institutional_proxy_net', 'unknown')}，"
                f"散户代理净额 {ownership.get('retail_proxy_net', 'unknown')}），"
                f"板块相对回暖 {crowding.get('relative_warming_score', 'unknown')}，"
                f"拥挤度 {crowding.get('crowding_state', 'unknown')}"
                f"（{crowding.get('crowding_score', 'unknown')}）。"
            )
    else:
        lines.append("当前无符合“下一交易日买入”触发标准的个股。")
    lines.extend(["", _watchlist_section(diagnostics)])
    lines.extend(
        [
            "",
            "风险提示",
            "- 观察名单不是买入建议，只有未达标指标被后续交易日确认后才可重新评估。",
            "- 本报告仅供研究参考，不构成投资建议；最终决策由用户自行判断。",
        ]
    )
    return "\n".join(lines)


def _watchlist_section(diagnostics: dict[str, Any]) -> str:
    watchlist = diagnostics.get("watchlist") or []
    lines = [
        f"观察名单（完整列举，本次 {len(watchlist)} 只）",
    ]
    if not watchlist:
        lines.append("- 无。")
        return "\n".join(lines)
    for index, item in enumerate(watchlist, start=1):
        failed = "；".join(item["failed_condition_text"]) or item["reason"]
        ownership = item.get("ownership_flow") or {}
        crowding = item.get("sector_crowding") or {}
        sector = item.get("industry_name") or crowding.get("industry_name") or "unknown"
        lines.append(
            f"{index}. {item['name']}（{item['symbol']}）：{failed}。"
            f"板块 {sector}，资金流 {ownership.get('counterparty_signal', 'unknown')}，"
            f"板块拥挤 {crowding.get('crowding_state', 'unknown')}。"
        )
    return "\n".join(lines)


def _sector_crowding_summary(report: dict[str, Any]) -> str:
    crowding = report.get("sector_crowding") or {}
    if not crowding:
        return "- 板块拥挤度：未获取"
    extreme = crowding.get("extreme_crowding") or []
    return (
        f"- 板块拥挤度：{crowding.get('status', 'unknown')}，"
        f"覆盖 {crowding.get('board_count', 0)} 个行业板块，"
        f"极度拥挤 {len(extreme)} 个；景气度采用相对回暖分位标准。"
    )


def _watchlist_item(item: dict[str, Any]) -> dict[str, Any]:
    conditions = [_condition_payload(row) for row in item.get("unmet_conditions", [])]
    return {
        "symbol": item.get("symbol", ""),
        "name": item.get("name", ""),
        "close": item.get("close"),
        "pct_change": item.get("pct_change"),
        "amount": item.get("amount"),
        "reason": item.get("reason", ""),
        "ema20": item.get("ema20"),
        "ema60": item.get("ema60"),
        "industry_name": item.get("industry_name", ""),
        "concept_tags": item.get("concept_tags", []),
        "ownership_flow": item.get("ownership_flow", {}),
        "sector_crowding": item.get("sector_crowding", {}),
        "failed_conditions": conditions,
        "failed_condition_text": [row["text_zh"] for row in conditions],
    }


def _condition_payload(condition: dict[str, Any]) -> dict[str, Any]:
    code = str(condition.get("code") or "unknown")
    label = CONDITION_LABELS.get(code, code)
    actual = condition.get("actual")
    operator = condition.get("operator", "")
    threshold = condition.get("threshold")
    return {
        "code": code,
        "label_zh": label,
        "actual": actual,
        "operator": operator,
        "threshold": threshold,
        "text_zh": f"{label}未达标（实际 {actual}，要求 {operator} {threshold}）",
    }
