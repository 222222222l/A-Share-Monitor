"""Custom tool for generating offline A-share structured reports."""

from __future__ import annotations

import json
from typing import Any

from kohakuterrarium.modules.tool.base import BaseTool
from kohakuterrarium.modules.tool.base import ExecutionMode
from kohakuterrarium.modules.tool.base import ToolResult

from a_share_monitor.reporting import build_latest_fixture_report


class AShareReportTool(BaseTool):
    """Generate the deterministic offline A-share analysis report."""

    @property
    def tool_name(self) -> str:
        return "generate_a_share_report"

    @property
    def description(self) -> str:
        return "Generate a structured offline A-share candidate report."

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pretty": {
                    "type": "boolean",
                    "description": "Return indented JSON when true.",
                    "default": True,
                }
            },
            "required": [],
        }

    async def _execute(self, args: dict[str, Any], **kwargs: Any) -> ToolResult:
        pretty = bool(args.get("pretty", True))
        report = build_latest_fixture_report()
        output = json.dumps(
            report,
            ensure_ascii=False,
            indent=2 if pretty else None,
            sort_keys=True,
        )
        return ToolResult(
            output=output,
            metadata={
                "trade_date": report["trade_date"],
                "planned_symbols": report["selection_summary"]["planned_symbols"],
                "critic_status": report["critic_review"]["status"],
            },
        )

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return (
            "# generate_a_share_report\n\n"
            "Builds the deterministic offline A-share structured report from "
            "fixture data and the staged C-group strategy pipeline.\n\n"
            "The tool never places orders and never enables real trading. "
            "All output is research material for user review."
        )
