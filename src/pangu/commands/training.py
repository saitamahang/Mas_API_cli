"""训练任务管理命令 - pangu training create/get/list/stop/retry/delete/logs/..."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console

from pangu.client import PanguClient
from pangu.output import output

app = typer.Typer(help="训练任务管理")
console = Console()

BASE_PATH = "/v1/{project_id}/workspaces/{workspace_id}/training-jobs"
DETAIL_PATH = BASE_PATH + "/{job_id}"
VERSIONS_PATH = DETAIL_PATH + "/versions"
VERSION_PATH = DETAIL_PATH + "/versions/{version_id}"

LIST_COLUMNS = [
    ("job_id", "任务 ID"),
    ("job_name", "名称"),
    ("status", "状态"),
    ("duration", "耗时(s)"),
    ("create_time", "创建时间"),
]

DETAIL_FIELDS = [
    ("job_id", "任务 ID"),
    ("job_name", "名称"),
    ("status", "状态"),
    ("duration", "耗时(s)"),
    ("pre_version_id", "上一版本"),
    ("description", "描述"),
    ("create_time", "创建时间"),
    ("update_time", "更新时间"),
]

VERSION_COLUMNS = [
    ("version_id", "版本 ID"),
    ("version_name", "版本名"),
    ("status", "状态"),
    ("duration", "耗时(s)"),
    ("create_time", "创建时间"),
]


def _build_job_body(params: dict, config_file: Optional[str]) -> dict:
    """合并 YAML 配置与命令行参数构建请求体，命令行参数优先。"""
    body: dict = {}

    # 先加载 YAML 配置
    if config_file:
        p = Path(config_file)
        if not p.exists():
            console.print(f"[red]配置文件不存在: {config_file}[/red]")
            raise typer.Exit(1)
        with p.open() as f:
            body = yaml.safe_load(f) or {}

    # 命令行参数覆盖
    for k, v in params.items():
        if v is not None:
            body[k] = v

    return body


@app.command("list")
def list_jobs(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    status: Optional[str] = typer.Option(None, "--status", help="状态过滤: running/succeeded/failed/stopped"),
    name: Optional[str] = typer.Option(None, "--name", help="按名称搜索"),
    limit: int = typer.Option(20, "--limit", help="每页数量"),
    offset: int = typer.Option(0, "--offset", help="起始偏移"),
    sort_by: str = typer.Option("create_time", "--sort-by", help="排序字段"),
    order: str = typer.Option("desc", "--order", help="排序方向: asc/desc"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式: table/json/yaml/id"),
):
    """查询训练任务列表"""
    client = PanguClient()
    params: dict = {"limit": limit, "offset": offset, "sort_by": sort_by, "order": order}
    if status:
        params["status"] = status
    if name:
        params["job_name"] = name

    data = client.get(BASE_PATH, workspace_id=workspace, params=params)
    output(
        data,
        fmt=fmt,
        columns=LIST_COLUMNS,
        list_key="jobs",
        title="训练任务",
        status_key="status",
        id_key="job_id",
    )


@app.command("get")
def get_job(
    job_id: str = typer.Argument(help="任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询训练任务详情"""
    client = PanguClient()
    data = client.get(DETAIL_PATH, workspace_id=workspace, job_id=job_id)
    output(
        data,
        fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title=f"训练任务: {data.get('job_name', '')}",
        status_key="status",
    )


@app.command("create")
def create_job(
    config: Optional[str] = typer.Option(None, "--config", "-f", help="YAML 配置文件路径"),
    name: Optional[str] = typer.Option(None, "--name", help="任务名称"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="任务描述"),
    asset_id: Optional[str] = typer.Option(None, "--asset-id", help="模型资产 ID"),
    asset_type: Optional[str] = typer.Option(None, "--asset-type", help="模型类型: NLP/CV"),
    task_type: Optional[str] = typer.Option(None, "--task-type", help="任务类型: finetune/pretrain/rlhf"),
    pool_id: Optional[str] = typer.Option(None, "--pool-id", help="资源池 ID"),
    instances: Optional[int] = typer.Option(None, "--instances", help="训练节点数"),
    device_type: Optional[str] = typer.Option(None, "--device-type", help="设备类型: NPU/GPU"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    wait: bool = typer.Option(False, "--wait", help="等待任务完成"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """创建训练任务 (可通过 --config 传入 YAML 配置)"""
    client = PanguClient()

    cli_params = {}
    if name:
        cli_params["job_name"] = name
    if description:
        cli_params["description"] = description
    if asset_id or asset_type:
        asset = {}
        if asset_id:
            asset["asset_id"] = asset_id
        if asset_type:
            asset["asset_type"] = asset_type
        cli_params["asset"] = asset
    if task_type:
        cli_params["task_type"] = task_type

    # resource_config 组装
    resource = {}
    if pool_id:
        resource["pool_id"] = pool_id
    if instances is not None:
        resource["node_num"] = instances
    if device_type:
        resource["device_type"] = device_type
    if resource:
        cli_params["resource_config"] = resource

    body = _build_job_body(cli_params, config)

    if not body.get("job_name"):
        console.print("[red]必须提供任务名称 (--name 或配置文件中 job_name 字段)[/red]")
        raise typer.Exit(1)

    data = client.post(BASE_PATH, workspace_id=workspace, json=body)
    job_id = data.get("job_id", "")

    output(
        data,
        fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title="训练任务已创建",
        status_key="status",
    )

    if wait and job_id:
        console.print(f"[cyan]等待任务 {job_id} 完成...[/cyan]")
        final = client.wait_for_status(
            DETAIL_PATH,
            target_statuses=["succeeded", "failed", "stopped"],
            failure_statuses=["failed", "stopped"],
            status_key="status",
            workspace_id=workspace,
            job_id=job_id,
        )
        console.print(f"[green]任务完成，最终状态: {final.get('status')}[/green]")


@app.command("stop")
def stop_job(
    job_id: str = typer.Argument(help="任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
):
    """停止训练任务"""
    if not yes:
        if not typer.confirm(f"确认停止任务 {job_id}?"):
            raise typer.Abort()

    client = PanguClient()
    path = DETAIL_PATH + "/stop"
    client.post(path, workspace_id=workspace, json={}, job_id=job_id)
    console.print(f"[green]任务 {job_id} 已停止[/green]")


@app.command("retry")
def retry_job(
    job_id: str = typer.Argument(help="任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    wait: bool = typer.Option(False, "--wait", help="等待任务完成"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """重试失败的训练任务"""
    client = PanguClient()
    path = DETAIL_PATH + "/retry"
    data = client.post(path, workspace_id=workspace, json={}, job_id=job_id)

    new_job_id = data.get("job_id", job_id)
    console.print(f"[green]任务 {job_id} 已重试，新任务 ID: {new_job_id}[/green]")

    if wait and new_job_id:
        console.print(f"[cyan]等待任务 {new_job_id} 完成...[/cyan]")
        final = client.wait_for_status(
            DETAIL_PATH,
            target_statuses=["succeeded", "failed", "stopped"],
            failure_statuses=["failed", "stopped"],
            status_key="status",
            workspace_id=workspace,
            job_id=new_job_id,
        )
        console.print(f"[green]任务完成，最终状态: {final.get('status')}[/green]")


@app.command("delete")
def delete_job(
    job_id: str = typer.Argument(help="任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
):
    """删除训练任务"""
    if not yes:
        if not typer.confirm(f"确认删除任务 {job_id}?"):
            raise typer.Abort()

    client = PanguClient()
    client.delete(DETAIL_PATH, workspace_id=workspace, job_id=job_id)
    console.print(f"[green]任务 {job_id} 已删除[/green]")


@app.command("logs")
def job_logs(
    job_id: str = typer.Argument(help="任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    step: Optional[str] = typer.Option(None, "--step", help="训练步骤 (e.g. train/eval)"),
    node_id: Optional[str] = typer.Option(None, "--node-id", help="节点 ID"),
    lines: int = typer.Option(100, "--lines", "-n", help="返回行数"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查询训练任务日志"""
    client = PanguClient()
    path = DETAIL_PATH + "/logs"
    params: dict = {"lines": lines}
    if step:
        params["step"] = step
    if node_id:
        params["node_id"] = node_id

    data = client.get(path, workspace_id=workspace, params=params, job_id=job_id)
    output(data, fmt=fmt)


@app.command("nodes")
def job_nodes(
    job_id: str = typer.Argument(help="任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询训练任务节点列表"""
    client = PanguClient()
    path = DETAIL_PATH + "/nodes"
    data = client.get(path, workspace_id=workspace, job_id=job_id)

    columns = [
        ("node_id", "节点 ID"),
        ("node_name", "节点名"),
        ("status", "状态"),
        ("ip", "IP"),
        ("device_type", "设备类型"),
    ]
    output(data, fmt=fmt, columns=columns, list_key="nodes", title="训练节点", status_key="status")


@app.command("node-logs")
def node_logs(
    job_id: str = typer.Argument(help="任务 ID"),
    node_id: str = typer.Argument(help="节点 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    lines: int = typer.Option(100, "--lines", "-n", help="返回行数"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查询指定节点日志"""
    client = PanguClient()
    path = DETAIL_PATH + "/nodes/{node_id}/logs"
    data = client.get(path, workspace_id=workspace, params={"lines": lines}, job_id=job_id, node_id=node_id)
    output(data, fmt=fmt)


@app.command("metrics")
def job_metrics(
    job_id: str = typer.Argument(help="任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    metric_name: Optional[str] = typer.Option(None, "--metric", "-m", help="指标名称"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查询训练指标 (loss/accuracy 等)"""
    client = PanguClient()
    path = DETAIL_PATH + "/metrics"
    params = {}
    if metric_name:
        params["metric_name"] = metric_name

    data = client.get(path, workspace_id=workspace, params=params or None, job_id=job_id)
    output(data, fmt=fmt)


@app.command("checkpoints")
def job_checkpoints(
    job_id: str = typer.Argument(help="任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询训练 Checkpoint 列表"""
    client = PanguClient()
    path = DETAIL_PATH + "/checkpoints"
    data = client.get(path, workspace_id=workspace, job_id=job_id)

    columns = [
        ("checkpoint_id", "Checkpoint ID"),
        ("step", "训练步数"),
        ("obs_path", "OBS 路径"),
        ("create_time", "创建时间"),
    ]
    output(data, fmt=fmt, columns=columns, list_key="checkpoints", title="Checkpoint 列表")


@app.command("publish")
def publish_model(
    job_id: str = typer.Argument(help="任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    checkpoint_id: Optional[str] = typer.Option(None, "--checkpoint-id", help="Checkpoint ID (不传则用最新)"),
    asset_name: Optional[str] = typer.Option(None, "--asset-name", help="发布后的模型资产名称"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="描述"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """将训练结果发布为模型资产"""
    client = PanguClient()
    path = DETAIL_PATH + "/publish"
    body: dict = {}
    if checkpoint_id:
        body["checkpoint_id"] = checkpoint_id
    if asset_name:
        body["asset_name"] = asset_name
    if description:
        body["description"] = description

    data = client.post(path, workspace_id=workspace, json=body, job_id=job_id)
    output(data, fmt=fmt)
    console.print("[green]模型发布任务已创建[/green]")


@app.command("versions")
def list_versions(
    job_id: str = typer.Argument(help="任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询训练任务的历史版本列表"""
    client = PanguClient()
    data = client.get(VERSIONS_PATH, workspace_id=workspace, job_id=job_id)

    output(
        data,
        fmt=fmt,
        columns=VERSION_COLUMNS,
        list_key="versions",
        title=f"训练版本 ({job_id})",
        status_key="status",
        id_key="version_id",
    )


@app.command("usage")
def job_usage(
    job_id: str = typer.Argument(help="任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查询训练任务资源用量"""
    client = PanguClient()
    path = DETAIL_PATH + "/resource-usage"
    data = client.get(path, workspace_id=workspace, job_id=job_id)
    output(data, fmt=fmt)


@app.command("running")
def running_jobs(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询当前正在运行的训练任务"""
    client = PanguClient()
    params = {"status": "running", "limit": 100, "offset": 0}
    data = client.get(BASE_PATH, workspace_id=workspace, params=params)
    output(
        data,
        fmt=fmt,
        columns=LIST_COLUMNS,
        list_key="jobs",
        title="运行中的训练任务",
        status_key="status",
        id_key="job_id",
    )
