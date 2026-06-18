"""Local JSON storage for async monitors and delivery dead letters."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pangu.agent.errors import AgentError
from pangu.agent_monitor.models import MonitorTask, validate_monitor_task
from pangu.config import CONFIG_DIR


MONITORS_DIR = CONFIG_DIR / "agent_monitors"
DEAD_LETTERS_DIR = CONFIG_DIR / "agent_monitor_dead_letters"
MONITOR_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def monitor_path(monitor_id: str) -> Path:
    if not MONITOR_ID_RE.fullmatch(monitor_id):
        raise AgentError("invalid_monitor_id", f"非法 monitor_id: {monitor_id}", "check_monitor_id")
    return MONITORS_DIR / f"{monitor_id}.json"


def save_monitor(task: MonitorTask) -> None:
    validate_monitor_task(task)
    MONITORS_DIR.mkdir(parents=True, exist_ok=True)
    MONITORS_DIR.chmod(0o700)
    task.touch()
    path = monitor_path(task.monitor_id)
    path.write_text(json.dumps(task.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)


def load_monitor(monitor_id: str) -> MonitorTask:
    path = monitor_path(monitor_id)
    if not path.exists():
        raise AgentError("monitor_not_found", f"找不到 monitor: {monitor_id}", "check_monitor_id")
    return MonitorTask.from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_monitors(*, delivery_status: str | None = None) -> list[dict[str, Any]]:
    if not MONITORS_DIR.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(MONITORS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if delivery_status and data.get("delivery_status") != delivery_status:
            continue
        rows.append(data)
    return rows


def write_dead_letter(task: MonitorTask, message: str, payload: dict[str, Any], error: str) -> str:
    DEAD_LETTERS_DIR.mkdir(parents=True, exist_ok=True)
    DEAD_LETTERS_DIR.chmod(0o700)
    path = DEAD_LETTERS_DIR / f"{task.monitor_id}.json"
    data = {
        "monitor_id": task.monitor_id,
        "adapter": task.adapter,
        "session": task.session,
        "message": message,
        "payload": payload,
        "delivery_attempts": task.delivery_attempts,
        "last_delivery_error": error,
        "created_at": task.created_at,
        "failed_at": task.updated_at,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)
    return str(path)
