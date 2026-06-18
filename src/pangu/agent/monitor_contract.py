"""Structured monitor handoff contract for long-running submit commands."""

from __future__ import annotations

from typing import Any

from pangu.agent.goals import GOAL_ORDER


MONITOR_ADD_ACTION = "monitor.add"
FORBIDDEN_MAIN_SESSION_POLL_COMMANDS = [
    "pangu-agent train status",
    "pangu-agent deploy status",
    "pangu training get",
    "pangu service get",
]


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
        "main_session_polling_allowed": True,
    }


def apply_submit_monitor_contract(result: dict[str, Any]) -> dict[str, Any]:
    command = result.get("monitor_add_template")
    if not command:
        result["monitor_required"] = False
        return result

    required = not bool(result.get("terminal"))
    result["monitor_required"] = required
    result["main_session_polling_allowed"] = not required
    if required:
        result["forbidden_main_session_poll_commands"] = FORBIDDEN_MAIN_SESSION_POLL_COMMANDS
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


def apply_status_monitor_contract(
    result: dict[str, Any],
    *,
    run_id: str | None,
    target_id: str,
    submitted_milestone: str,
) -> dict[str, Any]:
    if result.get("terminal") or not run_id or not target_id:
        result.setdefault("monitor_required", False)
        return result

    goal = str(result.get("goal") or "")
    if GOAL_ORDER.get(goal, -1) <= GOAL_ORDER[submitted_milestone]:
        result.setdefault("monitor_required", False)
        return result

    result.update(monitor_submit_fields(run_id, target_id))
    result["monitor_required"] = True
    result["main_session_polling_allowed"] = False
    result["forbidden_main_session_poll_commands"] = FORBIDDEN_MAIN_SESSION_POLL_COMMANDS
    result["next_action"] = MONITOR_ADD_ACTION
    monitor = dict(result.get("monitor") or {})
    monitor["required"] = True
    result["monitor"] = monitor
    return result
