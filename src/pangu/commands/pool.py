"""资源池管理命令 - pangu pool list"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from pangu.client import PanguClient
from pangu.output import output

app = typer.Typer(help="资源池管理")
console = Console()

BASE_PATH = "/v1/{project_id}/pangu/studio/resource-pool/online/{workspace_id}/pool"


@app.command("list")
def list_pools(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式: table/json/yaml"),
):
    """查询资源池列表"""
    client = PanguClient()
    wid = client.config.get_workspace_id(workspace)

    data = client.post(BASE_PATH, workspace_id=wid, json={})

    # 资源池接口返回格式可能因版本不同有差异，兼容处理
    if isinstance(data, dict) and "pools" in data:
        items = data["pools"]
    elif isinstance(data, list):
        items = data
    else:
        items = [data] if data else []

    columns = [
        ("pool_id", "资源池 ID"),
        ("pool_name", "名称"),
        ("pool_type", "类型"),
        ("status", "状态"),
        ("node_count", "节点数"),
    ]

    output(
        items,
        fmt=fmt,
        columns=columns,
        title="资源池",
        status_key="status",
    )
