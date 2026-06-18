"""Status command construction and terminal-state classification."""

from __future__ import annotations

from typing import Any

from pangu.agent.errors import AgentError
from pangu.agent.state import load_state
from pangu.agent_monitor.models import DEPLOYMENT_KIND, TRAINING_KIND, MonitorTask, new_monitor_id


def _submit_result(state: dict[str, Any]) -> dict[str, Any]:
    data = state.get("submit_result")
    if not isinstance(data, dict):
        raise AgentError("missing_submit_result", "run state 中没有 submit_result，请先提交任务", "run_submit_first")
    return data


def _training_target_id(data: dict[str, Any]) -> str:
    return str(data.get("task_id") or data.get("id") or data.get("taskId") or "")


def _deployment_target_id(data: dict[str, Any]) -> str:
    return str(data.get("service_id") or data.get("id") or "")


def monitor_task_from_run(
    *,
    run_id: str,
    adapter: str,
    session: dict[str, Any],
    interval_seconds: int = 60,
    timeout_seconds: int = 86400,
    max_delivery_attempts: int = 8,
    success_message: str | None = None,
    failure_message: str | None = None,
) -> MonitorTask:
    state = load_state(run_id)
    kind = state.get("kind")
    submit = _submit_result(state)
    if kind == TRAINING_KIND:
        target_id = _training_target_id(submit)
        status_command = ["pangu-agent", "train", "status", "--run-id", run_id, "--task-id", target_id, "--json"]
        default_success = "训练任务已完成，请继续下一步。"
        default_failure = "训练任务已结束但未成功，请检查失败原因。"
    elif kind == DEPLOYMENT_KIND:
        target_id = _deployment_target_id(submit)
        status_command = ["pangu-agent", "deploy", "status", "--run-id", run_id, "--service-id", target_id, "--json"]
        default_success = "推理部署已达到运行状态，请继续下一步。"
        default_failure = "推理部署已结束但未成功，请检查失败原因。"
    else:
        raise AgentError("unsupported_monitor_run_kind", f"run kind={kind} 不支持 monitor", "use_training_or_deployment_run")

    if not target_id:
        raise AgentError("missing_monitor_target_id", "submit_result 中没有 task_id/service_id", "inspect_submit_result")

    return MonitorTask(
        monitor_id=new_monitor_id(kind),
        kind=kind,
        run_id=run_id,
        target_id=target_id,
        status_command=status_command,
        adapter=adapter,
        session=session,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        max_delivery_attempts=max_delivery_attempts,
        success_message=success_message or default_success,
        failure_message=failure_message or default_failure,
    )


def classify_status(kind: str, payload: dict[str, Any]) -> tuple[bool, bool, str]:
    if kind == TRAINING_KIND:
        status = str(payload.get("task_status") or (payload.get("task") or {}).get("task_status") or "").lower()
        if status == "completed":
            return True, True, status
        if status in {"failed", "stopped"}:
            return True, False, status
        return False, False, status
    if kind == DEPLOYMENT_KIND:
        status = str(payload.get("service_status") or (payload.get("service") or {}).get("status") or "").lower()
        if status == "running":
            return True, True, status
        if status in {"failed", "stopped"}:
            return True, False, status
        return False, False, status
    raise AgentError("invalid_monitor_kind", f"不支持的 monitor kind: {kind}", "use_training_or_deployment")


def build_delivery_payload(task: MonitorTask, status_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "monitor_id": task.monitor_id,
        "kind": task.kind,
        "run_id": task.run_id,
        "target_id": task.target_id,
        "terminal_status": task.terminal_status,
        "success": task.terminal_success,
        "next_action": status_payload.get("next_action"),
        "status_payload": status_payload,
    }
