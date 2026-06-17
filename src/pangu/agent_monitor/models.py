"""Data models for async task monitors."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from pangu.agent.errors import AgentError


TRAINING_KIND = "training"
DEPLOYMENT_KIND = "deployment"
MONITOR_KINDS = {TRAINING_KIND, DEPLOYMENT_KIND}

MONITOR_WATCHING = "watching"
MONITOR_COMPLETED = "completed"
MONITOR_FAILED = "failed"
MONITOR_STOPPED = "stopped"
MONITOR_TIMEOUT = "timeout"
MONITOR_CANCELLED = "cancelled"

DELIVERY_PENDING = "pending"
DELIVERY_DELIVERED = "delivered"
DELIVERY_RETRYING = "retrying"
DELIVERY_FAILED = "failed"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_monitor_id(kind: str) -> str:
    return f"monitor_{kind}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"


@dataclass
class MonitorTask:
    monitor_id: str
    kind: str
    run_id: str
    target_id: str
    status_command: list[str]
    adapter: str
    session: dict[str, Any]
    success_message: str
    failure_message: str
    session_title: str = ""
    interval_seconds: int = 60
    timeout_seconds: int = 86400
    max_delivery_attempts: int = 8
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    monitor_status: str = MONITOR_WATCHING
    delivery_status: str = DELIVERY_PENDING
    delivery_attempts: int = 0
    last_delivery_error: str = ""
    delivered_at: str | None = None
    terminal_status: str = ""
    terminal_success: bool | None = None
    terminal_payload: dict[str, Any] | None = None
    last_status_payload: dict[str, Any] | None = None
    dead_letter_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema_version"] = 1
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MonitorTask":
        payload = dict(data)
        payload.pop("schema_version", None)
        return cls(**payload)

    def touch(self) -> None:
        self.updated_at = utc_now_iso()


def validate_monitor_task(task: MonitorTask) -> None:
    if task.kind not in MONITOR_KINDS:
        raise AgentError("invalid_monitor_kind", f"不支持的 monitor kind: {task.kind}", "use_training_or_deployment")
    if not task.run_id:
        raise AgentError("missing_monitor_run_id", "monitor 缺少 run_id", "pass_run_id")
    if not task.target_id:
        raise AgentError("missing_monitor_target_id", "monitor 缺少 target_id", "check_submit_result")
    if not task.adapter:
        raise AgentError("missing_monitor_adapter", "monitor 缺少 adapter", "pass_adapter")
    if not isinstance(task.session, dict) or not task.session.get("session_id"):
        raise AgentError("missing_monitor_session", "monitor 需要 session_id", "pass_session_id")
    if task.interval_seconds < 1:
        raise AgentError("invalid_monitor_interval", "interval_seconds 必须大于等于 1", "pass_valid_interval")
    if task.timeout_seconds < task.interval_seconds:
        raise AgentError("invalid_monitor_timeout", "timeout_seconds 必须大于等于 interval_seconds", "pass_valid_timeout")
    if task.max_delivery_attempts < 1:
        raise AgentError("invalid_delivery_attempts", "max_delivery_attempts 必须大于等于 1", "pass_valid_delivery_attempts")
