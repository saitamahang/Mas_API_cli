"""资源池管理命令 - pangu pool list"""

from __future__ import annotations

from typing import List, Optional

import typer
from rich.console import Console

from pangu.client import PanguClient
from pangu.output import output

app = typer.Typer(help="资源池管理")
console = Console()

BASE_PATH = "/v1/{project_id}/pangu/studio/resource-pool/online/{workspace_id}/pool"


def _flatten_pool(pool: dict) -> dict:
    """将 API 响应的嵌套 pool 对象拍平为可直接展示的字典"""
    metadata = pool.get("metadata") or {}
    labels = metadata.get("labels") or {}
    spec = pool.get("spec") or {}
    status = pool.get("status") or {}

    scope_list = spec.get("scope") or []
    resources = spec.get("resources") or []
    nodes = pool.get("nodes") or []

    total_nodes = len(nodes)
    total_count = sum(r.get("count", 0) for r in resources)

    return {
        "pool_id": metadata.get("name", ""),
        "pool_name": labels.get("os.modelarts/name", ""),
        "pool_type": spec.get("type", ""),
        "status": status.get("phase", ""),
        "scope": "/".join(scope_list),
        "node_count": total_nodes or total_count,
        "chip_type": pool.get("chip_type", ""),
        "arch": pool.get("arch", ""),
        "create_time": metadata.get("creationTimestamp", metadata.get("create_time", "")),
    }


@app.command("list")
def list_pools(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    arch: str = typer.Option("X86", "--arch", help="架构类型: X86 | ARM"),
    device_type: Optional[str] = typer.Option(None, "--device-type", help="设备类型: GPU | NPU | NONE"),
    job_type: Optional[str] = typer.Option(None, "--job-type", help="作业类型: Train | Infer"),
    status: Optional[str] = typer.Option(None, "--status", help="资源池状态: created | failed | creating"),
    chip_types: Optional[List[str]] = typer.Option(None, "--chip-type", help="卡类型，可多次传入"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式: table/json/yaml/id"),
):
    """查询资源池列表"""
    client = PanguClient()

    body: dict = {"arch": arch}
    if device_type:
        body["device_type"] = device_type
    if job_type:
        body["job_type"] = job_type
    if status:
        body["status"] = status
    if chip_types:
        body["chip_types"] = chip_types

    data = client.post(BASE_PATH, workspace_id=workspace, json=body)

    raw_pools = []
    if isinstance(data, dict):
        raw_pools = data.get("pools") or []
    elif isinstance(data, list):
        raw_pools = data

    items = [_flatten_pool(p) for p in raw_pools]

    columns = [
        ("pool_id", "资源池 ID"),
        ("pool_name", "名称"),
        ("pool_type", "类型"),
        ("status", "状态"),
        ("scope", "支持作业"),
        ("node_count", "节点数"),
        ("chip_type", "芯片"),
        ("arch", "架构"),
    ]

    output(
        items,
        fmt=fmt,
        columns=columns,
        title="资源池",
        status_key="status",
        id_key="pool_id",
    )
