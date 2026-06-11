"""Approval helpers for high-impact agent actions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pangu.agent.errors import AgentError


TRAIN_SUBMIT_ACTION = "train.submit"
DEPLOY_SUBMIT_ACTION = "deploy.submit"
TRAIN_SUBMIT_CONFIRM = "submit-training"
DEPLOY_SUBMIT_CONFIRM = "deploy-service"
PUBLISH_MODEL_CONFIRM = "publish-model"


def require_confirmation(confirm: str | None, expected: str) -> None:
    if confirm != expected:
        raise AgentError(
            "approval_confirmation_required",
            f"需要用户确认后传入 --confirm {expected}",
            "ask_user_for_explicit_approval",
        )


def record_approval(
    state: dict[str, Any],
    action: str,
    summary: dict[str, Any],
    artifact_hash: str,
) -> dict[str, Any]:
    approval = {
        "action": action,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "artifact_hash": artifact_hash,
        "summary": summary,
    }
    state["approval"] = approval
    return approval


def require_approval(state: dict[str, Any], action: str, artifact_hash: str) -> dict[str, Any]:
    approval = state.get("approval") or {}
    if approval.get("action") != action:
        raise AgentError(
            "approval_required",
            f"{action} 前必须先获取用户确认",
            f"run_{action.replace('.', '_')}_approve",
        )
    if approval.get("artifact_hash") != artifact_hash:
        raise AgentError(
            "approval_stale",
            "审批对应的 artifact 已过期，请重新 validate 并确认",
            "rerun_validate_and_approve",
        )
    return approval


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if row.get(key) not in (None, "", [], {})}


def build_training_submit_summary(state: dict[str, Any]) -> dict[str, Any]:
    selection = state.get("selection") or {}
    validation = state.get("validation") or {}
    return {
        "action": TRAIN_SUBMIT_ACTION,
        "run_id": state.get("run_id"),
        "scenario": state.get("scenario"),
        "workspace_id": state.get("workspace_id"),
        "task_name": selection.get("task_name"),
        "cards": selection.get("cards"),
        "batch_size": validation.get("batch_size"),
        "training_overrides": validation.get("overrides") or [],
        "training_context": state.get("training_context") or {},
        "train_yaml": (state.get("artifacts") or {}).get("train_yaml"),
        "artifact_hash": state.get("artifact_hash"),
        "model": _pick(
            selection.get("model") or {},
            ("index", "asset_id", "model_id", "asset_name", "asset_type", "sub_asset_type"),
        ),
        "dataset": _pick(
            selection.get("dataset") or {},
            ("index", "dataset_id", "id", "name", "catalog", "content_type"),
        ),
        "pool": _pick(
            selection.get("pool") or {},
            ("index", "pool_id", "pool_name", "chip_type", "processor", "arch", "pool_type"),
        ),
    }


def build_deploy_submit_summary(state: dict[str, Any]) -> dict[str, Any]:
    selection = state.get("selection") or {}
    return {
        "action": DEPLOY_SUBMIT_ACTION,
        "run_id": state.get("run_id"),
        "workspace_id": state.get("workspace_id"),
        "asset_id": state.get("asset_id"),
        "service_name": selection.get("service_name"),
        "access_mode": selection.get("access_mode"),
        "instances": selection.get("instances"),
        "deploy_yaml": (state.get("artifacts") or {}).get("deploy_yaml"),
        "artifact_hash": state.get("artifact_hash"),
        "deploy_option": _pick(
            selection.get("deploy_option") or {},
            ("index", "action_type", "arch", "chip_types", "spec"),
        ),
        "pool": _pick(
            selection.get("pool") or {},
            ("index", "pool_id", "pool_name", "chip_type", "processor", "arch", "pool_type"),
        ),
    }
