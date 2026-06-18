"""Structured monitor handoff contract for long-running submit commands."""

from __future__ import annotations

from typing import Any


MONITOR_ADD_ACTION = "monitor.add"


def monitor_add_template(run_id: str) -> str:
    return f"pangu-agent monitor add --run-id {run_id} --session-id <session_id> --detach --json"


def monitor_submit_fields(run_id: str, target_id: str) -> dict[str, Any]:
    if not target_id:
        return {"monitor_required": False, "monitor_add_template": ""}
    command = monitor_add_template(run_id)
    return {
        "monitor_required": False,
        "monitor_add_template": command,
        "monitor": {
            "available": True,
            "required": False,
            "next_action": MONITOR_ADD_ACTION,
            "command_template": command,
            "session_id_required": True,
            "session_id_sources": ["--session-id", "PANGU_MONITOR_SESSION_ID"],
            "adapter_source": "pangu config monitor_adapter",
            "detach": True,
        },
    }


def apply_submit_monitor_contract(result: dict[str, Any]) -> dict[str, Any]:
    command = result.get("monitor_add_template")
    if not command:
        result["monitor_required"] = False
        return result

    required = not bool(result.get("terminal"))
    result["monitor_required"] = required
    monitor = dict(result.get("monitor") or {})
    monitor.update(
        {
            "available": True,
            "required": required,
            "next_action": MONITOR_ADD_ACTION,
            "command_template": command,
            "session_id_required": True,
            "session_id_sources": ["--session-id", "PANGU_MONITOR_SESSION_ID"],
            "adapter_source": "pangu config monitor_adapter",
            "detach": True,
        }
    )
    result["monitor"] = monitor
    if required:
        result["next_action"] = MONITOR_ADD_ACTION
    return result
