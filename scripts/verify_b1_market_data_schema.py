#!/usr/bin/env python
"""Verify the B1 market data schema contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent

SCHEMA_PATH = PACKAGE_ROOT / "data-schema" / "market-data-schema.yaml"

EXPECTED_RECORD_TYPES = {
    "security_master",
    "daily_bar",
    "index_bar",
    "sector_bar",
    "market_breadth",
    "market_state_signal",
    "technical_indicator",
    "divergence_signal",
    "fundamental_risk_event",
    "ownership_flow_signal",
    "sector_score",
    "stock_signal",
    "recommendation",
}

TECHNICAL_FIELDS = {
    "ema_5",
    "ema_10",
    "ema_20",
    "ema_60",
    "ema_12",
    "ema_26",
    "rsi_6",
    "rsi_14",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "atr_14",
    "relative_strength_20d",
}

RECOMMENDATION_EXIT_FIELDS = {
    "technical_exit_price",
    "technical_exit_reason",
    "fundamental_exit_trigger",
    "time_exit_rule",
}

OWNERSHIP_FLOW_FIELDS = {
    "retail_crowding_score",
    "institutional_accumulation_score",
    "institutional_exit_score",
    "counterparty_signal",
    "evidence",
}

MARKET_STATE_FIELDS = {
    "market_state",
    "buy_permission",
    "liquidity_state",
    "breadth_state",
    "rotation_state",
    "policy_support_signal",
    "evidence",
}


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise AssertionError(f"Expected YAML object in {path}")
    return data


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    schema = load_yaml(SCHEMA_PATH)

    check(schema.get("version") == 1, "schema version must be 1")
    check(schema.get("status") == "design-contract", "schema status mismatch")

    markets = schema.get("markets") or {}
    check("bse" in markets.get("reference_only", []), "BSE must be reference-only")
    check("bse" not in markets.get("tradable", []), "BSE must not be tradable in B1")

    source_tiers = schema.get("source_tiers") or {}
    check(
        source_tiers.get("L0", {}).get("default_for_validation"), "L0 must be default"
    )
    tradingview_ref = source_tiers.get("L1_5", {})
    check(
        tradingview_ref.get("default_for_automation") is False,
        "TradingView reference tier must not be default automation",
    )

    record_types = schema.get("record_types")
    check(isinstance(record_types, dict), "record_types must be declared")
    missing_records = EXPECTED_RECORD_TYPES - set(record_types)
    check(not missing_records, f"missing record types: {sorted(missing_records)}")

    technical = record_types["technical_indicator"]
    technical_required = set(technical.get("required_fields") or [])
    missing_technical = TECHNICAL_FIELDS - technical_required
    check(
        not missing_technical,
        f"technical_indicator missing fields: {sorted(missing_technical)}",
    )
    check(
        technical.get("field_rules", {}).get("warmup_min_days") == 180,
        "technical indicator warmup must be 180 days",
    )

    divergence = record_types["divergence_signal"]
    divergence_required = set(divergence.get("required_fields") or [])
    for field in (
        "divergence",
        "price_swing_a",
        "price_swing_b",
        "indicator_name",
        "indicator_swing_a",
        "indicator_swing_b",
        "evidence",
    ):
        check(field in divergence_required, f"divergence_signal missing {field}")

    market_state = record_types["market_state_signal"]
    market_state_required = set(market_state.get("required_fields") or [])
    missing_market_state = MARKET_STATE_FIELDS - market_state_required
    check(
        not missing_market_state,
        f"market_state_signal missing fields: {sorted(missing_market_state)}",
    )
    market_regime_enum = set(schema.get("enums", {}).get("market_regime") or [])
    for state in (
        "liquidity_crisis",
        "policy_support_rebound",
        "rotation_opportunity",
        "broad_risk_on",
        "mixed_chop",
        "overheated_chase_risk",
        "unknown",
    ):
        check(state in market_regime_enum, f"market regime missing: {state}")
    buy_permission_enum = set(schema.get("enums", {}).get("buy_permission") or [])
    for permission in (
        "blocked",
        "selective",
        "rotation_only",
        "rebound_watch",
        "normal",
    ):
        check(
            permission in buy_permission_enum, f"buy permission missing: {permission}"
        )

    recommendation = record_types["recommendation"]
    recommendation_required = set(recommendation.get("required_fields") or [])
    missing_exit = RECOMMENDATION_EXIT_FIELDS - recommendation_required
    check(
        not missing_exit,
        f"recommendation missing exit fields: {sorted(missing_exit)}",
    )
    for field in ("technical_indicators", "divergence", "risk_reward", "confidence"):
        check(field in recommendation_required, f"recommendation missing {field}")
    check(
        "ownership_flow_risk" in recommendation_required,
        "recommendation missing ownership_flow_risk",
    )

    ownership = record_types["ownership_flow_signal"]
    ownership_required = set(ownership.get("required_fields") or [])
    missing_ownership = OWNERSHIP_FLOW_FIELDS - ownership_required
    check(
        not missing_ownership,
        f"ownership_flow_signal missing fields: {sorted(missing_ownership)}",
    )
    counterparty_enum = set(schema.get("enums", {}).get("counterparty_signal") or [])
    check(
        "retail_institution_exit_risk" in counterparty_enum,
        "counterparty enum missing retail risk signal",
    )
    check(
        "retail_exit_institution_accumulation" in counterparty_enum,
        "counterparty enum missing institution accumulation signal",
    )

    quality = schema.get("quality_rules") or {}
    reject_when = set(quality.get("reject_when") or [])
    for rule in (
        "missing_exit_risk_fields_for_buy",
        "retail_crowding_with_institutional_exit_for_buy",
        "risk_reward_below_threshold",
        "bse_symbol_in_tradable_output",
    ):
        check(rule in reject_when, f"quality reject rule missing: {rule}")

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check(
        "`B1`" in blueprint_text and "market data schema" in blueprint_text,
        "blueprint missing B1",
    )

    return {
        "status": "PASS",
        "schema": str(SCHEMA_PATH.relative_to(repo_root)),
        "record_types": sorted(EXPECTED_RECORD_TYPES),
        "technical_fields": sorted(TECHNICAL_FIELDS),
        "exit_fields": sorted(RECOMMENDATION_EXIT_FIELDS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify B1 market data schema.")
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
