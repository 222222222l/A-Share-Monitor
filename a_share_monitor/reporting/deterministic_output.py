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
            "",
            "股票推荐结论",
        ]
    )
    recommendations = report.get("recommendations") or []
    if recommendations:
        lines.append("当前存在符合全部买入条件的候选：")
        for index, item in enumerate(recommendations, start=1):
            lines.append(
                f"{index}. {item.get('name')}（{item.get('symbol')}）："
                f"盈亏比 {item.get('risk_reward')}，"
                f"技术止损 {item.get('technical_exit_price')}，"
                f"目标价 {item.get('target_1')}。"
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
        lines.append(f"{index}. {item['name']}（{item['symbol']}）：{failed}。")
    return "\n".join(lines)


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
