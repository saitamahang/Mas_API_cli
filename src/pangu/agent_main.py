"""Agent-safe CLI entrypoint for Pangu workflows."""

from __future__ import annotations

import os
import json
import shutil
import time
import traceback
from importlib.metadata import version as get_version
from pathlib import Path
from typing import Any, List, Optional

import typer

from pangu.adapters import get_pool_adapter
from pangu.adapters.base import PoolRequest
from pangu.agent.approval import (
    DEPLOY_SUBMIT_ACTION,
    DEPLOY_SUBMIT_CONFIRM,
    PUBLISH_MODEL_CONFIRM,
    TRAIN_SUBMIT_ACTION,
    TRAIN_SUBMIT_CONFIRM,
    build_deploy_submit_summary,
    build_training_submit_summary,
    record_approval,
    require_approval,
    require_confirmation,
)
from pangu.agent.candidates import DEFAULT_PAGE_SIZE, candidate_page, page_metadata
from pangu.agent.datasets import (
    DATASET_JOB_FAILURE_STATUSES,
    READY_DATASET_STATUS,
    dataset_identifier,
    extract_job_id,
    find_matching_dataset,
    validate_training_dataset_ready,
)
from pangu.agent.errors import AgentError
from pangu.agent.goals import (
    DATASET_READY,
    DEPLOYMENT_SUBMITTED,
    MODEL_PUBLISHED,
    SERVICE_RUNNING,
    TRAINING_COMPLETED,
    TRAINING_SUBMITTED,
    normalize_goal,
    transient_goal_state,
    with_goal_next_action,
)
from pangu.agent.monitor_contract import apply_status_monitor_contract, apply_submit_monitor_contract, monitor_submit_fields
from pangu.agent.published_assets import flatten_asset_ext, published_asset_query, select_published_asset
from pangu.agent.scenarios import get_scenario, list_scenarios
from pangu.agent.state import (
    RUNS_DIR,
    base_state,
    gc_runs,
    load_state,
    load_yaml,
    save_state,
    select_index,
    sha256_file,
    yaml_has_todo,
)
from pangu.agent.training_params import (
    list_training_parameters_from_body,
    resolve_training_override_from_body,
    resolve_training_param_overrides_from_body,
)
from pangu.agent.training_context import expected_training_context, validate_training_context
from pangu.agent.utils import extract_first_json, failure, print_json, run_quietly, success
from pangu.agent_monitor.models import MONITOR_CANCELLED
from pangu.agent_monitor.runner import monitor_message, retry_delivery, run_monitor, start_detached_monitor
from pangu.agent_monitor.status import monitor_task_from_run
from pangu.agent_monitor.store import list_monitors, load_monitor, save_monitor
from pangu.auth import AuthManager
from pangu.client import APIError, PanguClient
from pangu.commands.model import DETAIL_PATH as MODEL_DETAIL_PATH, _extract_resource_info
from pangu.commands.service import DETAIL_PATH as SERVICE_DETAIL_PATH, deploy_service, scaffold_deploy
from pangu.commands.training import create_task, publish_model, scaffold as training_scaffold
from pangu.config import PanguConfig


try:
    __version__ = get_version("pangu-cli")
except Exception:
    __version__ = "0.2.0"


app = typer.Typer(
    name="pangu-agent",
    help="Agent-safe workflows for Pangu dataset, training, and deployment operations.",
    no_args_is_help=True,
)
dataset_app = typer.Typer(help="Agent-safe dataset workflows")
train_app = typer.Typer(help="Agent-safe training workflows")
deploy_app = typer.Typer(help="Agent-safe deployment workflows")
monitor_app = typer.Typer(help="Async monitors for long-running agent workflows")
skill_app = typer.Typer(help="Manage Claude Code skill files")
app.add_typer(dataset_app, name="dataset")
app.add_typer(train_app, name="train")
app.add_typer(deploy_app, name="deploy")
app.add_typer(monitor_app, name="monitor")
app.add_typer(skill_app, name="skill")


MODEL_EXT_PATH = "/v1/{project_id}/workspaces/{workspace_id}/asset-manager/model-assets-ext"
DATASET_LIST_PATH = "/v2/{project_id}/workspaces/{workspace_id}/data-management/datasets"
DATASET_DETAIL_PATH = "/v1/{project_id}/workspaces/{workspace_id}/data-management/dataset/{dataset_name}"
IMPORT_JOBS_PATH = "/v1/{project_id}/workspaces/{workspace_id}/data-extraction/import-jobs"
PUBLISH_JOBS_PATH = "/v1/{project_id}/workspaces/{workspace_id}/data-publish/jobs"
TRAIN_TASK_PATH = "/v1/{project_id}/workspaces/{workspace_id}/model-train/train-task/{task_id}"
TRAIN_MODELS_PATH = "/v1/{project_id}/workspaces/{workspace_id}/model-train/models"


def _emit(factory):
    try:
        print_json(success(**factory()))
    except AgentError as e:
        print_json(failure(e))
        raise typer.Exit(1)
    except APIError as e:
        err = AgentError("api_error", str(e), "inspect_api_error")
        print_json(failure(err))
        raise typer.Exit(1)
    except Exception as e:
        err = AgentError("unexpected_error", f"{type(e).__name__}: {e}", "inspect_error")
        data = failure(err)
        if os.environ.get("PANGU_AGENT_DEBUG"):
            data["traceback"] = traceback.format_exc()
        print_json(data)
        raise typer.Exit(1)


def _config_and_client(workspace: Optional[str] = None) -> tuple[PanguConfig, PanguClient, str]:
    config = PanguConfig.load()
    try:
        workspace_id = config.get_workspace_id(workspace)
    except Exception as e:
        raise AgentError("missing_workspace", str(e), "set_default_workspace_or_pass_workspace") from e
    return config, PanguClient(config), workspace_id


def _training_status_value(data: dict[str, Any]) -> str:
    return str(data.get("task_status") or data.get("status") or "").lower()


def _service_status_value(data: dict[str, Any]) -> str:
    return str(data.get("status") or data.get("service_status") or "").lower()


def _goal_state(
    run_id: Optional[str],
    expected_kind: str,
    goal: Optional[str],
    default_goal: str,
) -> dict[str, Any]:
    if not run_id:
        return transient_goal_state(expected_kind, goal, default_goal)
    state = load_state(run_id, expected_kind=expected_kind)
    if goal:
        state["goal"] = normalize_goal(goal, default_goal)
        save_state(state)
    return state


def _query_models(client: PanguClient, workspace_id: str, scenario: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    mq = scenario["model_query"]
    params = {
        "limit": limit,
        "offset": 0,
        "asset_source": mq["source"],
        "asset_type": mq["type"],
        "sub_asset_type": mq["sub_type"],
    }
    if mq.get("asset_action"):
        params["asset_action"] = mq["asset_action"]
    data = client.get(MODEL_EXT_PATH, workspace_id=workspace_id, params=params)
    assets = (data.get("assets") if isinstance(data, dict) else None) or []
    rows = []
    for idx, item in enumerate(assets, start=1):
        if not isinstance(item, dict):
            continue
        row = flatten_asset_ext(item)
        row["index"] = idx
        rows.append(row)
    return rows


def _asset_id(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    return str(row.get("asset_id") or row.get("id") or "")


def _deploy_plan_command(asset_id: str, goal: str | None = None) -> str:
    if not asset_id:
        return ""
    goal_part = f" --goal {goal}" if goal else ""
    return f"pangu-agent deploy plan --asset-id {asset_id}{goal_part} --page-size 20 --json"


def _monitor_adapter(adapter: str | None) -> str:
    value = adapter or os.environ.get("PANGU_MONITOR_ADAPTER", "") or PanguConfig.load().monitor_adapter
    if not value:
        raise AgentError(
            "missing_monitor_adapter",
            "缺少 monitor adapter，请设置 PANGU_MONITOR_ADAPTER 或 pangu config set monitor_adapter <adapter>",
            "configure_monitor_adapter",
        )
    return value


def _monitor_session(
    *,
    session_id: str | None = None,
    session_json: str | None = None,
    session_file: Path | None = None,
) -> dict[str, Any]:
    session: dict[str, Any] = {}
    if session_file:
        try:
            session = json.loads(session_file.read_text(encoding="utf-8"))
        except Exception as e:
            raise AgentError("invalid_monitor_session_file", str(e), "pass_valid_session_file") from e
    if session_json:
        try:
            parsed = json.loads(session_json)
        except json.JSONDecodeError as e:
            raise AgentError("invalid_monitor_session_json", str(e), "pass_valid_session_json") from e
        if not isinstance(parsed, dict):
            raise AgentError("invalid_monitor_session_json", "session-json 必须是 JSON object", "pass_valid_session_json")
        session.update(parsed)

    env_session_id = os.environ.get("PANGU_MONITOR_SESSION_ID")
    if session_id or env_session_id:
        session["session_id"] = session_id or env_session_id
    if not session.get("session_id"):
        raise AgentError("missing_monitor_session", "缺少 monitor session_id", "pass_session_id_or_set_env")
    return session


def _create_detached_monitor_from_run(
    *,
    run_id: str,
    session_id: str | None = None,
    interval: int = 60,
    timeout: int = 86400,
) -> dict[str, Any]:
    task = monitor_task_from_run(
        run_id=run_id,
        adapter=_monitor_adapter(None),
        session=_monitor_session(session_id=session_id),
        interval_seconds=interval,
        timeout_seconds=timeout,
    )
    save_monitor(task)
    detach_info = start_detached_monitor(task.monitor_id)
    return {
        "monitor_id": task.monitor_id,
        "monitor_task": task.to_dict(),
        "detached": bool(detach_info),
        "detach": detach_info,
        "next_action": "stop_waiting_in_main_session",
    }


def _attach_submit_monitor(
    result: dict[str, Any],
    *,
    run_id: str,
    monitor: bool,
    session_id: str | None,
) -> dict[str, Any]:
    session_available = bool(session_id or os.environ.get("PANGU_MONITOR_SESSION_ID"))
    if not monitor and not (result.get("monitor_required") and session_available):
        result["monitor_created"] = False
        return result

    monitor_info = _create_detached_monitor_from_run(run_id=run_id, session_id=session_id)
    result.update(monitor_info)
    result["monitor_created"] = True
    result["main_session_polling_allowed"] = False
    result["terminal"] = False
    return result


def _resolve_published_asset(
    client: PanguClient,
    workspace_id: str,
    *,
    model_id: str | None = None,
    asset_name: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    query_plans: list[dict[str, Any]] = []
    query_plans.append(published_asset_query(asset_name, current_workspace=True))
    query_plans.append(published_asset_query(asset_name, current_workspace=False))
    if asset_name:
        query_plans.append({"limit": 1000, "offset": 0, "asset_name": asset_name})

    seen: set[tuple[tuple[str, str], ...]] = set()
    candidates: list[dict[str, Any]] = []
    for params in query_plans:
        key = tuple(sorted((str(k), str(v)) for k, v in params.items()))
        if key in seen:
            continue
        seen.add(key)
        data = client.get(MODEL_EXT_PATH, workspace_id=workspace_id, params=params)
        assets = (data.get("assets") if isinstance(data, dict) else None) or []
        rows = [flatten_asset_ext(item) for item in assets if isinstance(item, dict)]
        if rows and not candidates:
            candidates = rows
        selected = select_published_asset(rows, model_id=model_id, asset_name=asset_name)
        if selected:
            return selected, rows
    return None, candidates


def _query_datasets(
    client: PanguClient,
    workspace_id: str,
    scenario: dict[str, Any],
    catalog: str,
    limit: int = 100,
    name: Optional[str] = None,
    status: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    ds = scenario["dataset"]
    content_type = (
        ds.get("publish", {}).get("file_content_type")
        if catalog == ds.get("training_catalog")
        else ds.get("import", {}).get("content_type")
    )
    params = {
        "limit": limit,
        "offset": 0,
        "sort_by": "create_time",
        "sort_type": "desc",
        "mine": "false",
        "show_deleted": "false",
        "catalog": catalog,
        "modal": ds["modal"],
        "content_type": [content_type],
    }
    if name:
        params["name"] = name
    if status:
        params["status"] = status
    data = client.get(DATASET_LIST_PATH, workspace_id=workspace_id, params=params)
    datasets = (data.get("datasets") if isinstance(data, dict) else None) or []
    rows = []
    for idx, item in enumerate(datasets, start=1):
        if isinstance(item, dict):
            row = dict(item)
            row["index"] = idx
            rows.append(row)
    return rows


def _get_dataset_detail(
    client: PanguClient,
    workspace_id: str,
    *,
    name: str,
    catalog: str,
) -> dict[str, Any]:
    data = client.get(
        DATASET_DETAIL_PATH,
        workspace_id=workspace_id,
        params={"catalog": catalog},
        dataset_name=name,
    )
    if not isinstance(data, dict):
        return {}
    row = dict(data)
    row.setdefault("name", name)
    row.setdefault("catalog", catalog)
    return row


def _query_pools(
    client: PanguClient,
    workspace_id: str,
    env_type: str,
    purpose: str = "train",
    chip_types: Optional[list[str]] = None,
    arch: Optional[str] = None,
    edge: bool = False,
) -> list[dict[str, Any]]:
    adapter = get_pool_adapter(env_type)
    if edge:
        req = PoolRequest(
            arch=arch or "ARM",
            job_type=None,
            chip_types=chip_types or None,
            is_edge=True,
        )
    elif env_type == "HC":
        req = PoolRequest(
            job_type="train" if purpose == "train" else "infer",
            chip_types=chip_types or ["D910B3"],
            use_type="private",
        )
    else:
        req = PoolRequest(
            arch=arch or "ARM",
            job_type="Train" if purpose == "train" else "Infer",
            chip_types=chip_types or None,
        )
    body = adapter.build_request(req)
    path = getattr(adapter, "edge_path", adapter.path) if edge else adapter.path
    if adapter.workspace_in_path:
        data = client.post(path, workspace_id=workspace_id, json=body)
    else:
        extra_headers = adapter.extra_headers(workspace_id)
        data = client.post(path, workspace_id=None, json=body, extra_headers=extra_headers)
    rows = []
    for idx, item in enumerate(adapter.normalize(data), start=1):
        row = dict(item)
        row["index"] = idx
        rows.append(row)
    return rows


def _find_ready_training_dataset(
    client: PanguClient,
    workspace_id: str,
    scenario: dict[str, Any],
    *,
    dataset_id: str = "",
    name: str = "",
    limit: int = 1000,
) -> dict[str, Any] | None:
    training_catalog = scenario["dataset"]["training_catalog"]
    if name:
        try:
            detail = _get_dataset_detail(client, workspace_id, name=name, catalog=training_catalog)
        except APIError:
            detail = {}
        if detail:
            detail_id = dataset_identifier(detail)
            if dataset_id and detail_id and detail_id != dataset_id:
                return None
            try:
                return validate_training_dataset_ready(detail, scenario)
            except AgentError:
                return None

    rows = _query_datasets(
        client,
        workspace_id,
        scenario,
        catalog=training_catalog,
        limit=limit,
        name=name or None,
        status=[READY_DATASET_STATUS],
    )
    match = find_matching_dataset(rows, dataset_id=dataset_id, name=name)
    if not match:
        return None
    return validate_training_dataset_ready(match, scenario)


def _ensure_training_dataset_ready(
    client: PanguClient,
    workspace_id: str,
    scenario: dict[str, Any],
    dataset_row: dict[str, Any],
) -> dict[str, Any]:
    dataset_id = dataset_identifier(dataset_row)
    name = str(dataset_row.get("name") or "")
    ready = _find_ready_training_dataset(
        client,
        workspace_id,
        scenario,
        dataset_id=dataset_id,
        name=name,
    )
    if not ready:
        raise AgentError(
            "dataset_not_ready_for_training",
            "所选数据集不是 ONLINE 的 PUBLISH 数据集，不能用于训练",
            "dataset.publish-wait_or_choose_ready_dataset",
            {
                "dataset": {
                    "id": dataset_id,
                    "name": name,
                    "catalog": dataset_row.get("catalog"),
                    "status": dataset_row.get("status"),
                    "content_type": dataset_row.get("content_type"),
                },
                "expected": {
                    "catalog": scenario["dataset"]["training_catalog"],
                    "status": READY_DATASET_STATUS,
                    "content_type": scenario["dataset"].get("publish", {}).get("file_content_type"),
                },
            },
        )
    if dataset_row.get("index") is not None:
        ready = dict(ready)
        ready["index"] = dataset_row["index"]
    return ready


def _wait_for_published_dataset(
    client: PanguClient,
    workspace_id: str,
    scenario: dict[str, Any],
    publish_name: str,
    *,
    job_id: str = "",
    interval: int = 10,
    timeout: int = 3600,
) -> dict[str, Any]:
    if interval < 1:
        raise AgentError("invalid_wait_interval", "interval 必须大于等于 1", "pass_valid_wait_interval")
    if timeout < 1:
        raise AgentError("invalid_wait_timeout", "timeout 必须大于等于 1", "pass_valid_wait_timeout")

    deadline = time.time() + timeout
    publish_status = None
    while True:
        ready = _find_ready_training_dataset(client, workspace_id, scenario, name=publish_name)
        if ready:
            return {
                "publish_request": {"id": job_id},
                "publish_status": publish_status,
                "dataset": ready,
            }
        if job_id:
            try:
                publish_status = client.get(PUBLISH_JOBS_PATH + f"/{job_id}", workspace_id=workspace_id)
            except APIError as e:
                publish_status = {"status_check_error": str(e)}
            if isinstance(publish_status, dict) and publish_status.get("status") in DATASET_JOB_FAILURE_STATUSES:
                raise AgentError(
                    "dataset_publish_failed",
                    f"发布请求进入失败状态: {publish_status.get('status')}",
                    "inspect_dataset_publish_status",
                    {"publish_name": publish_name, "publish_request_id": job_id, "publish_status": publish_status},
                )
        remaining = deadline - time.time()
        if remaining <= 0:
            raise AgentError(
                "dataset_publish_timeout",
                f"等待发布数据集 ONLINE 超时: {publish_name}",
                "retry_dataset_publish_wait_or_inspect_publish_status",
                {
                    "publish_name": publish_name,
                    "publish_request_id": job_id,
                    "timeout": timeout,
                    "publish_status": publish_status,
                },
            )
        time.sleep(min(interval, remaining))


def _normalize_obs_path(obs_path: str) -> str:
    if obs_path.startswith("obs://"):
        return obs_path[len("obs://"):]
    return obs_path


def _training_artifact_path(run_id: str) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.chmod(0o700)
    return RUNS_DIR / f"{run_id}.train.yaml"


def _deploy_artifact_path(run_id: str) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.chmod(0o700)
    return RUNS_DIR / f"{run_id}.deploy.yaml"


def _require_artifact_hash(state: dict[str, Any], artifact_key: str) -> Path:
    if not state.get("validate_success"):
        raise AgentError("submit_without_validate", "submit 前必须先 validate 成功", "run_validate")
    path = Path(state.get("artifacts", {}).get(artifact_key) or "")
    if not path.exists():
        raise AgentError("artifact_missing", f"找不到 artifact: {path}", "rerun_scaffold")
    actual = sha256_file(path)
    expected = state.get("artifact_hash")
    if actual != expected:
        raise AgentError("artifact_changed_after_validate", "artifact 在 validate 后发生变化", "rerun_validate")
    return path


def _resolve_training_override(
    artifact: Path,
    scenario: dict[str, Any],
    param_key: str,
    value: Any,
) -> tuple[str, str]:
    body = load_yaml(artifact)
    return resolve_training_override_from_body(body, scenario, param_key, value)


def _resolve_training_overrides(
    artifact: Path,
    scenario: dict[str, Any],
    batch_size: Optional[int],
    override_params: Optional[List[str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    body = load_yaml(artifact)
    overrides = resolve_training_param_overrides_from_body(body, override_params)
    batch_param_names = set(scenario["training"].get("batch_size_param_names") or ["batch_size"])
    batch_records = [item for item in overrides if item.get("param") in batch_param_names]
    if batch_size is not None and batch_records:
        raise AgentError(
            "duplicate_training_param_override",
            "不能同时使用 --batch-size 和 --param 覆盖 batch size",
            "choose_batch_size_or_param_not_both",
            {"batch_size_params": sorted(batch_param_names)},
        )
    if batch_records:
        batch_param = str(batch_records[0]["param"])
        bs = batch_records[0]["value"]
    else:
        bs = batch_size if batch_size is not None else scenario["training"].get("default_batch_size", 1)
        batch_param, batch_override = resolve_training_override_from_body(body, scenario, "batch_size", bs)
        overrides.append(
            {
                "input": "--batch-size" if batch_size is not None else "scenario.default_batch_size",
                "param": batch_param,
                "value": bs,
                "override": batch_override,
            }
        )
    validation = {
        "batch_size": bs,
        "batch_size_param": batch_param,
        "override_params": [str(item["override"]) for item in overrides],
        "overrides": [
            {
                "param": item["param"],
                "value": item["value"],
                "source": item["input"],
            }
            for item in overrides
        ],
    }
    return overrides, validation


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility")):
    """Check config/auth state before any agent workflow."""
    try:
        config = PanguConfig.load()
        auth = AuthManager(config).status()
        missing_config = config.validate_required("endpoint", "project_id")
        if config.auth_mode == "token":
            auth_ok = bool(auth.get("valid"))
        else:
            auth_ok = bool(auth.get("configured"))
        ready = not missing_config and bool(config.default_workspace_id) and auth_ok
        result = {
            "ok": ready,
            "code": "" if ready else "doctor_not_ready",
            "message": "Pangu 环境已就绪" if ready else "Pangu 环境未就绪",
            "version": __version__,
            "auth": auth,
            "config": {
                "endpoint_configured": bool(config.endpoint),
                "modelarts_endpoint_configured": bool(config.modelarts_endpoint),
                "iam_endpoint_configured": bool(config.iam_endpoint),
                "project_id_configured": bool(config.project_id),
                "default_workspace_id": config.default_workspace_id,
                "env_type": config.env_type,
                "ssl_verify": config.ssl_verify,
                "use_system_proxy": config.use_system_proxy,
                "proxy_configured": bool(config.proxy),
            },
            "missing_config": missing_config,
            "next_action": "scenarios" if ready else "fix_config_or_auth",
        }
        print_json(result)
        if not ready:
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        print_json(failure(AgentError("doctor_failed", f"{type(e).__name__}: {e}", "inspect_config")))
        raise typer.Exit(1)


@app.command("scenarios")
def scenarios(json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility")):
    """List supported agent-safe scenarios."""
    _emit(lambda: {"scenarios": list_scenarios(), "next_action": "choose_scenario"})


@app.command("gc")
def gc(max_age_hours: int = typer.Option(24, "--max-age-hours")):
    """Delete expired local agent run states."""
    _emit(lambda: {**gc_runs(max_age_hours=max_age_hours), "next_action": "continue"})


@app.command("candidates")
def candidates(
    run_id: str = typer.Option(..., "--run-id"),
    kind: str = typer.Option(..., "--kind", help="models|datasets|sources|pools|deploy_options"),
    page: int = typer.Option(1, "--page"),
    page_size: int = typer.Option(DEFAULT_PAGE_SIZE, "--page-size"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Return one compact page of candidates saved in a run state."""

    def run():
        state = load_state(run_id)
        rows = state.get(kind)
        if not isinstance(rows, list):
            raise AgentError("candidate_kind_not_found", f"run state 中没有候选列表: {kind}", "choose_kind_from_plan_output")
        page_data = candidate_page(kind, rows, page=page, page_size=page_size)
        return with_goal_next_action(state, {
            "run_id": run_id,
            "state_kind": state.get("kind"),
            **page_data,
        }, continue_action="choose_index_or_page_more" if page_data["has_more"] else "choose_index")

    _emit(run)


@dataset_app.command("list")
def dataset_list(
    scenario: str = typer.Option(..., "--scenario"),
    catalog: str = typer.Option("PUBLISH", "--catalog"),
    name: Optional[str] = typer.Option(None, "--name", help="按数据集名称模糊过滤"),
    limit: int = typer.Option(1000, "--limit"),
    page: int = typer.Option(1, "--page"),
    page_size: int = typer.Option(DEFAULT_PAGE_SIZE, "--page-size"),
    goal: Optional[str] = typer.Option(None, "--goal", help="Workflow goal boundary"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """List datasets using scenario-defined filters."""

    def run():
        scn = get_scenario(scenario)
        config, client, workspace_id = _config_and_client(workspace)
        status = [READY_DATASET_STATUS] if catalog == scn["dataset"]["training_catalog"] else None
        rows = _query_datasets(client, workspace_id, scn, catalog=catalog, limit=limit, name=name, status=status)
        state = base_state("dataset_list", scenario, config.env_type, workspace_id, goal=goal)
        state["catalog"] = catalog
        state["filters"] = {"name": name, "limit": limit, "status": status}
        state["datasets"] = rows
        save_state(state)
        page_data = candidate_page("datasets", rows, page=page, page_size=page_size)
        return with_goal_next_action(state, {
            "run_id": state["run_id"],
            "scenario": scenario,
            "catalog": catalog,
            "filters": state["filters"],
            **page_data,
            "next_page_command": (
                f"pangu-agent candidates --run-id {state['run_id']} --kind datasets "
                f"--page {page + 1} --page-size {page_data['page_size']} --json"
                if page_data["has_more"] else ""
            ),
        }, continue_action="choose_dataset_or_page_more" if rows else "dataset_import_or_publish_required")

    _emit(run)


@dataset_app.command("import-validate")
def dataset_import_validate(
    scenario: str = typer.Option(..., "--scenario"),
    name: str = typer.Option(..., "--name"),
    obs_path: str = typer.Option(..., "--obs-path"),
    desc: Optional[str] = typer.Option(None, "--desc"),
    goal: Optional[str] = typer.Option(None, "--goal", help="Workflow goal boundary"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
):
    """Build and cache a dataset import request without submitting it."""

    def run():
        scn = get_scenario(scenario)
        config, _, workspace_id = _config_and_client(workspace)
        imp = scn["dataset"]["import"]
        body = {
            "name": name,
            "obs_path": _normalize_obs_path(obs_path),
            "content_type": imp["content_type"],
            "file_format": imp["file_format"],
            "file_source": imp.get("file_source", "OBS"),
        }
        if desc:
            body["desc"] = desc
        state = base_state("dataset_import", scenario, config.env_type, workspace_id, goal=goal)
        state["request_body"] = body
        save_state(state)
        return with_goal_next_action(state, {
            "run_id": state["run_id"],
            "request_body": body,
        }, continue_action="dataset.import-submit")

    _emit(run)


@dataset_app.command("import-submit")
def dataset_import_submit(
    run_id: str = typer.Option(..., "--run-id"),
    wait: bool = typer.Option(False, "--wait"),
):
    """Submit a previously validated dataset import request."""

    def run():
        state = load_state(run_id, expected_kind="dataset_import")
        _, client, workspace_id = _config_and_client(state.get("workspace_id"))
        data = client.post(IMPORT_JOBS_PATH, workspace_id=workspace_id, json=state["request_body"])
        job_id = data.get("id", "") if isinstance(data, dict) else ""
        final = None
        if wait and job_id:
            final = client.wait_for_status(
                IMPORT_JOBS_PATH + f"/{job_id}",
                target_statuses=["SUCCESS"],
                failure_statuses=["FAILED", "STOPPED"],
                status_key="status",
                workspace_id=workspace_id,
            )
        state["submit_result"] = data
        save_state(state)
        return with_goal_next_action(
            state,
            {"job": data, "final": final},
            continue_action="dataset.publish-prepare",
        )

    _emit(run)


@dataset_app.command("publish-prepare")
def dataset_publish_prepare(
    scenario: str = typer.Option(..., "--scenario"),
    source_catalog: str = typer.Option("ORIGINAL", "--source-catalog"),
    name: Optional[str] = typer.Option(None, "--name", help="按源数据集名称模糊过滤"),
    limit: int = typer.Option(1000, "--limit"),
    page: int = typer.Option(1, "--page"),
    page_size: int = typer.Option(DEFAULT_PAGE_SIZE, "--page-size"),
    goal: Optional[str] = typer.Option(None, "--goal", help="Workflow goal boundary"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Query source datasets and cache indexed candidates for publishing."""

    def run():
        scn = get_scenario(scenario)
        config, client, workspace_id = _config_and_client(workspace)
        sources = _query_datasets(
            client,
            workspace_id,
            scn,
            catalog=source_catalog,
            limit=limit,
            name=name,
            status=[READY_DATASET_STATUS],
        )
        state = base_state("dataset_publish", scenario, config.env_type, workspace_id, goal=goal)
        state["source_catalog"] = source_catalog
        state["filters"] = {"name": name, "limit": limit, "status": [READY_DATASET_STATUS]}
        state["sources"] = sources
        save_state(state)
        page_data = candidate_page("sources", sources, page=page, page_size=page_size)
        return with_goal_next_action(state, {
            "run_id": state["run_id"],
            "scenario": scenario,
            "source_catalog": source_catalog,
            "filters": state["filters"],
            **page_data,
            "next_page_command": (
                f"pangu-agent candidates --run-id {state['run_id']} --kind sources "
                f"--page {page + 1} --page-size {page_data['page_size']} --json"
                if page_data["has_more"] else ""
            ),
        }, continue_action="choose_sources_or_page_more" if sources else "dataset.import-validate")

    _emit(run)


@dataset_app.command("publish-validate")
def dataset_publish_validate(
    run_id: str = typer.Option(..., "--run-id"),
    publish_name: str = typer.Option(..., "--publish-name"),
    source: List[int] = typer.Option(..., "--source", help="Source dataset index; repeat for multiple datasets"),
    train_proportion: Optional[float] = typer.Option(None, "--train-proportion"),
    description: Optional[str] = typer.Option(None, "--description", "-d"),
):
    """Build and cache a dataset publish request without submitting it."""

    def run():
        state = load_state(run_id, expected_kind="dataset_publish")
        scn = get_scenario(state["scenario"])
        pub = scn["dataset"]["publish"]
        if train_proportion is None:
            train_proportion_value = pub.get("default_train_proportion")
        else:
            train_proportion_value = train_proportion
        if pub.get("require_train_proportion") and train_proportion_value is None:
            raise AgentError(
                "train_proportion_required",
                "该场景发布数据集需要 train_proportion",
                "pass_train_proportion",
            )
        datasets_payload = []
        for idx in source:
            item = select_index(state, "sources", idx)
            datasets_payload.append({
                "dataset_id": item.get("dataset_id") or item.get("id", ""),
                "dataset_name": item.get("name"),
                "catalog": state["source_catalog"],
            })
        body = {
            "job_type": "CIRCULATION",
            "publish_name": publish_name,
            "file_content_type": pub["file_content_type"],
            "publish_format": pub.get("publish_format", "PANGU"),
            "is_global": False,
            "datasets": datasets_payload,
        }
        if description:
            body["description"] = description
        if train_proportion_value is not None:
            body["train_proportion"] = train_proportion_value
        state["request_body"] = body
        state["validate_success"] = True
        save_state(state)
        return with_goal_next_action(state, {
            "run_id": run_id,
            "request_body": body,
        }, continue_action="dataset.publish-submit")

    _emit(run)


@dataset_app.command("publish-submit")
def dataset_publish_submit(
    run_id: str = typer.Option(..., "--run-id"),
    wait: bool = typer.Option(False, "--wait"),
    interval: int = typer.Option(10, "--interval"),
    timeout: int = typer.Option(3600, "--timeout"),
):
    """Submit a previously validated dataset publish request."""

    def run():
        state = load_state(run_id, expected_kind="dataset_publish")
        if not state.get("validate_success"):
            raise AgentError("submit_without_validate", "publish-submit 前必须先 publish-validate", "run_publish_validate")
        scn = get_scenario(state["scenario"])
        _, client, workspace_id = _config_and_client(state.get("workspace_id"))
        data = client.post(PUBLISH_JOBS_PATH, workspace_id=workspace_id, json=state["request_body"])
        job_id = extract_job_id(data)
        final = None
        ready_dataset = None
        if wait:
            final = _wait_for_published_dataset(
                client,
                workspace_id,
                scn,
                state["request_body"]["publish_name"],
                job_id=job_id,
                interval=interval,
                timeout=timeout,
            )
            ready_dataset = final["dataset"]
        state["submit_result"] = data
        state["job_id"] = job_id
        state["publish_request_id"] = job_id
        if final:
            state["final"] = final
        if ready_dataset:
            state["published_dataset"] = ready_dataset
        save_state(state)
        return with_goal_next_action(
            state,
            {
                "publish_request": data,
                "publish_request_id": job_id,
                "final": final,
                "published_dataset": ready_dataset,
                "wait_command": "" if ready_dataset else f"pangu-agent dataset publish-wait --run-id {run_id} --json",
            },
            milestone=DATASET_READY if ready_dataset else None,
            continue_action="train.plan" if ready_dataset else "dataset.publish-wait",
        )

    _emit(run)


@dataset_app.command("publish-status")
def dataset_publish_status(
    run_id: str = typer.Option(..., "--run-id"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Check a submitted dataset publish request and published dataset readiness."""

    def run():
        state = load_state(run_id, expected_kind="dataset_publish")
        if not state.get("submit_result"):
            raise AgentError("publish_not_submitted", "发布任务尚未提交", "run_dataset_publish_submit")
        scn = get_scenario(state["scenario"])
        _, client, workspace_id = _config_and_client(state.get("workspace_id"))
        publish_request_id = state.get("publish_request_id") or state.get("job_id") or extract_job_id(state.get("submit_result"))
        publish_status = None
        if publish_request_id:
            try:
                publish_status = client.get(PUBLISH_JOBS_PATH + f"/{publish_request_id}", workspace_id=workspace_id)
            except APIError as e:
                publish_status = {"status_check_error": str(e)}
        publish_name = state["request_body"]["publish_name"]
        ready_dataset = _find_ready_training_dataset(client, workspace_id, scn, name=publish_name)
        if ready_dataset:
            state["published_dataset"] = ready_dataset
            save_state(state)
        return with_goal_next_action(
            state,
            {
                "run_id": run_id,
                "publish_request_id": publish_request_id,
                "publish_status": publish_status,
                "dataset_ready": bool(ready_dataset),
                "published_dataset": ready_dataset,
            },
            milestone=DATASET_READY if ready_dataset else None,
            continue_action="train.plan" if ready_dataset else "dataset.publish-wait",
        )

    _emit(run)


@dataset_app.command("publish-wait")
def dataset_publish_wait(
    run_id: str = typer.Option(..., "--run-id"),
    interval: int = typer.Option(10, "--interval"),
    timeout: int = typer.Option(3600, "--timeout"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Wait until a submitted dataset publish request produces an ONLINE PUBLISH dataset."""

    def run():
        state = load_state(run_id, expected_kind="dataset_publish")
        if not state.get("submit_result"):
            raise AgentError("publish_not_submitted", "发布任务尚未提交", "run_dataset_publish_submit")
        scn = get_scenario(state["scenario"])
        _, client, workspace_id = _config_and_client(state.get("workspace_id"))
        job_id = state.get("publish_request_id") or state.get("job_id") or extract_job_id(state.get("submit_result"))
        final = _wait_for_published_dataset(
            client,
            workspace_id,
            scn,
            state["request_body"]["publish_name"],
            job_id=job_id,
            interval=interval,
            timeout=timeout,
        )
        state["job_id"] = job_id
        state["publish_request_id"] = job_id
        state["final"] = final
        state["published_dataset"] = final["dataset"]
        save_state(state)
        return with_goal_next_action(
            state,
            {
                "run_id": run_id,
                "publish_request_id": job_id,
                "final": final,
                "published_dataset": final["dataset"],
            },
            milestone=DATASET_READY,
            continue_action="train.plan",
        )

    _emit(run)


@train_app.command("plan")
def train_plan(
    scenario: str = typer.Option(..., "--scenario"),
    limit: int = typer.Option(1000, "--limit"),
    dataset_name: Optional[str] = typer.Option(None, "--dataset-name", help="按训练数据集名称模糊过滤"),
    page_size: int = typer.Option(DEFAULT_PAGE_SIZE, "--page-size"),
    goal: Optional[str] = typer.Option(None, "--goal", help="Workflow goal boundary"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Query model, dataset, and pool candidates for a training run."""

    def run():
        scn = get_scenario(scenario)
        config, client, workspace_id = _config_and_client(workspace)
        models = _query_models(client, workspace_id, scn, limit=limit)
        datasets = _query_datasets(
            client,
            workspace_id,
            scn,
            catalog=scn["dataset"]["training_catalog"],
            limit=limit,
            name=dataset_name,
            status=[READY_DATASET_STATUS],
        )
        pools = _query_pools(client, workspace_id, config.env_type, purpose="train")
        state = base_state("training", scenario, config.env_type, workspace_id, goal=goal)
        state["models"] = models
        state["datasets"] = datasets
        state["pools"] = pools
        state["filters"] = {"limit": limit, "dataset_name": dataset_name, "dataset_status": [READY_DATASET_STATUS]}
        save_state(state)
        next_action = "choose_model_dataset_pool"
        if not models:
            next_action = "add_or_adjust_model_scenario_profile"
        elif not datasets:
            next_action = "dataset_import_or_publish_required"
        elif not pools:
            next_action = "check_resource_pools"
        model_page = candidate_page("models", models, page=1, page_size=page_size)
        dataset_page = candidate_page("datasets", datasets, page=1, page_size=page_size)
        pool_page = candidate_page("pools", pools, page=1, page_size=page_size)
        return with_goal_next_action(state, {
            "run_id": state["run_id"],
            "scenario": scenario,
            "env_type": config.env_type,
            "workspace_id": workspace_id,
            "filters": state["filters"],
            "models": model_page["models"],
            "datasets": dataset_page["datasets"],
            "pools": pool_page["pools"],
            "candidate_pages": {
                "models": page_metadata("models", models, page=1, page_size=page_size),
                "datasets": page_metadata("datasets", datasets, page=1, page_size=page_size),
                "pools": page_metadata("pools", pools, page=1, page_size=page_size),
            },
            "page_more_command": f"pangu-agent candidates --run-id {state['run_id']} --kind <models|datasets|pools> --page <n> --page-size {page_size} --json",
        }, continue_action=next_action)

    _emit(run)


@train_app.command("scaffold")
def train_scaffold(
    run_id: str = typer.Option(..., "--run-id"),
    model: int = typer.Option(..., "--model", help="Model index from train plan"),
    dataset: int = typer.Option(..., "--dataset", help="Dataset index from train plan"),
    pool: int = typer.Option(..., "--pool", help="Pool index from train plan"),
    task_name: str = typer.Option(..., "--task-name"),
    cards: int = typer.Option(1, "--cards"),
):
    """Generate a training YAML using selected plan candidates."""

    def run():
        state = load_state(run_id, expected_kind="training")
        scn = get_scenario(state["scenario"])
        model_row = select_index(state, "models", model)
        dataset_row = select_index(state, "datasets", dataset)
        pool_row = select_index(state, "pools", pool)
        _, client, workspace_id = _config_and_client(state.get("workspace_id"))
        dataset_row = _ensure_training_dataset_ready(client, workspace_id, scn, dataset_row)
        artifact = _training_artifact_path(run_id)
        env_type = state["env_type"]
        chip_type = pool_row.get("chip_type") or pool_row.get("processor") or ""
        if env_type != "HC" and not chip_type:
            raise AgentError(
                "missing_pool_chip_type",
                "所选资源池没有 chip_type，无法生成 HCS 训练模板",
                "choose_pool_with_chip_type_or_update_pool_adapter",
            )
        output = run_quietly(
            training_scaffold,
            model_id=model_row.get("model_id") or model_row.get("asset_id"),
            model_type=scn["training"]["model_type"],
            train_type=scn["training"]["train_type"],
            model_source=scn["training"]["model_source_detail"],
            create_model_source=scn["training"]["create_model_source"],
            strategy=None,
            asset_id=model_row.get("asset_id"),
            model_name=model_row.get("asset_name"),
            task_name=task_name,
            workspace=state.get("workspace_id"),
            out_file=str(artifact),
            dataset_name=dataset_row.get("name"),
            dataset_catalog=dataset_row.get("catalog") or scn["dataset"]["training_catalog"],
            eval_dataset_name=None,
            eval_dataset_catalog="ORIGINAL",
            pool_id=pool_row.get("pool_id"),
            chip_type=chip_type or None,
            cards=cards,
            nodes=1,
            auto_publish=False,
            asset_name=None,
            publish_desc=None,
            visibility="current",
        )
        state["selection"] = {
            "model": model_row,
            "dataset": dataset_row,
            "pool": pool_row,
            "task_name": task_name,
            "cards": cards,
        }
        body = load_yaml(artifact)
        parameters = list_training_parameters_from_body(body)
        state["training_context"] = {
            "expected": expected_training_context(state),
            "actual": validate_training_context(state, body),
        }
        state["artifacts"]["train_yaml"] = str(artifact)
        state["validate_success"] = False
        state["artifact_hash"] = ""
        state["params_listed"] = False
        state.pop("params_artifact_hash", None)
        state.pop("approval", None)
        save_state(state)
        return with_goal_next_action(state, {
            "run_id": run_id,
            "train_yaml": str(artifact),
            "parameters": parameters,
            "parameter_count": len(parameters),
            "params_command": f"pangu-agent train params --run-id {run_id} --json",
            "wrapped_output": output.strip(),
        }, continue_action="train.params")

    _emit(run)


@train_app.command("params")
def train_params(
    run_id: str = typer.Option(..., "--run-id"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """List editable training parameters from the generated YAML."""

    def run():
        state = load_state(run_id, expected_kind="training")
        artifact = Path(state.get("artifacts", {}).get("train_yaml") or "")
        if not artifact.exists():
            raise AgentError("artifact_missing", "训练 YAML 不存在", "run_train_scaffold")
        body = load_yaml(artifact)
        context = validate_training_context(state, body)
        parameters = list_training_parameters_from_body(body)
        state["params_listed"] = True
        state["params_artifact_hash"] = sha256_file(artifact)
        save_state(state)
        return with_goal_next_action(state, {
            "run_id": run_id,
            "train_yaml": str(artifact),
            "training_context": context,
            "parameters": parameters,
            "parameter_count": len(parameters),
            "param_usage": "pangu-agent train validate --run-id <run_id> --param <index|name>=<json_value>",
        }, continue_action="train.validate")

    _emit(run)


@train_app.command("validate")
def train_validate(
    run_id: str = typer.Option(..., "--run-id"),
    batch_size: Optional[int] = typer.Option(None, "--batch-size"),
    override_params: Optional[List[str]] = typer.Option(None, "--param", help="覆盖训练超参，格式 name=value 或 index=value，可多次传入"),
):
    """Dry-run a generated training YAML and record its artifact hash."""

    def run():
        state = load_state(run_id, expected_kind="training")
        artifact = Path(state.get("artifacts", {}).get("train_yaml") or "")
        if not artifact.exists():
            raise AgentError("artifact_missing", "训练 YAML 不存在", "run_train_scaffold")
        body = load_yaml(artifact)
        artifact_hash = sha256_file(artifact)
        if not state.get("params_listed") or not state.get("params_artifact_hash"):
            raise AgentError(
                "training_params_not_listed",
                "validate 前必须先运行 train params 并向用户展示完整训练参数",
                "run_train_params",
                {"params_command": f"pangu-agent train params --run-id {run_id} --json"},
            )
        if state.get("params_artifact_hash") != artifact_hash:
            raise AgentError(
                "training_params_stale",
                "训练 YAML 在 train params 后发生变化，必须重新列出训练参数",
                "rerun_train_params",
                {"params_command": f"pangu-agent train params --run-id {run_id} --json"},
            )
        context = validate_training_context(state, body)
        scn = get_scenario(state["scenario"])
        _, client, workspace_id = _config_and_client(state.get("workspace_id"))
        _ensure_training_dataset_ready(client, workspace_id, scn, state.get("selection", {}).get("dataset") or {})
        overrides, validation = _resolve_training_overrides(artifact, scn, batch_size, override_params)
        wrapped_override_params = [item["override"] for item in overrides]
        output = run_quietly(
            create_task,
            config=str(artifact),
            name=None,
            description=None,
            asset_id=None,
            model_id=None,
            model_type=None,
            train_type=None,
            model_source=None,
            model_name=None,
            dataset_id=None,
            dataset_name=None,
            dataset_version_id=None,
            eval_dataset_id=None,
            eval_dataset_name=None,
            eval_dataset_version_id=None,
            dataset_split_ratio=None,
            checkpoint_id=None,
            save_checkpoints_max=None,
            restore_training=None,
            sfs_model=None,
            sfs_dataset=None,
            sfs_preload=None,
            pool_id=None,
            pool_type=None,
            chip_type=None,
            flavor_id=None,
            nodes=None,
            flavor=None,
            t_flops=None,
            train_flavor=None,
            plog_level=None,
            is_input_finished=None,
            workspace=state.get("workspace_id"),
            wait=False,
            dry_run=True,
            override_params=wrapped_override_params,
            fmt="yaml",
        )
        state["validate_success"] = True
        state["artifact_hash"] = artifact_hash
        state["validation"] = validation
        state["training_context"] = {
            "expected": expected_training_context(state),
            "actual": context,
        }
        state.pop("approval", None)
        approval_summary = build_training_submit_summary(state)
        save_state(state)
        return with_goal_next_action(state, {
            "run_id": run_id,
            "train_yaml": str(artifact),
            "artifact_hash": state["artifact_hash"],
            "training_context": context,
            "validated_overrides": validation["overrides"],
            "approval_required": True,
            "approval_summary": approval_summary,
            "approval_confirm": TRAIN_SUBMIT_CONFIRM,
            "dry_run_output": output.strip(),
        }, continue_action="ask_user_submit_approval")

    _emit(run)


@train_app.command("approve")
def train_approve(
    run_id: str = typer.Option(..., "--run-id"),
    confirm: Optional[str] = typer.Option(None, "--confirm"),
):
    """Record explicit user approval for a validated training submission."""

    def run():
        state = load_state(run_id, expected_kind="training")
        artifact = _require_artifact_hash(state, "train_yaml")
        validate_training_context(state, load_yaml(artifact))
        require_confirmation(confirm, TRAIN_SUBMIT_CONFIRM)
        summary = build_training_submit_summary(state)
        approval = record_approval(state, TRAIN_SUBMIT_ACTION, summary, state["artifact_hash"])
        save_state(state)
        return with_goal_next_action(state, {
            "run_id": run_id,
            "approval": approval,
        }, continue_action="train.submit")

    _emit(run)


@train_app.command("submit")
def train_submit(
    run_id: str = typer.Option(..., "--run-id"),
    batch_size: Optional[int] = typer.Option(None, "--batch-size"),
    monitor: bool = typer.Option(False, "--monitor", help="Create a detached monitor after successful submit"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Source agent session id for monitor delivery"),
):
    """Submit a validated training YAML."""

    def run():
        if monitor:
            _monitor_session(session_id=session_id)
        state = load_state(run_id, expected_kind="training")
        artifact = _require_artifact_hash(state, "train_yaml")
        validate_training_context(state, load_yaml(artifact))
        scn = get_scenario(state["scenario"])
        _, client, workspace_id = _config_and_client(state.get("workspace_id"))
        _ensure_training_dataset_ready(client, workspace_id, scn, state.get("selection", {}).get("dataset") or {})
        if state.get("submit_result"):
            raise AgentError("already_submitted", "该 run 已提交过训练任务", "train.status")
        require_approval(state, TRAIN_SUBMIT_ACTION, state["artifact_hash"])
        validation = state.get("validation") or {}
        bs = validation.get("batch_size")
        if batch_size is not None and batch_size != bs:
            raise AgentError(
                "submit_parameter_mismatch",
                f"submit 的 batch_size={batch_size} 与 validate 的 batch_size={bs} 不一致",
                "rerun_train_validate_with_batch_size",
            )
        batch_param = validation.get("batch_size_param")
        if not batch_param or bs is None:
            raise AgentError(
                "missing_validated_training_override",
                "缺少 validate 阶段确认过的训练参数覆盖记录",
                "rerun_train_validate",
            )
        wrapped_override_params = validation.get("override_params")
        if not wrapped_override_params:
            wrapped_override_params = [f"{batch_param}={bs}"]
        output = run_quietly(
            create_task,
            config=str(artifact),
            name=None,
            description=None,
            asset_id=None,
            model_id=None,
            model_type=None,
            train_type=None,
            model_source=None,
            model_name=None,
            dataset_id=None,
            dataset_name=None,
            dataset_version_id=None,
            eval_dataset_id=None,
            eval_dataset_name=None,
            eval_dataset_version_id=None,
            dataset_split_ratio=None,
            checkpoint_id=None,
            save_checkpoints_max=None,
            restore_training=None,
            sfs_model=None,
            sfs_dataset=None,
            sfs_preload=None,
            pool_id=None,
            pool_type=None,
            chip_type=None,
            flavor_id=None,
            nodes=None,
            flavor=None,
            t_flops=None,
            train_flavor=None,
            plog_level=None,
            is_input_finished=None,
            workspace=state.get("workspace_id"),
            wait=False,
            dry_run=False,
            override_params=wrapped_override_params,
            fmt="json",
        )
        data = extract_first_json(output)
        state["submit_result"] = data
        save_state(state)
        task_id = data.get("task_id") or data.get("id") or data.get("taskId") if isinstance(data, dict) else ""
        status_command = f"pangu-agent train status --run-id {run_id} --task-id {task_id} --json" if task_id else ""
        result = apply_submit_monitor_contract(
            with_goal_next_action(
                state,
                {
                    "run_id": run_id,
                    "task": data,
                    "task_id": task_id,
                    "status_command": status_command,
                    **monitor_submit_fields(run_id, task_id),
                },
                milestone=TRAINING_SUBMITTED,
                continue_action="train.status",
            )
        )
        return _attach_submit_monitor(
            result,
            run_id=run_id,
            monitor=monitor,
            session_id=session_id,
        )

    _emit(run)


@train_app.command("status")
def train_status(
    task_id: str = typer.Option(..., "--task-id"),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    goal: Optional[str] = typer.Option(None, "--goal", help="Workflow goal boundary for standalone status checks"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Get training task status."""

    def run():
        state = _goal_state(run_id, "training", goal, TRAINING_COMPLETED)
        _, client, workspace_id = _config_and_client(workspace or state.get("workspace_id"))
        data = client.get(TRAIN_TASK_PATH, workspace_id=workspace_id, task_id=task_id)
        status = _training_status_value(data)
        if status == "completed":
            return with_goal_next_action(
                state,
                {"run_id": run_id, "task": data, "task_id": task_id, "task_status": status},
                milestone=TRAINING_COMPLETED,
                continue_action="train.publish_if_user_wants",
            )
        next_action = "inspect_training_failure" if status in {"failed", "stopped"} else "poll_training_status"
        result = with_goal_next_action(
            state,
            {"run_id": run_id, "task": data, "task_id": task_id, "task_status": status},
            continue_action=next_action,
        )
        if status in {"failed", "stopped"}:
            result["terminal"] = True
        return apply_status_monitor_contract(
            result,
            run_id=run_id,
            target_id=task_id,
            submitted_milestone=TRAINING_SUBMITTED,
        )

    _emit(run)


@train_app.command("publish")
def train_publish(
    task_id: str = typer.Option(..., "--task-id"),
    asset_name: str = typer.Option(..., "--asset-name"),
    visibility: str = typer.Option("current", "--visibility"),
    category: str = typer.Option("pangu", "--category"),
    description: str = typer.Option("", "--description", "-d"),
    confirm: Optional[str] = typer.Option(None, "--confirm"),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    goal: Optional[str] = typer.Option(None, "--goal", help="Workflow goal boundary for standalone publish"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
):
    """Publish a completed training task output as a model asset."""

    def run():
        state = _goal_state(run_id, "training", goal, MODEL_PUBLISHED)
        workspace_arg = workspace or state.get("workspace_id")
        _, client, workspace_id = _config_and_client(workspace_arg)
        require_confirmation(confirm, PUBLISH_MODEL_CONFIRM)
        output = run_quietly(
            publish_model,
            task_id=task_id,
            asset_name=asset_name,
            visibility=visibility,
            workspace=workspace_arg,
            execution_id=None,
            model_id=None,
            category=category,
            description=description,
            fmt="json",
        )
        data = extract_first_json(output)
        published_model_id = data.get("model_id") if isinstance(data, dict) else ""
        published_asset, asset_candidates = _resolve_published_asset(
            client,
            workspace_id,
            model_id=published_model_id,
            asset_name=asset_name,
        )
        asset_id = _asset_id(published_asset)
        publish_request = {
            "task_id": task_id,
            "asset_name": asset_name,
            "visibility": visibility,
            "category": category,
            "description": description,
        }
        if run_id:
            state["publish_request"] = publish_request
            state["publish_result"] = data
            if published_asset:
                state["published_asset"] = published_asset
                state["published_assets"] = [published_asset]
            save_state(state)
        continue_action = "deploy.plan" if asset_id else "train.published-assets"
        return with_goal_next_action(
            state,
            {
                "publish_request": publish_request,
                "publish_result": data,
                "published_model_id": published_model_id,
                "published_asset": published_asset,
                "published_asset_id": asset_id,
                "asset_resolution": {
                    "resolved": bool(asset_id),
                    "lookup": "model-assets-ext",
                    "matched_by": "model_id+asset_name" if asset_id else "",
                    "candidate_count": len(asset_candidates),
                    "retry_command": f"pangu-agent train published-assets --run-id {run_id} --task-id {task_id} --json" if run_id else "",
                },
                "deploy_plan_command": _deploy_plan_command(asset_id, state.get("goal")),
            },
            milestone=MODEL_PUBLISHED,
            continue_action=continue_action,
        )

    _emit(run)


@train_app.command("published-assets")
def train_published_assets(
    task_id: str = typer.Option(..., "--task-id"),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    asset_name: Optional[str] = typer.Option(None, "--asset-name", help="Published asset name used to resolve asset_id"),
    goal: Optional[str] = typer.Option(None, "--goal", help="Workflow goal boundary for standalone asset resolution"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Resolve published model asset IDs for deployment."""

    def run():
        state = _goal_state(run_id, "training", goal, SERVICE_RUNNING)
        _, client, workspace_id = _config_and_client(workspace or state.get("workspace_id"))
        detail = client.get(TRAIN_TASK_PATH, workspace_id=workspace_id, task_id=task_id)
        execution_id = detail.get("execution_id")
        if not execution_id:
            raise AgentError("missing_execution_id", "任务详情中没有 execution_id", "inspect_task_detail")
        data = client.get(TRAIN_MODELS_PATH, workspace_id=workspace_id, params={"execution_id": execution_id})
        training_models = data.get("models", []) if isinstance(data, dict) else []
        publish_request = state.get("publish_request") or {}
        publish_result = state.get("publish_result") or {}
        resolved_asset_name = asset_name or publish_request.get("asset_name")
        target_model_ids = []
        if isinstance(publish_result, dict) and publish_result.get("model_id"):
            target_model_ids.append(str(publish_result.get("model_id")))
        for item in training_models:
            if isinstance(item, dict) and item.get("model_id"):
                mid = str(item.get("model_id"))
                if mid not in target_model_ids:
                    target_model_ids.append(mid)

        published_assets: list[dict[str, Any]] = []
        asset_candidates: list[dict[str, Any]] = []
        for model_id in target_model_ids or [""]:
            selected, candidates = _resolve_published_asset(
                client,
                workspace_id,
                model_id=model_id,
                asset_name=resolved_asset_name,
            )
            if selected:
                aid = _asset_id(selected)
                if aid and all(_asset_id(row) != aid for row in published_assets):
                    published_assets.append(selected)
            for row in candidates:
                aid = _asset_id(row)
                if aid and all(_asset_id(existing) != aid for existing in asset_candidates):
                    asset_candidates.append(row)

        published_asset = published_assets[0] if len(published_assets) == 1 else None
        asset_id = _asset_id(published_asset)
        if run_id:
            state["training_models"] = training_models
            state["published_assets"] = published_assets
            if published_asset:
                state["published_asset"] = published_asset
            save_state(state)
        continue_action = "deploy.plan" if asset_id else "wait_or_retry_train.published-assets"
        return with_goal_next_action(
            state,
            {
                "models": training_models,
                "training_models": training_models,
                "published_assets": published_assets,
                "published_asset": published_asset,
                "published_asset_id": asset_id,
                "asset_resolution": {
                    "resolved": bool(asset_id),
                    "lookup": "model-assets-ext",
                    "target_model_ids": target_model_ids,
                    "asset_name": resolved_asset_name,
                    "candidate_count": len(asset_candidates),
                },
                "deploy_plan_command": _deploy_plan_command(asset_id, state.get("goal")),
            },
            continue_action=continue_action,
        )

    _emit(run)


@deploy_app.command("plan")
def deploy_plan(
    asset_id: str = typer.Option(..., "--asset-id"),
    page_size: int = typer.Option(DEFAULT_PAGE_SIZE, "--page-size"),
    goal: Optional[str] = typer.Option(None, "--goal", help="Workflow goal boundary"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Query deploy options and matching edge pools for an asset."""

    def run():
        config, client, workspace_id = _config_and_client(workspace)
        asset = client.get(
            MODEL_DETAIL_PATH,
            workspace_id=workspace_id,
            asset_id=asset_id,
            params={"is_all_action": "true"},
        )
        _, options = _extract_resource_info(asset)
        for row in options:
            chips = " ".join(f"--chip-type {ct}" for ct in row["chip_types"])
            arch = f"--arch {row['arch']}" if row["arch"] else ""
            if row["action_type"] == "EDGE-DEPLOY":
                row["pool_cmd"] = f"pangu pool list {chips} {arch} --edge".strip()
            else:
                row["pool_cmd"] = f"pangu pool list {chips} {arch} --job-type Infer".strip()
        indexed_options = []
        all_pools = []
        for opt_index, opt in enumerate(options, start=1):
            if not isinstance(opt, dict):
                continue
            option = dict(opt)
            option["index"] = opt_index
            indexed_options.append(option)
            chip_types = option.get("chip_types") or []
            arch = option.get("arch") or "ARM"
            try:
                pools = _query_pools(
                    client,
                    workspace_id,
                    config.env_type,
                    purpose="infer",
                    chip_types=chip_types,
                    arch=arch,
                    edge=option.get("action_type") == "EDGE-DEPLOY",
                )
            except Exception:
                pools = []
            for pool in pools:
                row = dict(pool)
                row["option_index"] = opt_index
                row["index"] = len(all_pools) + 1
                all_pools.append(row)
        state = base_state("deployment", None, config.env_type, workspace_id, goal=goal)
        state["asset_id"] = asset_id
        state["deploy_options"] = indexed_options
        state["pools"] = all_pools
        save_state(state)
        option_page = candidate_page("deploy_options", indexed_options, page=1, page_size=page_size)
        pool_page = candidate_page("pools", all_pools, page=1, page_size=page_size)
        return with_goal_next_action(state, {
            "run_id": state["run_id"],
            "asset_id": asset_id,
            "deploy_options": option_page["deploy_options"],
            "pools": pool_page["pools"],
            "candidate_pages": {
                "deploy_options": page_metadata("deploy_options", indexed_options, page=1, page_size=page_size),
                "pools": page_metadata("pools", all_pools, page=1, page_size=page_size),
            },
            "page_more_command": f"pangu-agent candidates --run-id {state['run_id']} --kind <deploy_options|pools> --page <n> --page-size {page_size} --json",
        }, continue_action="choose_deploy_option_and_pool")

    _emit(run)


@deploy_app.command("scaffold")
def deploy_scaffold(
    run_id: str = typer.Option(..., "--run-id"),
    option: int = typer.Option(..., "--option"),
    pool: int = typer.Option(..., "--pool"),
    service_name: str = typer.Option(..., "--service-name"),
    access_mode: str = typer.Option("ELB", "--access-mode"),
    instances: int = typer.Option(1, "--instances"),
):
    """Generate a deployment YAML using selected plan candidates."""

    def run():
        state = load_state(run_id, expected_kind="deployment")
        option_row = select_index(state, "deploy_options", option)
        pool_row = select_index(state, "pools", pool)
        if pool_row.get("option_index") != option:
            raise AgentError(
                "pool_option_mismatch",
                f"pool index {pool} 不属于 deploy option {option}",
                "choose_pool_for_selected_option",
            )
        artifact = _deploy_artifact_path(run_id)
        infer_type = "edge" if option_row.get("action_type") == "EDGE-DEPLOY" else "online"
        output = run_quietly(
            scaffold_deploy,
            asset_id=state["asset_id"],
            infer_type=infer_type,
            pool_id=pool_row.get("pool_id"),
            instances=instances,
            service_name=service_name,
            edge_access_mode=access_mode,
            elb_id=None,
            https_secrets=None,
            infer_version=None,
            workspace=state.get("workspace_id"),
            output=str(artifact),
        )
        state["selection"] = {
            "deploy_option": option_row,
            "pool": pool_row,
            "service_name": service_name,
            "access_mode": access_mode,
            "instances": instances,
        }
        state["artifacts"]["deploy_yaml"] = str(artifact)
        state["validate_success"] = False
        state["artifact_hash"] = ""
        state.pop("approval", None)
        save_state(state)
        return with_goal_next_action(state, {
            "run_id": run_id,
            "deploy_yaml": str(artifact),
            "wrapped_output": output.strip(),
        }, continue_action="deploy.validate")

    _emit(run)


@deploy_app.command("validate")
def deploy_validate(run_id: str = typer.Option(..., "--run-id")):
    """Static-validate a generated deployment YAML."""

    def run():
        state = load_state(run_id, expected_kind="deployment")
        artifact = Path(state.get("artifacts", {}).get("deploy_yaml") or "")
        if not artifact.exists():
            raise AgentError("artifact_missing", "部署 YAML 不存在", "run_deploy_scaffold")
        if yaml_has_todo(artifact):
            raise AgentError("deploy_yaml_has_todo", "部署 YAML 中仍有 TODO 占位", "edit_or_regenerate_deploy_yaml")
        body = load_yaml(artifact)
        missing = []
        for key in ("service_name", "asset_id", "arch", "infer_type"):
            if not body.get(key):
                missing.append(key)
        svc = body.get("service_config") or {}
        if not svc.get("cluster_id"):
            missing.append("service_config.cluster_id")
        if not svc.get("instance_count"):
            missing.append("service_config.instance_count")
        if missing:
            raise AgentError(
                "deploy_required_field_missing",
                f"部署 YAML 缺少字段: {', '.join(missing)}",
                "regenerate_or_fix_deploy_yaml",
            )
        state["validate_success"] = True
        state["artifact_hash"] = sha256_file(artifact)
        state.pop("approval", None)
        approval_summary = build_deploy_submit_summary(state)
        save_state(state)
        return with_goal_next_action(state, {
            "run_id": run_id,
            "deploy_yaml": str(artifact),
            "artifact_hash": state["artifact_hash"],
            "approval_required": True,
            "approval_summary": approval_summary,
            "approval_confirm": DEPLOY_SUBMIT_CONFIRM,
        }, continue_action="ask_user_deploy_approval")

    _emit(run)


@deploy_app.command("approve")
def deploy_approve(
    run_id: str = typer.Option(..., "--run-id"),
    confirm: Optional[str] = typer.Option(None, "--confirm"),
):
    """Record explicit user approval for a validated deployment submission."""

    def run():
        state = load_state(run_id, expected_kind="deployment")
        _require_artifact_hash(state, "deploy_yaml")
        require_confirmation(confirm, DEPLOY_SUBMIT_CONFIRM)
        summary = build_deploy_submit_summary(state)
        approval = record_approval(state, DEPLOY_SUBMIT_ACTION, summary, state["artifact_hash"])
        save_state(state)
        return with_goal_next_action(state, {
            "run_id": run_id,
            "approval": approval,
        }, continue_action="deploy.submit")

    _emit(run)


@deploy_app.command("submit")
def deploy_submit(
    run_id: str = typer.Option(..., "--run-id"),
    monitor: bool = typer.Option(False, "--monitor", help="Create a detached monitor after successful submit"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Source agent session id for monitor delivery"),
):
    """Submit a validated deployment YAML."""

    def run():
        if monitor:
            _monitor_session(session_id=session_id)
        state = load_state(run_id, expected_kind="deployment")
        artifact = _require_artifact_hash(state, "deploy_yaml")
        if state.get("submit_result"):
            raise AgentError("already_submitted", "该 run 已提交过部署任务", "deploy.status")
        require_approval(state, DEPLOY_SUBMIT_ACTION, state["artifact_hash"])
        output = run_quietly(
            deploy_service,
            config=str(artifact),
            name=None,
            desc=None,
            asset_id=None,
            asset_ids=None,
            asset_tag=None,
            asset_type=None,
            arch=None,
            infer_type=None,
            device_type=None,
            chip_type=None,
            request_mode=None,
            category=None,
            pool_id=None,
            instances=None,
            elb_id=None,
            scene=None,
            security_bar_type=None,
            security_bar_edition=None,
            deployed_model=None,
            task_config=None,
            input_types=None,
            output_types=None,
            infer_version=None,
            https_secrets=None,
            edge_node_port=None,
            workspace=state.get("workspace_id"),
            wait=False,
            fmt="json",
        )
        data = extract_first_json(output)
        state["submit_result"] = data
        save_state(state)
        service_id = data.get("service_id") or data.get("id") if isinstance(data, dict) else ""
        status_command = (
            f"pangu-agent deploy status --run-id {run_id} --service-id {service_id} --json" if service_id else ""
        )
        result = apply_submit_monitor_contract(
            with_goal_next_action(
                state,
                {
                    "run_id": run_id,
                    "service": data,
                    "service_id": service_id,
                    "status_command": status_command,
                    **monitor_submit_fields(run_id, service_id),
                },
                milestone=DEPLOYMENT_SUBMITTED,
                continue_action="deploy.status",
            )
        )
        return _attach_submit_monitor(
            result,
            run_id=run_id,
            monitor=monitor,
            session_id=session_id,
        )

    _emit(run)


@deploy_app.command("status")
def deploy_status(
    service_id: str = typer.Option(..., "--service-id"),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    goal: Optional[str] = typer.Option(None, "--goal", help="Workflow goal boundary for standalone status checks"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Get deployment service status."""

    def run():
        state = _goal_state(run_id, "deployment", goal, SERVICE_RUNNING)
        _, client, workspace_id = _config_and_client(workspace or state.get("workspace_id"))
        data = client.get(SERVICE_DETAIL_PATH, workspace_id=workspace_id, service_id=service_id)
        assets = data.get("assets", [])
        if assets and isinstance(assets[0], dict) and "asset_type" not in data:
            data["asset_type"] = assets[0].get("asset_type", "")
        status = _service_status_value(data)
        if status == "running":
            return with_goal_next_action(
                state,
                {"run_id": run_id, "service": data, "service_id": service_id, "service_status": status},
                milestone=SERVICE_RUNNING,
                continue_action="stop",
            )
        next_action = "inspect_deployment_failure" if status in {"failed", "stopped"} else "poll_deploy_status"
        result = with_goal_next_action(
            state,
            {"run_id": run_id, "service": data, "service_id": service_id, "service_status": status},
            continue_action=next_action,
        )
        if status in {"failed", "stopped"}:
            result["terminal"] = True
        return apply_status_monitor_contract(
            result,
            run_id=run_id,
            target_id=service_id,
            submitted_milestone=DEPLOYMENT_SUBMITTED,
        )

    _emit(run)


@monitor_app.command("add")
def monitor_add(
    run_id: str = typer.Option(..., "--run-id"),
    adapter: Optional[str] = typer.Option(None, "--adapter", help="Agent adapter name; overrides configured default"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Source agent session id"),
    session_json: Optional[str] = typer.Option(None, "--session-json", help="Opaque adapter session JSON object"),
    session_file: Optional[Path] = typer.Option(None, "--session-file", help="File containing adapter session JSON object"),
    detach: bool = typer.Option(False, "--detach", help="Start a detached monitor runner"),
    interval: int = typer.Option(60, "--interval", help="Polling interval in seconds"),
    timeout: int = typer.Option(86400, "--timeout", help="Monitor timeout in seconds"),
    max_delivery_attempts: int = typer.Option(8, "--max-delivery-attempts"),
    success_message: Optional[str] = typer.Option(None, "--success-message"),
    failure_message: Optional[str] = typer.Option(None, "--failure-message"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Create an async monitor from a submitted training/deployment run."""

    def run():
        adapter_name = _monitor_adapter(adapter)
        session = _monitor_session(
            session_id=session_id,
            session_json=session_json,
            session_file=session_file,
        )
        task = monitor_task_from_run(
            run_id=run_id,
            adapter=adapter_name,
            session=session,
            interval_seconds=interval,
            timeout_seconds=timeout,
            max_delivery_attempts=max_delivery_attempts,
            success_message=success_message,
            failure_message=failure_message,
        )
        save_monitor(task)
        detach_info = start_detached_monitor(task.monitor_id) if detach else {}
        return {
            "monitor_id": task.monitor_id,
            "monitor": task.to_dict(),
            "detached": bool(detach_info),
            "detach": detach_info,
            "next_action": "stop_waiting_in_main_session" if detach else "monitor.run",
        }

    _emit(run)


@monitor_app.command("run")
def monitor_run(
    monitor_id: str = typer.Option(..., "--monitor-id"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Run a monitor loop until terminal state, timeout, or cancel."""

    def run():
        task = run_monitor(monitor_id)
        return {"monitor_id": task.monitor_id, "monitor": task.to_dict(), "next_action": "stop"}

    _emit(run)


@monitor_app.command("list")
def monitor_list(
    delivery_status: Optional[str] = typer.Option(None, "--delivery-status"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """List local monitor tasks."""

    _emit(lambda: {"monitors": list_monitors(delivery_status=delivery_status), "next_action": "continue"})


@monitor_app.command("status")
def monitor_status(
    monitor_id: str = typer.Option(..., "--monitor-id"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Show a local monitor task."""

    def run():
        task = load_monitor(monitor_id)
        return {"monitor_id": task.monitor_id, "monitor": task.to_dict(), "next_action": "continue"}

    _emit(run)


@monitor_app.command("cancel")
def monitor_cancel(
    monitor_id: str = typer.Option(..., "--monitor-id"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Mark a local monitor task as cancelled."""

    def run():
        task = load_monitor(monitor_id)
        task.monitor_status = MONITOR_CANCELLED
        save_monitor(task)
        return {"monitor_id": task.monitor_id, "monitor": task.to_dict(), "next_action": "stop"}

    _emit(run)


@monitor_app.command("retry-delivery")
def monitor_retry_delivery(
    monitor_id: str = typer.Option(..., "--monitor-id"),
    adapter: Optional[str] = typer.Option(None, "--adapter"),
    session_id: Optional[str] = typer.Option(None, "--session-id"),
    session_json: Optional[str] = typer.Option(None, "--session-json"),
    session_file: Optional[Path] = typer.Option(None, "--session-file"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Retry delivery for a terminal monitor, optionally to a new session."""

    def run():
        session = None
        if session_id or session_json or session_file:
            session = _monitor_session(
                session_id=session_id,
                session_json=session_json,
                session_file=session_file,
            )
        task = retry_delivery(
            monitor_id,
            adapter=adapter or os.environ.get("PANGU_MONITOR_ADAPTER") or None,
            session=session,
        )
        return {"monitor_id": task.monitor_id, "monitor": task.to_dict(), "next_action": "continue"}

    _emit(run)


@monitor_app.command("message")
def monitor_message_cmd(
    monitor_id: str = typer.Option(..., "--monitor-id"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Export the message that would be delivered for a terminal monitor."""

    _emit(lambda: {"monitor_id": monitor_id, "message": monitor_message(monitor_id), "next_action": "manual_send"})


def _skill_source_path() -> Path:
    """Locate the bundled skill file inside the repo/package."""
    # Editable install: agent_main.py is at src/pangu/agent_main.py
    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / ".claude" / "skills" / "pangu-agent" / "SKILL.md"
    if candidate.exists():
        return candidate
    # Fallback: inside the installed package
    pkg_root = Path(__file__).resolve().parent
    candidate = pkg_root / "data" / "skills" / "pangu-agent" / "SKILL.md"
    if candidate.exists():
        return candidate
    raise AgentError("skill_source_missing", "找不到内置的 SKILL.md 源文件", "check_installation")


def _skill_dest_path() -> Path:
    return Path.home() / ".claude" / "skills" / "pangu-agent" / "SKILL.md"


@skill_app.command("install")
def skill_install(force: bool = typer.Option(False, "--force")):
    """Install the pangu-agent skill to ~/.claude/skills/."""

    def run():
        src = _skill_source_path()
        dest = _skill_dest_path()
        exists_before = dest.exists()
        if exists_before and not force:
            raise AgentError(
                "skill_already_installed",
                f"skill 已安装到 {dest}，使用 --force 覆盖",
                "pass_force_or_skip",
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return {
            "installed_to": str(dest),
            "exists_before": exists_before,
            "force": force,
            "next_action": "use_pangu_agent_skill",
        }

    _emit(run)


@skill_app.command("uninstall")
def skill_uninstall(yes: bool = typer.Option(False, "-y", "--yes")):
    """Remove the pangu-agent skill from ~/.claude/skills/."""

    def run():
        dest = _skill_dest_path()
        if not dest.exists():
            raise AgentError("skill_not_installed", f"skill 未安装: {dest}", "skip_or_install")
        if not yes and not typer.confirm(f"确认删除 {dest}?"):
            raise typer.Abort()
        dest.unlink()
        return {"uninstalled_from": str(dest), "next_action": "continue"}

    _emit(run)


@skill_app.command("path")
def skill_path():
    """Show skill source and destination paths."""

    def run():
        src = _skill_source_path()
        dest = _skill_dest_path()
        return {
            "source": str(src),
            "destination": str(dest),
            "installed": dest.exists(),
            "next_action": "install_if_needed",
        }

    _emit(run)


@skill_app.command("status")
def skill_status():
    """Check whether the pangu-agent skill is installed."""

    def run():
        dest = _skill_dest_path()
        src = _skill_source_path()
        installed = dest.exists()
        up_to_date = False
        if installed:
            up_to_date = dest.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")
        return {
            "installed": installed,
            "up_to_date": up_to_date,
            "destination": str(dest),
            "next_action": "install" if not installed else ("up_to_date" if up_to_date else "reinstall_with_force"),
        }

    _emit(run)


if __name__ == "__main__":
    app()
