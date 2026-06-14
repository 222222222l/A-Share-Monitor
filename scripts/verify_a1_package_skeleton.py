#!/usr/bin/env python
"""Verify the A1 a-share-monitor package skeleton."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent


REQUIRED_PATHS = [
    "kohaku.yaml",
    "README.md",
    "creatures/lab-runner/config.yaml",
    "creatures/lab-runner/prompts/system.md",
    "data-schema/README.md",
    "fixtures/README.md",
    "scripts/README.md",
    "config/strategy.yaml",
    "a_share_monitor/__init__.py",
    "a_share_monitor/config.py",
    "a_share_monitor/data/__init__.py",
    "a_share_monitor/strategy/__init__.py",
]


def verify(repo_root: Path) -> dict:
    missing = [path for path in REQUIRED_PATHS if not (PACKAGE_ROOT / path).exists()]
    if missing:
        raise AssertionError(f"missing required paths: {missing}")

    manifest = yaml.safe_load(
        (PACKAGE_ROOT / "kohaku.yaml").read_text(encoding="utf-8")
    )
    if manifest.get("name") != "a-share-monitor":
        raise AssertionError("manifest name must be a-share-monitor")
    if manifest.get("version") != "0.1.10":
        raise AssertionError("manifest version must be 0.1.10")

    creatures = manifest.get("creatures") or []
    creature_names = {entry.get("name") for entry in creatures}
    if "lab-runner" not in creature_names:
        raise AssertionError("manifest must expose lab-runner")
    for entry in creatures:
        path = entry.get("path")
        if not path or not (PACKAGE_ROOT / path).exists():
            raise AssertionError(f"manifest creature path missing: {path}")
    for entry in manifest.get("terrariums") or []:
        path = entry.get("path")
        if not path or not (PACKAGE_ROOT / path).exists():
            raise AssertionError(f"manifest terrarium path missing: {path}")

    config = yaml.safe_load(
        (PACKAGE_ROOT / "creatures" / "lab-runner" / "config.yaml").read_text(
            encoding="utf-8"
        )
    )
    if config.get("name") != "lab-runner":
        raise AssertionError("lab-runner config name mismatch")
    tools = config.get("tools") or []
    tool_names = {item if isinstance(item, str) else item.get("name") for item in tools}
    for tool_name in ("think", "stop_task", "generate_a_share_report"):
        if tool_name not in tool_names:
            raise AssertionError(f"lab-runner missing tool: {tool_name}")
    for tool_name in ("read", "glob", "grep", "json_read"):
        if tool_name in tool_names:
            raise AssertionError(
                f"lab-runner should not expose high-context tool: {tool_name}"
            )

    strategy_config = yaml.safe_load(
        (PACKAGE_ROOT / "config" / "strategy.yaml").read_text(encoding="utf-8")
    )
    for section in (
        "data_quality",
        "quote_screen",
        "market_gate",
        "technical",
        "risk_preference",
        "fallback_pool",
    ):
        if section not in strategy_config:
            raise AssertionError(f"strategy config missing section: {section}")
    if strategy_config["risk_preference"]["min_risk_reward"] < 1.5:
        raise AssertionError("default min risk-reward must stay at least 1.5")

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    if not blueprint.exists():
        raise AssertionError("a-share-monitor blueprint is missing")
    blueprint_text = blueprint.read_text(encoding="utf-8")
    if "`A1`" not in blueprint_text or "a-share-monitor" not in blueprint_text:
        raise AssertionError("blueprint does not track A1")

    return {
        "status": "PASS",
        "package": manifest["name"],
        "version": manifest["version"],
        "creatures": [entry["name"] for entry in creatures],
        "required_paths": len(REQUIRED_PATHS),
        "strategy_config": "config/strategy.yaml",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
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

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
