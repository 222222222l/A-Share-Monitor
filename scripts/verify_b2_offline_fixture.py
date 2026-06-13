#!/usr/bin/env python
"""Verify the B2 offline fixture dataset."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent
FIXTURE_ROOT = PACKAGE_ROOT / "fixtures" / "b2_minimal"
SCHEMA_PATH = PACKAGE_ROOT / "data-schema" / "market-data-schema.yaml"

MIN_TRADABLE_SYMBOLS = 5
MIN_INDEXES = 2
MIN_SECTORS = 2
MIN_TRADING_DAYS = 60

REQUIRED_FILES = {
    "manifest.json",
    "security_master.csv",
    "daily_bars.csv",
    "index_bars.csv",
    "sector_bars.csv",
    "market_breadth.csv",
    "fundamental_risk_events.csv",
    "ownership_flow_signals.csv",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    check(isinstance(data, dict), f"Expected YAML object in {path}")
    return data


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def required_fields(schema: dict[str, Any], record_type: str) -> set[str]:
    record_types = schema.get("record_types") or {}
    record = record_types.get(record_type) or {}
    return set(record.get("required_fields") or [])


def assert_fields(rows: list[dict[str, str]], fields: set[str], file_name: str) -> None:
    check(rows, f"{file_name} must not be empty")
    actual = set(rows[0])
    missing = fields - actual
    check(not missing, f"{file_name} missing fields: {sorted(missing)}")


def parse_float(row: dict[str, str], field: str) -> float:
    try:
        return float(row[field])
    except ValueError as exc:
        raise AssertionError(f"{field} must be numeric in row {row}") from exc


def verify_price_integrity(rows: list[dict[str, str]]) -> None:
    sample_rows = rows[:50] + rows[-50:]
    for row in sample_rows:
        open_price = parse_float(row, "open")
        high = parse_float(row, "high")
        low = parse_float(row, "low")
        close = parse_float(row, "close")
        limit_up = parse_float(row, "limit_up")
        limit_down = parse_float(row, "limit_down")
        check(low <= min(open_price, close), f"low price integrity failed: {row}")
        check(high >= max(open_price, close), f"high price integrity failed: {row}")
        check(limit_up > limit_down, f"limit price integrity failed: {row}")
        check(row["is_suspended"] in {"true", "false"}, "is_suspended must be boolean")
        check(row["is_st"] in {"true", "false"}, "is_st must be boolean")


def verify(repo_root: Path) -> dict:
    missing_files = [
        file_name
        for file_name in sorted(REQUIRED_FILES)
        if not (FIXTURE_ROOT / file_name).exists()
    ]
    check(not missing_files, f"missing fixture files: {missing_files}")

    schema = load_yaml(SCHEMA_PATH)
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    check(manifest.get("dataset_id") == "b2_minimal", "manifest dataset_id mismatch")
    check(manifest.get("synthetic") is True, "fixture must be explicitly synthetic")
    check(manifest.get("trading_day_count", 0) >= MIN_TRADING_DAYS, "not enough days")
    check(manifest.get("price_mode") == "qfq", "price_mode must be qfq")

    security_rows = load_csv(FIXTURE_ROOT / "security_master.csv")
    daily_rows = load_csv(FIXTURE_ROOT / "daily_bars.csv")
    index_rows = load_csv(FIXTURE_ROOT / "index_bars.csv")
    sector_rows = load_csv(FIXTURE_ROOT / "sector_bars.csv")
    breadth_rows = load_csv(FIXTURE_ROOT / "market_breadth.csv")
    event_rows = load_csv(FIXTURE_ROOT / "fundamental_risk_events.csv")
    ownership_rows = load_csv(FIXTURE_ROOT / "ownership_flow_signals.csv")

    assert_fields(
        security_rows, required_fields(schema, "security_master"), "security_master.csv"
    )
    assert_fields(daily_rows, required_fields(schema, "daily_bar"), "daily_bars.csv")
    assert_fields(index_rows, required_fields(schema, "index_bar"), "index_bars.csv")
    assert_fields(sector_rows, required_fields(schema, "sector_bar"), "sector_bars.csv")
    assert_fields(
        breadth_rows, required_fields(schema, "market_breadth"), "market_breadth.csv"
    )
    assert_fields(
        event_rows,
        required_fields(schema, "fundamental_risk_event"),
        "fundamental_risk_events.csv",
    )
    assert_fields(
        ownership_rows,
        required_fields(schema, "ownership_flow_signal"),
        "ownership_flow_signals.csv",
    )

    tradable_symbols = {
        row["symbol"] for row in security_rows if row["tradable"] == "true"
    }
    bse_rows = [row for row in security_rows if row["exchange"] == "bse"]
    check(len(tradable_symbols) >= MIN_TRADABLE_SYMBOLS, "not enough tradable symbols")
    check(bse_rows, "BSE reference row is required")
    check(
        all(row["tradable"] == "false" for row in bse_rows),
        "BSE rows must not be tradable",
    )
    check(
        all(row["bse_reference_only"] == "true" for row in bse_rows),
        "BSE rows must be reference-only",
    )

    daily_symbols = defaultdict(set)
    for row in daily_rows:
        daily_symbols[row["symbol"]].add(row["trade_date"])
    check(
        set(daily_symbols) == tradable_symbols, "daily bars must cover tradable symbols"
    )
    for symbol, dates in daily_symbols.items():
        check(len(dates) >= MIN_TRADING_DAYS, f"{symbol} has too few daily bars")

    index_symbols = {row["index_symbol"] for row in index_rows}
    sector_ids = {row["sector_id"] for row in sector_rows}
    check(len(index_symbols) >= MIN_INDEXES, "not enough index bars")
    check(len(sector_ids) >= MIN_SECTORS, "not enough sector bars")
    check(len(breadth_rows) >= MIN_TRADING_DAYS, "not enough market breadth rows")

    ownership_symbols = {row["symbol"] for row in ownership_rows}
    check(
        tradable_symbols <= ownership_symbols,
        "ownership flow signals must cover every tradable symbol",
    )
    counterparty_signals = {row["counterparty_signal"] for row in ownership_rows}
    check(
        "retail_institution_exit_risk" in counterparty_signals,
        "fixture must include retail crowding / institution exit risk",
    )
    check(
        "retail_exit_institution_accumulation" in counterparty_signals,
        "fixture must include retail exit / institution accumulation signal",
    )

    verify_price_integrity(daily_rows)

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check(
        "`B2`" in blueprint_text and "fixture" in blueprint_text, "blueprint missing B2"
    )

    return {
        "status": "PASS",
        "fixture": str(FIXTURE_ROOT.relative_to(repo_root)),
        "trading_days": manifest["trading_day_count"],
        "tradable_symbols": sorted(tradable_symbols),
        "index_count": len(index_symbols),
        "sector_count": len(sector_ids),
        "daily_bar_rows": len(daily_rows),
        "ownership_flow_rows": len(ownership_rows),
        "offline_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify B2 offline fixture dataset.")
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
