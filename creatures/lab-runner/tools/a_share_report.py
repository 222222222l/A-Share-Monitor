"""Custom tool for generating A-share structured reports."""

from __future__ import annotations

import json
from typing import Any

from kohakuterrarium.modules.tool.base import BaseTool
from kohakuterrarium.modules.tool.base import ExecutionMode
from kohakuterrarium.modules.tool.base import ToolResult

from a_share_monitor.reporting import build_latest_fixture_report
from a_share_monitor.reporting import build_real_snapshot_report
from a_share_monitor.reporting import build_unavailable_real_snapshot


class AShareReportTool(BaseTool):
    """Generate a real-market or fixture-backed A-share analysis report."""

    @property
    def tool_name(self) -> str:
        return "generate_a_share_report"

    @property
    def description(self) -> str:
        return "Generate a structured A-share candidate report. Defaults to real market data."

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["real", "fixture"],
                    "description": "Data mode. Use real by default; use fixture only for explicit offline validation.",
                    "default": "real",
                },
                "requested_trade_date": {
                    "type": "string",
                    "description": "Optional YYYY-MM-DD trade date. If omitted, use the latest completed A-share session.",
                },
                "user_intent": {
                    "type": "string",
                    "description": "Short description of the user's market question.",
                    "default": "latest_completed_session",
                },
                "pretty": {
                    "type": "boolean",
                    "description": "Return indented JSON when true. Defaults to compact JSON for lower token cost.",
                    "default": False,
                },
            },
            "required": [],
        }

    async def _execute(self, args: dict[str, Any], **kwargs: Any) -> ToolResult:
        pretty = bool(args.get("pretty", False))
        mode = str(args.get("mode") or "real")
        requested_trade_date = args.get("requested_trade_date")
        user_intent = str(args.get("user_intent") or "latest_completed_session")
        if mode == "fixture":
            report = build_latest_fixture_report()
        else:
            try:
                report = build_real_snapshot_report(
                    requested_trade_date=requested_trade_date,
                    user_intent=user_intent,
                )
            except Exception as exc:
                report = build_unavailable_real_snapshot(
                    error=str(exc),
                    requested_trade_date=requested_trade_date,
                    user_intent=user_intent,
                )
        output = json.dumps(
            report,
            ensure_ascii=False,
            indent=2 if pretty else None,
            sort_keys=True,
        )
        return ToolResult(
            output=output,
            metadata={
                "mode": report.get("data_freshness", {}).get("mode", mode),
                "status": report.get("status", "PASS"),
                "trade_date": report["trade_date"],
                "planned_symbols": report.get("selection_summary", {}).get(
                    "planned_symbols", []
                ),
                "critic_status": report.get("critic_review", {}).get("status"),
            },
        )

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return (
            "# generate_a_share_report\n\n"
            "Builds a structured A-share report. The default `mode` is `real`, "
            "which resolves the latest completed A-share session and fetches "
            "public quote/kline data. Use `mode: fixture` only when the user "
            "explicitly asks for offline validation.\n\n"
            "The tool does not silently fall back from real data to fixture data. "
            "If real data is unavailable it returns DATA_UNAVAILABLE.\n\n"
            "The tool never places orders and never enables real trading. "
            "All output is research material for user review."
        )
