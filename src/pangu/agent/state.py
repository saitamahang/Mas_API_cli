"""Run-state persistence for pangu-agent."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from pangu.agent.errors import AgentError
from pangu.config import CONFIG_DIR


RUNS_DIR = CONFIG_DIR / "agent_runs"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,96}$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_run_id(kind: str) -> str:
    return f"{kind}_{now_utc().strftime('%Y%m%d_%H%M%S')}"


def run_path(run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise AgentError("invalid_run_id", f"非法 run_id: {run_id}", "rerun_plan")
    return RUNS_DIR / f"{run_id}.json"


def save_state(state: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.chmod(0o700)
    path = run_path(state["run_id"])
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)


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


def gc_runs(max_age_hours: int = 24) -> dict[str, Any]:
    """Delete expired run-state files older than max_age_hours."""
    if max_age_hours < 1:
        raise AgentError("invalid_gc_age", "max_age_hours 必须大于等于 1", "pass_valid_max_age_hours")
    if not RUNS_DIR.exists():
        return {"runs_dir": str(RUNS_DIR), "deleted": [], "kept": 0}

    cutoff = now_utc() - timedelta(hours=max_age_hours)
    deleted: list[str] = []
    kept = 0
    for path in RUNS_DIR.glob("*.json"):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            expires_at = state.get("expires_at")
            expired = bool(expires_at and datetime.fromisoformat(expires_at) < now_utc())
            old = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff
            if expired and old:
                path.unlink()
                deleted.append(path.name)
            else:
                kept += 1
        except Exception:
            kept += 1
    return {"runs_dir": str(RUNS_DIR), "deleted": deleted, "kept": kept}
