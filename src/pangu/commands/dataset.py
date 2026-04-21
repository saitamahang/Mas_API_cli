"""数据集管理命令 - pangu dataset list/get/delete/import/publish/..."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console

from pangu.client import PanguClient
from pangu.output import output

app = typer.Typer(help="数据集管理")
console = Console()

BASE_PATH = "/v1/{project_id}/workspaces/{workspace_id}/data-management/datasets"
DETAIL_PATH = BASE_PATH + "/{dataset_id}"
PUBLISH_PATH = BASE_PATH + "/{dataset_id}/data-annotations"
OPERATORS_PATH = "/v1/{project_id}/workspaces/{workspace_id}/data-management/operators"
PROCESS_PATH = BASE_PATH + "/{dataset_id}/data-processes"

LIST_COLUMNS = [
    ("dataset_id", "数据集 ID"),
    ("name", "名称"),
    ("type", "类型"),
    ("status", "状态"),
    ("sample_count", "样本数"),
    ("create_time", "创建时间"),
]

DETAIL_FIELDS = [
    ("dataset_id", "数据集 ID"),
    ("name", "名称"),
    ("type", "类型"),
    ("status", "状态"),
    ("description", "描述"),
    ("sample_count", "样本数"),
    ("managed", "是否托管"),
    ("obs_path", "OBS 路径"),
    ("create_time", "创建时间"),
    ("update_time", "更新时间"),
]


@app.command("list")
def list_datasets(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    dataset_type: Optional[str] = typer.Option(None, "--type", "-t", help="数据集类型: text/image/audio/video/table"),
    name: Optional[str] = typer.Option(None, "--name", help="按名称搜索"),
    status: Optional[str] = typer.Option(None, "--status", help="状态过滤"),
    limit: int = typer.Option(20, "--limit", help="每页数量"),
    offset: int = typer.Option(0, "--offset", help="起始偏移"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式: table/json/yaml/id"),
):
    """查询数据集列表"""
    client = PanguClient()
    params: dict = {"limit": limit, "offset": offset}
    if dataset_type:
        params["type"] = dataset_type
    if name:
        params["name"] = name
    if status:
        params["status"] = status

    data = client.get(BASE_PATH, workspace_id=workspace, params=params)
    output(
        data,
        fmt=fmt,
        columns=LIST_COLUMNS,
        list_key="datasets",
        title="数据集",
        status_key="status",
        id_key="dataset_id",
    )


@app.command("get")
def get_dataset(
    dataset_id: str = typer.Argument(help="数据集 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询数据集详情"""
    client = PanguClient()
    data = client.get(DETAIL_PATH, workspace_id=workspace, dataset_id=dataset_id)
    output(
        data,
        fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title=f"数据集: {data.get('name', '')}",
        status_key="status",
    )


@app.command("delete")
def delete_dataset(
    dataset_id: str = typer.Argument(help="数据集 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
):
    """删除数据集"""
    if not yes:
        if not typer.confirm(f"确认删除数据集 {dataset_id}?"):
            raise typer.Abort()

    client = PanguClient()
    client.delete(DETAIL_PATH, workspace_id=workspace, dataset_id=dataset_id)
    console.print(f"[green]数据集 {dataset_id} 已删除[/green]")


@app.command("purge")
def purge_dataset(
    dataset_id: str = typer.Argument(help="数据集 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认 (将彻底删除数据)"),
):
    """彻底清除数据集及其所有数据 (不可恢复)"""
    if not yes:
        if not typer.confirm(f"[警告] 彻底清除数据集 {dataset_id} 的所有数据? 此操作不可恢复!"):
            raise typer.Abort()

    client = PanguClient()
    path = DETAIL_PATH + "/purge"
    client.post(path, workspace_id=workspace, json={}, dataset_id=dataset_id)
    console.print(f"[green]数据集 {dataset_id} 已彻底清除[/green]")


@app.command("import")
def import_data(
    dataset_id: str = typer.Argument(help="数据集 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    obs_path: Optional[str] = typer.Option(None, "--obs-path", help="OBS 数据路径"),
    import_type: str = typer.Option("obs", "--import-type", help="导入类型: obs/local"),
    config: Optional[str] = typer.Option(None, "--config", "-f", help="YAML 配置文件路径"),
    wait: bool = typer.Option(False, "--wait", help="等待导入完成"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """从 OBS 路径导入数据到数据集"""
    client = PanguClient()
    path = DETAIL_PATH + "/import-tasks"

    body: dict = {"import_type": import_type}
    if config:
        p = Path(config)
        if not p.exists():
            console.print(f"[red]配置文件不存在: {config}[/red]")
            raise typer.Exit(1)
        with p.open() as f:
            body.update(yaml.safe_load(f) or {})

    if obs_path:
        body["obs_path"] = obs_path

    if not body.get("obs_path"):
        console.print("[red]必须提供 OBS 路径 (--obs-path 或配置文件中 obs_path)[/red]")
        raise typer.Exit(1)

    data = client.post(path, workspace_id=workspace, json=body, dataset_id=dataset_id)
    task_id = data.get("task_id", "")
    output(data, fmt=fmt)
    console.print(f"[green]导入任务已创建: {task_id}[/green]")

    if wait and task_id:
        status_path = DETAIL_PATH + f"/import-tasks/{task_id}"
        console.print(f"[cyan]等待导入完成...[/cyan]")
        final = client.wait_for_status(
            status_path,
            target_statuses=["succeeded", "failed"],
            failure_statuses=["failed"],
            status_key="status",
            workspace_id=workspace,
            dataset_id=dataset_id,
        )
        console.print(f"[green]导入完成，状态: {final.get('status')}[/green]")


@app.command("publish")
def publish_dataset(
    dataset_id: str = typer.Argument(help="数据集 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    version_name: Optional[str] = typer.Option(None, "--version-name", help="版本名称"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="版本描述"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """发布数据集为新版本"""
    client = PanguClient()
    body: dict = {}
    if version_name:
        body["version_name"] = version_name
    if description:
        body["description"] = description

    data = client.post(PUBLISH_PATH, workspace_id=workspace, json=body, dataset_id=dataset_id)
    output(data, fmt=fmt)
    console.print("[green]数据集版本发布成功[/green]")


@app.command("publish-list")
def list_published(
    dataset_id: str = typer.Argument(help="数据集 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    limit: int = typer.Option(20, "--limit", help="每页数量"),
    offset: int = typer.Option(0, "--offset", help="起始偏移"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询数据集已发布版本列表"""
    client = PanguClient()
    params = {"limit": limit, "offset": offset}
    data = client.get(PUBLISH_PATH, workspace_id=workspace, params=params, dataset_id=dataset_id)

    columns = [
        ("annotation_id", "版本 ID"),
        ("version_name", "版本名"),
        ("status", "状态"),
        ("sample_count", "样本数"),
        ("create_time", "创建时间"),
    ]
    output(data, fmt=fmt, columns=columns, list_key="annotations", title=f"数据集版本 ({dataset_id})", status_key="status")


@app.command("publish-delete")
def delete_published(
    dataset_id: str = typer.Argument(help="数据集 ID"),
    annotation_id: str = typer.Argument(help="版本 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
):
    """删除数据集已发布版本"""
    if not yes:
        if not typer.confirm(f"确认删除版本 {annotation_id}?"):
            raise typer.Abort()

    client = PanguClient()
    path = PUBLISH_PATH + "/{annotation_id}"
    client.delete(path, workspace_id=workspace, dataset_id=dataset_id, annotation_id=annotation_id)
    console.print(f"[green]版本 {annotation_id} 已删除[/green]")


@app.command("process")
def process_dataset(
    dataset_id: str = typer.Argument(help="数据集 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    operator: Optional[str] = typer.Option(None, "--operator", help="算子名称"),
    config: Optional[str] = typer.Option(None, "--config", "-f", help="YAML 配置文件路径"),
    wait: bool = typer.Option(False, "--wait", help="等待处理完成"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """对数据集执行数据处理任务"""
    client = PanguClient()
    body: dict = {}

    if config:
        p = Path(config)
        if not p.exists():
            console.print(f"[red]配置文件不存在: {config}[/red]")
            raise typer.Exit(1)
        with p.open() as f:
            body.update(yaml.safe_load(f) or {})

    if operator:
        body.setdefault("operators", [{"operator_name": operator}])

    data = client.post(PROCESS_PATH, workspace_id=workspace, json=body, dataset_id=dataset_id)
    task_id = data.get("task_id", "")
    output(data, fmt=fmt)
    console.print(f"[green]数据处理任务已创建: {task_id}[/green]")

    if wait and task_id:
        status_path = PROCESS_PATH + f"/{task_id}"
        console.print("[cyan]等待处理完成...[/cyan]")
        final = client.wait_for_status(
            status_path,
            target_statuses=["succeeded", "failed"],
            failure_statuses=["failed"],
            status_key="status",
            workspace_id=workspace,
            dataset_id=dataset_id,
        )
        console.print(f"[green]处理完成，状态: {final.get('status')}[/green]")


@app.command("operators")
def list_operators(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    category: Optional[str] = typer.Option(None, "--category", help="算子类别"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询可用数据处理算子列表"""
    client = PanguClient()
    params = {}
    if category:
        params["category"] = category

    data = client.get(OPERATORS_PATH, workspace_id=workspace, params=params or None)

    columns = [
        ("operator_id", "算子 ID"),
        ("operator_name", "算子名称"),
        ("category", "类别"),
        ("description", "描述"),
    ]
    output(data, fmt=fmt, columns=columns, list_key="operators", title="数据处理算子")


@app.command("lineage")
def dataset_lineage(
    dataset_id: str = typer.Argument(help="数据集 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查询数据集血缘关系"""
    client = PanguClient()
    path = DETAIL_PATH + "/lineage"
    data = client.get(path, workspace_id=workspace, dataset_id=dataset_id)
    output(data, fmt=fmt)
