"""空间管理命令 - pangu workspace list/get/create/update/delete"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from pangu.client import PanguClient, APIError
from pangu.config import PanguConfig
from pangu.output import output

app = typer.Typer(help="空间管理")
console = Console()

BASE_PATH = "/v1/{project_id}/workspaces"
DETAIL_PATH = "/v1/{project_id}/workspaces/{workspace_id}"

LIST_COLUMNS = [
    ("id", "ID"),
    ("name", "名称"),
    ("status", "状态"),
    ("workspace_owner", "所有者"),
    ("create_user", "创建人"),
    ("create_time", "创建时间"),
]

DETAIL_FIELDS = [
    ("id", "空间 ID"),
    ("name", "名称"),
    ("description", "描述"),
    ("status", "状态"),
    ("project_id", "项目 ID"),
    ("domain_id", "账号 ID"),
    ("workspace_owner", "所有者"),
    ("create_user", "创建人"),
    ("update_user", "更新人"),
    ("create_time", "创建时间"),
    ("update_time", "更新时间"),
    ("extend_properties", "扩展属性"),
]


@app.command("list")
def list_workspaces(
    user_id: Optional[str] = typer.Option(None, "--user-id", help="按用户 ID 过滤"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式: table/json/yaml/id"),
):
    """查询空间列表"""
    client = PanguClient()
    params = {}
    if user_id:
        params["user_id"] = user_id

    data = client.get(BASE_PATH, params=params or None)

    output(
        data,
        fmt=fmt,
        columns=LIST_COLUMNS,
        list_key="workspaces",
        title="工作空间",
        status_key="status",
        id_key="id",
    )


@app.command("get")
def get_workspace(
    workspace_id: str = typer.Argument(help="空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式: table/json/yaml"),
):
    """查询空间详情"""
    client = PanguClient()
    data = client.get(DETAIL_PATH, workspace_id=workspace_id)

    output(
        data,
        fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title=f"空间: {data.get('name', '')}",
        status_key="status",
    )


@app.command("create")
def create_workspace(
    name: str = typer.Option(..., "--name", help="空间名称 (1-32字符)"),
    description: str = typer.Option("", "--description", "-d", help="空间描述"),
    obs_ak: Optional[str] = typer.Option(None, "--obs-ak", help="OBS Access Key"),
    obs_sk: Optional[str] = typer.Option(None, "--obs-sk", help="OBS Secret Key"),
    obs_bucket: Optional[str] = typer.Option(None, "--obs-bucket", help="OBS Bucket 名称"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """新建工作空间"""
    client = PanguClient()
    body: dict = {"name": name}
    if description:
        body["description"] = description

    if obs_ak or obs_sk or obs_bucket:
        extend = {"obs": {}}
        if obs_ak:
            extend["obs"]["ak"] = obs_ak
        if obs_sk:
            extend["obs"]["sk"] = f"SECRET@{obs_sk}"
        if obs_bucket:
            extend["obs"]["bucket_name"] = obs_bucket
        body["extend_properties"] = str(extend)

    data = client.post(BASE_PATH, json=body)

    output(
        data,
        fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title="空间创建成功",
        status_key="status",
    )


@app.command("update")
def update_workspace(
    workspace_id: str = typer.Argument(help="空间 ID"),
    name: Optional[str] = typer.Option(None, "--name", help="新名称"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="新描述"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """修改工作空间"""
    client = PanguClient()
    body: dict = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description

    if not body:
        console.print("[yellow]未指定任何修改项[/yellow]")
        raise typer.Exit(1)

    data = client.put(DETAIL_PATH, workspace_id=workspace_id, json=body)

    output(
        data,
        fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title="空间更新成功",
        status_key="status",
    )


@app.command("delete")
def delete_workspace(
    workspace_id: str = typer.Argument(help="空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
):
    """删除工作空间"""
    if not yes:
        confirm = typer.confirm(f"确认删除空间 {workspace_id}?")
        if not confirm:
            raise typer.Abort()

    client = PanguClient()
    data = client.delete(DETAIL_PATH, workspace_id=workspace_id)
    console.print(f"[green]空间 {workspace_id} 已删除[/green]")
