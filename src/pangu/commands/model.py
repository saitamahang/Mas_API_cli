"""资产管理命令 - pangu model list/get/list-ext/export/export-tasks"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from pangu.client import PanguClient
from pangu.output import output

app = typer.Typer(help="模型资产管理")
console = Console()

BASE_PATH = "/v1/{project_id}/workspaces/{workspace_id}/asset-manager/model-assets"
DETAIL_PATH = BASE_PATH + "/{asset_id}"
EXT_PATH = "/v1/{project_id}/workspaces/{workspace_id}/asset-manager/model-assets-ext"
EXPORT_TASKS_PATH = BASE_PATH + "/{asset_id}/export-tasks"

LIST_COLUMNS = [
    ("asset_id", "资产 ID"),
    ("asset_name", "名称"),
    ("asset_type", "类型"),
    ("sub_asset_type", "子类型"),
    ("category", "来源"),
    ("create_time", "创建时间"),
]

DETAIL_FIELDS = [
    ("asset_id", "资产 ID"),
    ("asset_name", "名称"),
    ("asset_type", "类型"),
    ("sub_asset_type", "子类型"),
    ("category", "来源"),
    ("description", "描述"),
    ("create_time", "创建时间"),
    ("update_time", "更新时间"),
]


@app.command("list")
def list_models(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    asset_type: Optional[str] = typer.Option(None, "--type", "-t", help="模型类型: NLP/CV/MM/Predict/AI4Science/Profession"),
    category: Optional[str] = typer.Option(None, "--category", help="来源: pangu/3rd/pangu-poc/pangu-iit/3rd-pangu"),
    name: Optional[str] = typer.Option(None, "--name", help="按名称搜索"),
    limit: int = typer.Option(20, "--limit", help="每页数量"),
    offset: int = typer.Option(0, "--offset", help="起始偏移"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询模型资产列表"""
    client = PanguClient()
    params = {
        "limit": limit,
        "offset": offset,
    }
    if asset_type:
        params["asset_type"] = asset_type
    if category:
        params["category"] = category
    if name:
        params["asset_name"] = name

    data = client.get(BASE_PATH, workspace_id=workspace, params=params)

    output(
        data,
        fmt=fmt,
        columns=LIST_COLUMNS,
        list_key="assets",
        title="模型资产",
        id_key="asset_id",
    )


@app.command("get")
def get_model(
    asset_id: str = typer.Argument(help="资产 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询模型资产详情"""
    client = PanguClient()
    data = client.get(DETAIL_PATH, workspace_id=workspace, asset_id=asset_id)

    output(
        data,
        fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title=f"模型: {data.get('asset_name', '')}",
    )


@app.command("list-ext")
def list_ext(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    asset_type: Optional[str] = typer.Option(None, "--type", "-t", help="模型类型"),
    limit: int = typer.Option(20, "--limit", help="每页数量"),
    offset: int = typer.Option(0, "--offset", help="起始偏移"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """获取含部署信息的完整模型列表"""
    client = PanguClient()
    params = {"limit": limit, "offset": offset}
    if asset_type:
        params["asset_type"] = asset_type

    data = client.get(EXT_PATH, workspace_id=workspace, params=params)

    output(
        data,
        fmt=fmt,
        columns=LIST_COLUMNS,
        list_key="assets",
        title="模型资产 (完整)",
        id_key="asset_id",
    )


@app.command("export")
def export_model(
    asset_id: str = typer.Argument(help="资产 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """导出模型为 ModelArts Site 格式"""
    client = PanguClient()
    path = BASE_PATH + "/{asset_id}/export"
    data = client.post(path, workspace_id=workspace, json={}, asset_id=asset_id)

    output(data, fmt=fmt)
    console.print("[green]导出任务已创建[/green]")


@app.command("export-tasks")
def export_tasks(
    asset_id: str = typer.Argument(help="资产 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询模型导出任务列表"""
    client = PanguClient()
    data = client.get(EXPORT_TASKS_PATH, workspace_id=workspace, asset_id=asset_id)

    columns = [
        ("task_id", "任务 ID"),
        ("status", "状态"),
        ("create_time", "创建时间"),
    ]
    output(data, fmt=fmt, columns=columns, title="导出任务", status_key="status")
