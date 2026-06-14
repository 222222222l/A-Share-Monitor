#!/usr/bin/env python
"""Verify D2 daily-monitor terrarium topology."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_ROOT.parent
DEFAULT_REPO_ROOT = PACKAGE_ROOT.parent.parent
TERRARIUM_PATH = PACKAGE_ROOT / "terrariums" / "daily-monitor" / "terrarium.yaml"
EXPECTED_CHAIN = ["data", "regime", "screen", "risk", "recommendation", "critic"]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repo_root: Path) -> dict:
    data = yaml.safe_load(TERRARIUM_PATH.read_text(encoding="utf-8"))
    terrarium = data["terrarium"]
    creatures = terrarium["creatures"]
    names = [item["name"] for item in creatures]
    check(names == EXPECTED_CHAIN, "daily-monitor chain order mismatch")

    wiring = {
        item["name"]: [edge["to"] for edge in item.get("output_wiring", [])]
        for item in creatures
    }
    for source, target in zip(EXPECTED_CHAIN, EXPECTED_CHAIN[1:]):
        check(wiring.get(source) == [target], f"missing edge {source}->{target}")
    check(wiring.get("critic") == [], "critic must emit final output directly")

    for item in creatures:
        if item["name"] in {"data", "critic"}:
            continue
        tools = item.get("tools", [])
        tool_names = [
            tool if isinstance(tool, str) else tool.get("name") for tool in tools
        ]
        check(
            "tools" in item.get("no_inherit", []), f"{item['name']} must drop lab tools"
        )
        check(
            "generate_a_share_report" not in tool_names,
            f"{item['name']} must not fetch market data",
        )

    prompts = TERRARIUM_PATH.parent / "prompts"
    for item in creatures:
        prompt_path = TERRARIUM_PATH.parent / item["system_prompt_file"]
        check(prompt_path.exists(), f"missing prompt for {item['name']}")
    check(prompts.exists(), "prompts directory missing")

    manifest = PACKAGE_ROOT / "kohaku.yaml"
    manifest_text = manifest.read_text(encoding="utf-8")
    check("daily-monitor" in manifest_text, "terrarium not registered")

    blueprint = repo_root / "docs" / "zh-CN" / "dev" / "a-share-monitor-blueprint.md"
    blueprint_text = blueprint.read_text(encoding="utf-8")
    check(
        "`D2`" in blueprint_text and "terrarium" in blueprint_text,
        "blueprint missing D2",
    )

    return {
        "status": "PASS",
        "terrarium": terrarium["name"],
        "chain": EXPECTED_CHAIN,
        "edges": wiring,
        "channels": sorted(terrarium["channels"].keys()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify D2 daily-monitor terrarium.")
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
