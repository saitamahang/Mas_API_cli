"""Detached runner for async monitors."""

from __future__ import annotations

from json import JSONDecoder
import locale
import subprocess
import time
from typing import Any, Callable

from pangu.agent.errors import AgentError
from pangu.agent_monitor.adapters import AgentAdapter, create_adapter
from pangu.agent_monitor.models import (
    DELIVERY_DELIVERED,
    DELIVERY_FAILED,
    DELIVERY_PENDING,
    DELIVERY_RETRYING,
    MONITOR_COMPLETED,
    MONITOR_CANCELLED,
    MONITOR_FAILED,
    MONITOR_STOPPED,
    MONITOR_TIMEOUT,
    MonitorTask,
    utc_now_iso,
)
from pangu.agent_monitor.status import build_delivery_payload, classify_status
from pangu.agent_monitor.store import load_monitor, save_monitor, write_dead_letter
from pangu.config import CONFIG_DIR


LOGS_DIR = CONFIG_DIR / "agent_monitor_logs"

StatusRunner = Callable[[list[str]], dict[str, Any]]
AdapterFactory = Callable[[str], AgentAdapter]
SleepFn = Callable[[float], None]


def extract_first_json(text: str) -> Any:
    decoder = JSONDecoder()
    for index, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
            return value
        except ValueError:
            continue
    raise AgentError("json_parse_failed", "未能从 status command 输出中解析 JSON", "inspect_status_command_output")


def decode_process_output(data: bytes) -> str:
    encodings = ["utf-8-sig", locale.getpreferredencoding(False)]
    seen: set[str] = set()
    for encoding in encodings:
        normalized = (encoding or "").lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def run_json_command(command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(command, capture_output=True, check=False)
    output = decode_process_output((proc.stdout or b"") + (proc.stderr or b""))
    if proc.returncode != 0:
        raise AgentError(
            "monitor_status_command_failed",
            output.strip() or f"status command failed: {proc.returncode}",
            "inspect_monitor_status_command",
            {"command": command, "returncode": proc.returncode},
        )
    data = extract_first_json(output)
    if not isinstance(data, dict):
        raise AgentError("monitor_status_not_object", "status command 未返回 JSON object", "inspect_status_command")
    return data


def status_to_monitor_status(status: str, success: bool) -> str:
    if success:
        return MONITOR_COMPLETED
    if status == "stopped":
        return MONITOR_STOPPED
    return MONITOR_FAILED


def build_monitor_message(task: MonitorTask, success: bool) -> str:
    base = task.success_message if success else task.failure_message
    target_name = "task_id" if task.kind == "training" else "service_id"
    return "\n".join(
        [
            base,
            "",
            f"run_id: {task.run_id}",
            f"{target_name}: {task.target_id}",
            f"status: {task.terminal_status}",
            f"next_action: {(task.terminal_payload or {}).get('next_action', '')}",
        ]
    ).strip()


def delivery_backoff_seconds(attempt: int) -> int:
    return min(30 * (2 ** max(attempt - 1, 0)), 900)


def deliver_with_retries(
    task: MonitorTask,
    *,
    adapter_factory: AdapterFactory = create_adapter,
    sleep_fn: SleepFn = time.sleep,
) -> MonitorTask:
    payload = build_delivery_payload(task, task.terminal_payload or {})
    message = build_monitor_message(task, bool(task.terminal_success))
    adapter = adapter_factory(task.adapter)

    while task.delivery_attempts < task.max_delivery_attempts:
        task.delivery_attempts += 1
        task.delivery_status = DELIVERY_PENDING if task.delivery_attempts == 1 else DELIVERY_RETRYING
        save_monitor(task)
        try:
            adapter.send_message(task.session, message, payload)
            task.delivery_status = DELIVERY_DELIVERED
            task.delivered_at = utc_now_iso()
            task.last_delivery_error = ""
            save_monitor(task)
            return task
        except Exception as exc:
            task.last_delivery_error = str(exc)
            save_monitor(task)
            if task.delivery_attempts >= task.max_delivery_attempts:
                break
            sleep_fn(delivery_backoff_seconds(task.delivery_attempts))

    task.delivery_status = DELIVERY_FAILED
    task.dead_letter_path = write_dead_letter(task, message, payload, task.last_delivery_error)
    save_monitor(task)
    return task


def run_monitor(
    monitor_id: str,
    *,
    status_runner: StatusRunner = run_json_command,
    adapter_factory: AdapterFactory = create_adapter,
    sleep_fn: SleepFn = time.sleep,
) -> MonitorTask:
    task = load_monitor(monitor_id)
    deadline = time.time() + task.timeout_seconds

    while time.time() <= deadline:
        latest = load_monitor(monitor_id)
        if latest.monitor_status == MONITOR_CANCELLED:
            return latest
        task = latest
        payload = status_runner(task.status_command)
        task.last_status_payload = payload
        terminal, success, terminal_status = classify_status(task.kind, payload)
        save_monitor(task)

        if not terminal:
            sleep_fn(task.interval_seconds)
            continue

        task.terminal_status = terminal_status
        task.terminal_success = success
        task.terminal_payload = payload
        task.monitor_status = status_to_monitor_status(terminal_status, success)
        save_monitor(task)
        return deliver_with_retries(task, adapter_factory=adapter_factory, sleep_fn=sleep_fn)

    task.monitor_status = MONITOR_TIMEOUT
    task.terminal_status = "timeout"
    task.terminal_success = False
    task.terminal_payload = task.last_status_payload or {}
    save_monitor(task)
    return deliver_with_retries(task, adapter_factory=adapter_factory, sleep_fn=sleep_fn)


def start_detached_monitor(monitor_id: str) -> dict[str, Any]:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.chmod(0o700)
    log_path = LOGS_DIR / f"{monitor_id}.log"
    log_file = log_path.open("ab")
    try:
        proc = subprocess.Popen(
            ["pangu-agent", "monitor", "run", "--monitor-id", monitor_id],
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        log_file.close()
        raise AgentError("monitor_detach_failed", str(exc), "run_monitor_manually") from exc

    return {
        "pid": proc.pid,
        "log_path": str(log_path),
        "run_command": f"pangu-agent monitor run --monitor-id {monitor_id}",
    }


def retry_delivery(
    monitor_id: str,
    *,
    adapter: str | None = None,
    session: dict[str, Any] | None = None,
    adapter_factory: AdapterFactory = create_adapter,
) -> MonitorTask:
    task = load_monitor(monitor_id)
    if not task.terminal_payload:
        raise AgentError("monitor_not_terminal", "monitor 尚未到终态，不能重投递", "wait_for_monitor_terminal")
    if adapter:
        task.adapter = adapter
    if session:
        task.session = session
    task.delivery_status = DELIVERY_PENDING
    task.delivery_attempts = 0
    task.last_delivery_error = ""
    task.dead_letter_path = ""
    save_monitor(task)
    return deliver_with_retries(task, adapter_factory=adapter_factory)


def monitor_message(monitor_id: str) -> str:
    task = load_monitor(monitor_id)
    if not task.terminal_payload:
        raise AgentError("monitor_not_terminal", "monitor 尚未到终态，暂无可导出的消息", "wait_for_monitor_terminal")
    return build_monitor_message(task, bool(task.terminal_success))
