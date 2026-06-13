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
    "a_share_monitor/__init__.py",
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
    if manifest.get("version") != "0.1.0":
        raise AssertionError("manifest version must be 0.1.0")

    creatures = manifest.get("creatures") or []
    if creatures != [{"name": "lab-runner", "path": "creatures/lab-runner"}]:
        raise AssertionError("manifest must expose only lab-runner in A1")

    config = yaml.safe_load(
        (PACKAGE_ROOT / "creatures" / "lab-runner" / "config.yaml").read_text(
            encoding="utf-8"
        )
    )
    if config.get("name") != "lab-runner":
        raise AssertionError("lab-runner config name mismatch")
    tools = config.get("tools") or []
    for tool_name in ("read", "glob", "grep", "json_read", "think", "stop_task"):
        if tool_name not in tools:
            raise AssertionError(f"lab-runner missing tool: {tool_name}")

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
