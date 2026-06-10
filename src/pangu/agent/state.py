"""Run-state persistence for pangu-agent."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from pangu.agent.errors import AgentError
from pangu.config import CONFIG_DIR


RUNS_DIR = CONFIG_DIR / "agent_runs"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_run_id(kind: str) -> str:
    return f"{kind}_{now_utc().strftime('%Y%m%d_%H%M%S')}"


def run_path(run_id: str) -> Path:
    if "/" in run_id or ".." in run_id:
        raise AgentError("invalid_run_id", f"非法 run_id: {run_id}", "rerun_plan")
    return RUNS_DIR / f"{run_id}.json"


def save_state(state: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = run_path(state["run_id"])
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state(run_id: str, expected_kind: str | None = None) -> dict[str, Any]:
    path = run_path(run_id)
    if not path.exists():
        raise AgentError("run_state_not_found", f"找不到 run state: {run_id}", "rerun_plan")
    state = json.loads(path.read_text(encoding="utf-8"))
    if expected_kind and state.get("kind") != expected_kind:
        raise AgentError(
            "run_kind_mismatch",
            f"run_id={run_id} 类型为 {state.get('kind')}，不是 {expected_kind}",
            "rerun_plan",
        )
    expires_at = state.get("expires_at")
    if expires_at:
        exp = datetime.fromisoformat(expires_at)
        if now_utc() > exp:
            raise AgentError("stale_run_state", f"run state 已过期: {run_id}", "rerun_plan")
    return state


def base_state(kind: str, scenario: str | None, env_type: str, workspace_id: str) -> dict[str, Any]:
    created = now_utc()
    run_id = new_run_id(kind)
    return {
        "schema_version": 1,
        "run_id": run_id,
        "kind": kind,
        "scenario": scenario,
        "env_type": env_type,
        "workspace_id": workspace_id,
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(hours=6)).isoformat(),
        "artifacts": {},
        "validate_success": False,
        "artifact_hash": "",
    }


def select_index(state: dict[str, Any], key: str, index: int) -> dict[str, Any]:
    items = state.get(key) or []
    for item in items:
        if item.get("index") == index:
            return item
    raise AgentError(
        "invalid_selection_index",
        f"{key} index {index} 不存在",
        "choose_index_from_plan_output",
    )


def sha256_file(path: str | Path) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def yaml_has_todo(path: str | Path) -> bool:
    text = Path(path).read_text(encoding="utf-8")
    return "TODO" in text


def load_yaml(path: str | Path) -> Any:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

