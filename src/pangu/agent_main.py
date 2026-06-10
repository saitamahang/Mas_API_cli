"""Agent-safe CLI entrypoint for Pangu workflows."""

from __future__ import annotations

from importlib.metadata import version as get_version
from pathlib import Path
from typing import Any, List, Optional

import typer

from pangu.adapters import get_pool_adapter
from pangu.adapters.base import PoolRequest
from pangu.agent.errors import AgentError
from pangu.agent.scenarios import get_scenario, list_scenarios
from pangu.agent.state import (
    RUNS_DIR,
    base_state,
    load_state,
    load_yaml,
    save_state,
    select_index,
    sha256_file,
    yaml_has_todo,
)
from pangu.agent.utils import extract_first_json, failure, print_json, run_quietly, success
from pangu.auth import AuthManager
from pangu.client import APIError, PanguClient
from pangu.commands.service import deploy_service, get_service, scaffold_deploy
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
app.add_typer(dataset_app, name="dataset")
app.add_typer(train_app, name="train")
app.add_typer(deploy_app, name="deploy")


MODEL_EXT_PATH = "/v1/{project_id}/workspaces/{workspace_id}/asset-manager/model-assets-ext"
DATASET_LIST_PATH = "/v2/{project_id}/workspaces/{workspace_id}/data-management/datasets"
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
        print_json(failure(err))
        raise typer.Exit(1)


def _config_and_client(workspace: Optional[str] = None) -> tuple[PanguConfig, PanguClient, str]:
    config = PanguConfig.load()
    try:
        workspace_id = config.get_workspace_id(workspace)
    except Exception as e:
        raise AgentError("missing_workspace", str(e), "set_default_workspace_or_pass_workspace") from e
    return config, PanguClient(config), workspace_id


def _flatten_asset_ext(item: dict[str, Any]) -> dict[str, Any]:
    ma = item.get("modelAsset") or {}
    merged = dict(ma) if isinstance(ma, dict) else {}
    for key in (
        "can_deploy",
        "can_train",
        "can_delete",
        "can_eval",
        "can_quantize",
        "can_export",
        "model_id",
        "is_used",
        "publish_info",
        "subscribe_info",
    ):
        if key in item:
            merged[key] = item[key]
    return merged


def _query_models(client: PanguClient, workspace_id: str, scenario: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    mq = scenario["model_query"]
    params = {
        "limit": limit,
        "offset": 0,
        "asset_source": mq["source"],
        "asset_type": mq["type"],
        "sub_asset_type": mq["sub_type"],
        "asset_action": mq["asset_action"],
    }
    data = client.get(MODEL_EXT_PATH, workspace_id=workspace_id, params=params)
    assets = (data.get("assets") if isinstance(data, dict) else None) or []
    rows = []
    for idx, item in enumerate(assets, start=1):
        if not isinstance(item, dict):
            continue
        row = _flatten_asset_ext(item)
        row["index"] = idx
        rows.append(row)
    return rows


def _query_datasets(
    client: PanguClient,
    workspace_id: str,
    scenario: dict[str, Any],
    catalog: str,
    limit: int = 100,
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
    data = client.get(DATASET_LIST_PATH, workspace_id=workspace_id, params=params)
    datasets = (data.get("datasets") if isinstance(data, dict) else None) or []
    rows = []
    for idx, item in enumerate(datasets, start=1):
        if isinstance(item, dict):
            row = dict(item)
            row["index"] = idx
            rows.append(row)
    return rows


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


def _normalize_obs_path(obs_path: str) -> str:
    if obs_path.startswith("obs://"):
        return obs_path[len("obs://"):]
    return obs_path


def _training_artifact_path(run_id: str) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return RUNS_DIR / f"{run_id}.train.yaml"


def _deploy_artifact_path(run_id: str) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
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


@dataset_app.command("list")
def dataset_list(
    scenario: str = typer.Option(..., "--scenario"),
    catalog: str = typer.Option("PUBLISH", "--catalog"),
    limit: int = typer.Option(100, "--limit"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """List datasets using scenario-defined filters."""

    def run():
        scn = get_scenario(scenario)
        _, client, workspace_id = _config_and_client(workspace)
        rows = _query_datasets(client, workspace_id, scn, catalog=catalog, limit=limit)
        return {
            "scenario": scenario,
            "catalog": catalog,
            "datasets": rows,
            "next_action": "choose_dataset" if rows else "dataset_import_or_publish_required",
        }

    _emit(run)


@dataset_app.command("import-validate")
def dataset_import_validate(
    scenario: str = typer.Option(..., "--scenario"),
    name: str = typer.Option(..., "--name"),
    obs_path: str = typer.Option(..., "--obs-path"),
    desc: Optional[str] = typer.Option(None, "--desc"),
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
        state = base_state("dataset_import", scenario, config.env_type, workspace_id)
        state["request_body"] = body
        save_state(state)
        return {
            "run_id": state["run_id"],
            "request_body": body,
            "next_action": "dataset.import-submit",
        }

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
        return {"job": data, "final": final, "next_action": "dataset.publish-prepare"}

    _emit(run)


@dataset_app.command("publish-prepare")
def dataset_publish_prepare(
    scenario: str = typer.Option(..., "--scenario"),
    source_catalog: str = typer.Option("ORIGINAL", "--source-catalog"),
    limit: int = typer.Option(100, "--limit"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Query source datasets and cache indexed candidates for publishing."""

    def run():
        scn = get_scenario(scenario)
        config, client, workspace_id = _config_and_client(workspace)
        sources = _query_datasets(client, workspace_id, scn, catalog=source_catalog, limit=limit)
        state = base_state("dataset_publish", scenario, config.env_type, workspace_id)
        state["source_catalog"] = source_catalog
        state["sources"] = sources
        save_state(state)
        return {
            "run_id": state["run_id"],
            "scenario": scenario,
            "source_catalog": source_catalog,
            "sources": sources,
            "next_action": "choose_sources" if sources else "dataset.import-validate",
        }

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
        return {
            "run_id": run_id,
            "request_body": body,
            "next_action": "dataset.publish-submit",
        }

    _emit(run)


@dataset_app.command("publish-submit")
def dataset_publish_submit(run_id: str = typer.Option(..., "--run-id")):
    """Submit a previously validated dataset publish request."""

    def run():
        state = load_state(run_id, expected_kind="dataset_publish")
        if not state.get("validate_success"):
            raise AgentError("submit_without_validate", "publish-submit 前必须先 publish-validate", "run_publish_validate")
        _, client, workspace_id = _config_and_client(state.get("workspace_id"))
        data = client.post(PUBLISH_JOBS_PATH, workspace_id=workspace_id, json=state["request_body"])
        state["submit_result"] = data
        save_state(state)
        return {"job": data, "next_action": "train.plan"}

    _emit(run)


@train_app.command("plan")
def train_plan(
    scenario: str = typer.Option(..., "--scenario"),
    limit: int = typer.Option(100, "--limit"),
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
        )
        pools = _query_pools(client, workspace_id, config.env_type, purpose="train")
        state = base_state("training", scenario, config.env_type, workspace_id)
        state["models"] = models
        state["datasets"] = datasets
        state["pools"] = pools
        save_state(state)
        next_action = "choose_model_dataset_pool"
        if not models:
            next_action = "add_or_adjust_model_scenario_profile"
        elif not datasets:
            next_action = "dataset_import_or_publish_required"
        elif not pools:
            next_action = "check_resource_pools"
        return {
            "run_id": state["run_id"],
            "scenario": scenario,
            "env_type": config.env_type,
            "workspace_id": workspace_id,
            "models": models,
            "datasets": datasets,
            "pools": pools,
            "next_action": next_action,
        }

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
        state["artifacts"]["train_yaml"] = str(artifact)
        state["validate_success"] = False
        state["artifact_hash"] = ""
        save_state(state)
        return {
            "run_id": run_id,
            "train_yaml": str(artifact),
            "wrapped_output": output.strip(),
            "next_action": "train.validate",
        }

    _emit(run)


@train_app.command("validate")
def train_validate(
    run_id: str = typer.Option(..., "--run-id"),
    batch_size: Optional[int] = typer.Option(None, "--batch-size"),
):
    """Dry-run a generated training YAML and record its artifact hash."""

    def run():
        state = load_state(run_id, expected_kind="training")
        artifact = Path(state.get("artifacts", {}).get("train_yaml") or "")
        if not artifact.exists():
            raise AgentError("artifact_missing", "训练 YAML 不存在", "run_train_scaffold")
        scn = get_scenario(state["scenario"])
        bs = batch_size or scn["training"].get("default_batch_size", 1)
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
            override_params=[f"batch_size={bs}"],
            fmt="yaml",
        )
        state["validate_success"] = True
        state["artifact_hash"] = sha256_file(artifact)
        state["validation"] = {"batch_size": bs}
        save_state(state)
        return {
            "run_id": run_id,
            "train_yaml": str(artifact),
            "artifact_hash": state["artifact_hash"],
            "dry_run_output": output.strip(),
            "next_action": "train.submit",
        }

    _emit(run)


@train_app.command("submit")
def train_submit(
    run_id: str = typer.Option(..., "--run-id"),
    batch_size: Optional[int] = typer.Option(None, "--batch-size"),
):
    """Submit a validated training YAML."""

    def run():
        state = load_state(run_id, expected_kind="training")
        artifact = _require_artifact_hash(state, "train_yaml")
        bs = batch_size or state.get("validation", {}).get("batch_size") or 1
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
            override_params=[f"batch_size={bs}"],
            fmt="json",
        )
        data = extract_first_json(output)
        state["submit_result"] = data
        save_state(state)
        return {"task": data, "next_action": "train.status"}

    _emit(run)


@train_app.command("status")
def train_status(
    task_id: str = typer.Option(..., "--task-id"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Get training task status."""

    def run():
        _, client, workspace_id = _config_and_client(workspace)
        data = client.get(TRAIN_TASK_PATH, workspace_id=workspace_id, task_id=task_id)
        return {"task": data, "next_action": "train.publish_if_completed"}

    _emit(run)


@train_app.command("publish")
def train_publish(
    task_id: str = typer.Option(..., "--task-id"),
    asset_name: str = typer.Option(..., "--asset-name"),
    visibility: str = typer.Option("current", "--visibility"),
    category: str = typer.Option("pangu", "--category"),
    description: str = typer.Option("", "--description", "-d"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
):
    """Publish a completed training task output as a model asset."""

    def run():
        output = run_quietly(
            publish_model,
            task_id=task_id,
            asset_name=asset_name,
            visibility=visibility,
            workspace=workspace,
            execution_id=None,
            model_id=None,
            category=category,
            description=description,
            fmt="json",
        )
        data = extract_first_json(output)
        return {"publish_result": data, "next_action": "train.published-assets_or_deploy.plan"}

    _emit(run)


@train_app.command("published-assets")
def train_published_assets(
    task_id: str = typer.Option(..., "--task-id"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Resolve model outputs for a training task."""

    def run():
        _, client, workspace_id = _config_and_client(workspace)
        detail = client.get(TRAIN_TASK_PATH, workspace_id=workspace_id, task_id=task_id)
        execution_id = detail.get("execution_id")
        if not execution_id:
            raise AgentError("missing_execution_id", "任务详情中没有 execution_id", "inspect_task_detail")
        data = client.get(TRAIN_MODELS_PATH, workspace_id=workspace_id, params={"execution_id": execution_id})
        return {"models": data.get("models", []) if isinstance(data, dict) else [], "next_action": "deploy.plan"}

    _emit(run)


@deploy_app.command("plan")
def deploy_plan(
    asset_id: str = typer.Option(..., "--asset-id"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Query deploy options and matching edge pools for an asset."""

    def run():
        config, _, workspace_id = _config_and_client(workspace)
        from pangu.commands.model import get_model

        output = run_quietly(
            get_model,
            asset_id=asset_id,
            workspace=workspace_id,
            action_asset_tag=None,
            all_actions=True,
            show_resources=True,
            fmt="json",
        )
        data = extract_first_json(output)
        options = data.get("deploy_options") or []
        indexed_options = []
        all_pools = []
        _, client, _ = _config_and_client(workspace_id)
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
        state = base_state("deployment", None, config.env_type, workspace_id)
        state["asset_id"] = asset_id
        state["deploy_options"] = indexed_options
        state["pools"] = all_pools
        save_state(state)
        return {
            "run_id": state["run_id"],
            "asset_id": asset_id,
            "deploy_options": indexed_options,
            "pools": all_pools,
            "next_action": "choose_deploy_option_and_pool",
        }

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
        save_state(state)
        return {
            "run_id": run_id,
            "deploy_yaml": str(artifact),
            "wrapped_output": output.strip(),
            "next_action": "deploy.validate",
        }

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
        save_state(state)
        return {
            "run_id": run_id,
            "deploy_yaml": str(artifact),
            "artifact_hash": state["artifact_hash"],
            "next_action": "deploy.submit",
        }

    _emit(run)


@deploy_app.command("submit")
def deploy_submit(run_id: str = typer.Option(..., "--run-id")):
    """Submit a validated deployment YAML."""

    def run():
        state = load_state(run_id, expected_kind="deployment")
        artifact = _require_artifact_hash(state, "deploy_yaml")
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
        return {"service": data, "next_action": "deploy.status"}

    _emit(run)


@deploy_app.command("status")
def deploy_status(
    service_id: str = typer.Option(..., "--service-id"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json", help="Accepted for agent compatibility"),
):
    """Get deployment service status."""

    def run():
        output = run_quietly(
            get_service,
            service_id=service_id,
            workspace=workspace,
            fmt="json",
        )
        data = extract_first_json(output)
        return {"service": data, "next_action": "poll_until_running_or_failed"}

    _emit(run)


if __name__ == "__main__":
    app()
