"""资源池管理命令 - pangu pool list"""

from __future__ import annotations

from typing import List, Optional

import typer
from rich.console import Console

from pangu.adapters import get_pool_adapter
from pangu.adapters.base import PoolRequest
from pangu.client import PanguClient
from pangu.output import output

app = typer.Typer(help="资源池管理")
console = Console()

# 两个版本共用的展示列（normalize 后字段名统一）
COLUMNS = [
    ("pool_id",    "资源池 ID"),
    ("pool_name",  "名称"),
    ("pool_type",  "类型"),
    ("status",     "状态"),
    ("scope",      "作业类型"),
    ("node_count", "节点数"),
    ("chip_type",  "芯片"),
    ("flavor_id",  "规格 ID"),
    ("arch",       "架构"),
    ("create_time","创建时间"),
]


@app.command("list")
def list_pools(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    # HCS 参数
    arch: str = typer.Option("X86", "--arch", help="[HCS] 架构类型: X86 | ARM"),
    device_type: Optional[str] = typer.Option(None, "--device-type", help="[HCS] 设备类型: GPU | NPU | NONE"),
    filter_status: Optional[str] = typer.Option(None, "--status", help="[HCS] 资源池状态: created (创建成功) | creating (创建中) | failed (创建失败，记录保留3天)"),
    # HC 参数
    job_type: Optional[str] = typer.Option(None, "--job-type", help="作业类型 — HCS: Train (训练) | Infer (推理) 大写驼峰；HC: train | infer 小写（HC 必填）"),
    chip_types: Optional[List[str]] = typer.Option(None, "--chip-type", help="[HC 必填] 卡类型，可多次传入；常用值 D910B3（默认建议值，未传时不在代码侧自动补，需显式 --chip-type D910B3）"),
    use_type: Optional[str] = typer.Option(None, "--use-type", help="[HC 必填] 使用类型；常用值 private（默认建议值，未传时不在代码侧自动补，需显式 --use-type private）"),
    flavor_ids: Optional[List[str]] = typer.Option(None, "--flavor-id", help="[HC] 资源规格 ID，可多次传入"),
    asset_code: Optional[str] = typer.Option(None, "--asset-code", help="[HC] 资产编码"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式: table (表格) | json | yaml | id (仅 ID 列表)"),
):
    """查询资源池列表（env_type=HCS/HC 由 pangu config set env_type 控制）"""
    client  = PanguClient()
    adapter = get_pool_adapter(client.config.env_type)

    req = PoolRequest(
        arch=arch,
        device_type=device_type,
        status=filter_status,
        job_type=job_type,
        chip_types=chip_types,
        use_type=use_type,
        flavor_ids=flavor_ids,
        asset_code=asset_code,
    )
    body = adapter.build_request(req)

    if adapter.workspace_in_path:
        data = client.post(adapter.path, workspace_id=workspace, json=body)
    else:
        wid = client.config.get_workspace_id(workspace)
        extra_hdrs = adapter.extra_headers(wid)
        data = client.post(adapter.path, workspace_id=None, json=body, extra_headers=extra_hdrs)

    items = adapter.normalize(data)

    output(
        items,
        fmt=fmt,
        columns=COLUMNS,
        title=f"资源池 (env={client.config.env_type})",
        status_key="status",
        id_key="pool_id",
    )
