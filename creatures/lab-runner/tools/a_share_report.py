"""Custom tool for generating A-share structured reports."""

from __future__ import annotations

import json
from typing import Any

from kohakuterrarium.modules.tool.base import BaseTool
from kohakuterrarium.modules.tool.base import ExecutionMode
from kohakuterrarium.modules.tool.base import ToolResult

from a_share_monitor.reporting import build_agent_packet
from a_share_monitor.reporting import build_latest_fixture_report
from a_share_monitor.reporting import build_real_snapshot_report
from a_share_monitor.reporting import build_unavailable_real_snapshot


class AShareReportTool(BaseTool):
    """Generate a real-market or fixture-backed A-share analysis report."""

    needs_context = True

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
                "output_profile": {
                    "type": "string",
                    "enum": ["agent_packet", "full_report"],
                    "description": "agent_packet is the default compact handoff; full_report returns the raw package report.",
                    "default": "agent_packet",
                },
            },
            "required": [],
        }

    async def _execute(self, args: dict[str, Any], **kwargs: Any) -> ToolResult:
        context = kwargs.get("context")
        progress_log: list[dict[str, Any]] = []

        def progress(stage: str, payload: dict[str, Any]) -> None:
            entry = {"stage": stage, **payload}
            progress_log.append(entry)
            router = getattr(getattr(context, "agent", None), "output_router", None)
            if router is not None:
                router.notify_activity(
                    "tool_progress",
                    f"[generate_a_share_report] {stage}",
                    metadata={
                        "tool_name": "generate_a_share_report",
                        "stage": stage,
                        "payload": payload,
                    },
                )

        pretty = bool(args.get("pretty", False))
        mode = str(args.get("mode") or "real")
        output_profile = str(args.get("output_profile") or "agent_packet")
        requested_trade_date = args.get("requested_trade_date")
        user_intent = str(args.get("user_intent") or "latest_completed_session")
        if mode == "fixture":
            report = build_latest_fixture_report()
        else:
            try:
                report = build_real_snapshot_report(
                    requested_trade_date=requested_trade_date,
                    user_intent=user_intent,
                    progress=progress,
                )
            except Exception as exc:
                report = build_unavailable_real_snapshot(
                    error=str(exc),
                    requested_trade_date=requested_trade_date,
                    user_intent=user_intent,
                )
        if progress_log and isinstance(report.get("data_acquisition"), dict):
            report["data_acquisition"]["progress_log"] = progress_log
        payload = (
            report if output_profile == "full_report" else build_agent_packet(report)
        )
        output = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2 if pretty else None,
            sort_keys=True,
        )
        return ToolResult(
            output=output,
            metadata={
                "mode": report.get("data_freshness", {}).get("mode", mode),
                "output_profile": output_profile,
                "agent_packet_schema": (
                    payload.get("schema_version")
                    if isinstance(payload, dict) and output_profile == "agent_packet"
                    else ""
                ),
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
            "By default the tool returns `output_profile: agent_packet`, a compact "
            "handoff contract for terrarium nodes. Use `output_profile: full_report` "
            "only for manual debugging.\n\n"
            "The tool never places orders and never enables real trading. "
            "All output is research material for user review."
        )
