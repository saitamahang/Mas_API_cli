"""推理服务管理命令 - pangu service list/get/deploy/update/delete/start/stop/logs/node-logs/monitor/tasks/usage"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console

from pangu.client import PanguClient
from pangu.output import output

app = typer.Typer(help="推理服务管理")
console = Console()

BASE_PATH = "/v1/{project_id}/workspaces/{workspace_id}/model-service/services"
DETAIL_PATH = BASE_PATH + "/{service_id}"
START_STOP_PATH = DETAIL_PATH + "/start-or-stop"
RUNLOG_PATH = DETAIL_PATH + "/runlog"
NODE_RUNLOG_PATH = DETAIL_PATH + "/nodes/{model_node_id}/runlogs"
MONITOR_PATH = DETAIL_PATH + "/monitors"
TASKS_PATH = "/v1/{project_id}/model-service/tasks"
USAGE_PATH = "/v1/{project_id}/workspaces/{workspace_id}/model-service/resource-usage"

LIST_COLUMNS = [
    ("service_id", "服务 ID"),
    ("service_name", "名称"),
    ("asset_type", "模型类型"),
    ("infer_type", "部署类型"),
    ("status", "状态"),
    ("device_type", "设备"),
    ("arch", "架构"),
    ("cluster_name", "资源池"),
    ("create_time", "创建时间"),
]

DETAIL_FIELDS = [
    ("service_id", "服务 ID"),
    ("service_name", "名称"),
    ("service_desc", "描述"),
    ("status", "状态"),
    ("asset_type", "模型类型"),
    ("category", "来源"),
    ("infer_type", "部署类型"),
    ("request_mode", "请求模式"),
    ("arch", "架构"),
    ("device_type", "设备类型"),
    ("chip_type", "芯片类型"),
    ("cluster_name", "资源池"),
    ("cluster_id", "资源池 ID"),
    ("security_bar_type", "安全护栏"),
    ("api_url", "API URL"),
    ("access_url", "访问地址"),
    ("user_name", "创建人"),
    ("create_time", "创建时间"),
    ("update_time", "更新时间"),
    ("is_rollback", "是否回滚"),
]


def _load_yaml_config(config_path: str) -> dict:
    """加载 YAML 配置文件"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_deploy_body(
    config: Optional[str] = None,
    name: Optional[str] = None,
    asset_id: Optional[str] = None,
    asset_type: Optional[str] = None,
    arch: Optional[str] = None,
    infer_type: Optional[str] = None,
    device_type: Optional[str] = None,
    chip_type: Optional[str] = None,
    request_mode: Optional[str] = None,
    category: Optional[str] = None,
    pool_id: Optional[str] = None,
    instances: Optional[int] = None,
    elb_id: Optional[str] = None,
    scene: Optional[str] = None,
    security_bar_type: Optional[str] = None,
    security_bar_edition: Optional[str] = None,
    desc: Optional[str] = None,
) -> dict:
    """构建部署请求体：YAML 配置 + 命令行参数合并，命令行优先"""
    body = {}
    if config:
        body = _load_yaml_config(config)

    # 命令行参数覆盖 YAML
    overrides = {
        "service_name": name,
        "service_desc": desc,
        "asset_id": asset_id,
        "asset_type": asset_type,
        "arch": arch,
        "infer_type": infer_type,
        "device_type": device_type,
        "chip_type": chip_type,
        "request_mode": request_mode,
        "category": category,
        "scene": scene,
        "security_bar_type": security_bar_type,
        "security_bar_edition": security_bar_edition,
        "elb_id": elb_id,
    }
    for k, v in overrides.items():
        if v is not None:
            body[k] = v

    # service_config 处理
    if "service_config" not in body:
        body["service_config"] = {}
    if instances is not None:
        body["service_config"]["instance_count"] = instances
    if pool_id is not None:
        body["service_config"]["specification"] = "custom"
        if "custom_spec" not in body["service_config"]:
            body["service_config"]["custom_spec"] = {}
        body["service_config"]["custom_spec"]["resource_pool_id"] = pool_id

    # model_config 默认值
    if "model_config" not in body:
        body["model_config"] = {}

    # infer_type 默认值
    if "infer_type" not in body:
        body["infer_type"] = "online"

    # request_mode 默认值
    if "request_mode" not in body:
        body["request_mode"] = "sync"

    return body


# ---- 命令 ----


@app.command("list")
def list_services(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="状态过滤: running/stopped/deploying/failed"),
    asset_type: Optional[str] = typer.Option(None, "--type", "-t", help="模型类型: NLP/CV/MM/Predict/AI4Science"),
    infer_type: Optional[str] = typer.Option(None, "--infer-type", help="部署类型: online/edge"),
    name: Optional[str] = typer.Option(None, "--name", help="按名称搜索"),
    sort_by: str = typer.Option("create_time", "--sort-by", help="排序字段: create_time/service_name"),
    order: str = typer.Option("desc", "--order", help="排序方向: desc/asc"),
    limit: int = typer.Option(20, "--limit", help="每页数量"),
    offset: int = typer.Option(0, "--offset", help="起始偏移"),
    status_only: bool = typer.Option(False, "--status-only", help="只显示状态统计"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询推理服务列表"""
    client = PanguClient()
    params = {
        "limit": limit,
        "offset": offset,
        "sort_by": sort_by,
        "order": order,
    }
    if status:
        params["status"] = status
    if asset_type:
        params["asset_type"] = asset_type
    if infer_type:
        params["infer_type"] = infer_type
    if name:
        params["service_name"] = name

    data = client.get(BASE_PATH, workspace_id=workspace, params=params)

    if status_only:
        counts = data.get("status_count", [])
        for item in counts:
            console.print(f"  {item.get('status', '?')}: {item.get('count', 0)}")
        return

    # 展平 asset_type：从 assets[0].asset_type 取
    services = data.get("services", [])
    for svc in services:
        assets = svc.get("assets", [])
        if assets and "asset_type" not in svc:
            svc["asset_type"] = assets[0].get("asset_type", "")

    output(
        data,
        fmt=fmt,
        columns=LIST_COLUMNS,
        list_key="services",
        title="推理服务",
        status_key="status",
        id_key="service_id",
    )


@app.command("get")
def get_service(
    service_id: str = typer.Argument(help="服务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查询服务详情"""
    client = PanguClient()
    data = client.get(DETAIL_PATH, workspace_id=workspace, service_id=service_id)

    # 展平 asset_type
    assets = data.get("assets", [])
    if assets and "asset_type" not in data:
        data["asset_type"] = assets[0].get("asset_type", "")

    output(
        data,
        fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title=f"服务: {data.get('service_name', '')}",
        status_key="status",
    )


@app.command("deploy")
def deploy_service(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="YAML 配置文件路径"),
    name: Optional[str] = typer.Option(None, "--name", help="服务名称"),
    desc: Optional[str] = typer.Option(None, "--desc", help="服务描述"),
    asset_id: Optional[str] = typer.Option(None, "--asset-id", help="模型资产 ID"),
    asset_type: Optional[str] = typer.Option(None, "--asset-type", help="模型类型: NLP/CV/MM/Predict/AI4Science/Profession"),
    arch: Optional[str] = typer.Option(None, "--arch", help="架构: ARM/X86"),
    infer_type: Optional[str] = typer.Option(None, "--infer-type", help="部署类型: online/edge"),
    device_type: Optional[str] = typer.Option(None, "--device-type", help="设备: NPU/GPU/NONE"),
    chip_type: Optional[str] = typer.Option(None, "--chip-type", help="芯片类型"),
    request_mode: Optional[str] = typer.Option(None, "--request-mode", help="请求模式: sync/async"),
    category: Optional[str] = typer.Option(None, "--category", help="来源: pangu/3rd"),
    pool_id: Optional[str] = typer.Option(None, "--pool-id", help="资源池 ID"),
    instances: Optional[int] = typer.Option(None, "--instances", "-n", help="实例数 (1-128)"),
    elb_id: Optional[str] = typer.Option(None, "--elb-id", help="负载均衡 ID (边缘部署)"),
    scene: Optional[str] = typer.Option(None, "--scene", help="场景: Weather/Precip/Ocean/..."),
    security_bar_type: Optional[str] = typer.Option(None, "--security-bar", help="安全护栏: ENABLE/DISABLE"),
    security_bar_edition: Optional[str] = typer.Option(None, "--security-bar-edition", help="护栏版本: BASE/ADVANCED"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    wait: bool = typer.Option(False, "--wait", help="等待部署完成"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """部署模型服务"""
    if not config and not name:
        console.print("[red]请通过 --config 指定 YAML 文件，或通过 --name 指定服务名称[/red]")
        raise typer.Exit(1)

    body = _build_deploy_body(
        config=config, name=name, desc=desc, asset_id=asset_id,
        asset_type=asset_type, arch=arch, infer_type=infer_type,
        device_type=device_type, chip_type=chip_type, request_mode=request_mode,
        category=category, pool_id=pool_id, instances=instances,
        elb_id=elb_id, scene=scene, security_bar_type=security_bar_type,
        security_bar_edition=security_bar_edition,
    )

    # 必填参数校验
    required = ["service_name", "asset_id", "arch", "infer_type"]
    missing = [k for k in required if not body.get(k)]
    if missing:
        console.print(f"[red]缺少必填参数: {', '.join(missing)}[/red]")
        raise typer.Exit(1)

    client = PanguClient()
    data = client.post(BASE_PATH, workspace_id=workspace, json=body)

    service_id = data.get("service_id", "")
    console.print(f"[green]服务部署已提交，service_id: {service_id}[/green]")

    if wait and service_id:
        console.print("等待部署完成...")
        result = client.wait_for_status(
            poll_fn=lambda: client.get(DETAIL_PATH, workspace_id=workspace, service_id=service_id),
            target_statuses={"running"},
            failure_statuses={"failed"},
            interval=15,
            timeout=3600,
        )
        data = result

    output(
        data,
        fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title="服务部署",
        status_key="status",
    )


@app.command("update")
def update_service(
    service_id: str = typer.Argument(help="服务 ID"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="YAML 配置文件"),
    instances: Optional[int] = typer.Option(None, "--instances", "-n", help="实例数"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    wait: bool = typer.Option(False, "--wait", help="等待更新完成"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """更新服务配置"""
    body = {}
    if config:
        body = _load_yaml_config(config)
    if instances is not None:
        if "service_config" not in body:
            body["service_config"] = {}
        body["service_config"]["instance_count"] = instances

    if not body:
        console.print("[yellow]未指定任何修改项[/yellow]")
        raise typer.Exit(1)

    client = PanguClient()
    data = client.put(DETAIL_PATH, workspace_id=workspace, json=body, service_id=service_id)

    if wait:
        console.print("等待更新完成...")
        result = client.wait_for_status(
            poll_fn=lambda: client.get(DETAIL_PATH, workspace_id=workspace, service_id=service_id),
            target_statuses={"running"},
            failure_statuses={"failed"},
            interval=15,
        )
        data = result

    output(data, fmt=fmt, detail_fields=DETAIL_FIELDS, title="服务更新", status_key="status")


@app.command("delete")
def delete_service(
    service_id: str = typer.Argument(help="服务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
):
    """删除服务"""
    if not yes:
        confirm = typer.confirm(f"确认删除服务 {service_id}?")
        if not confirm:
            raise typer.Abort()

    client = PanguClient()
    client.delete(DETAIL_PATH, workspace_id=workspace, service_id=service_id)
    console.print(f"[green]服务 {service_id} 已删除[/green]")


@app.command("start")
def start_service(
    service_id: str = typer.Argument(help="服务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    wait: bool = typer.Option(False, "--wait", help="等待启动完成"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """启动服务"""
    client = PanguClient()
    data = client.post(
        START_STOP_PATH,
        workspace_id=workspace,
        json={"status": "running"},
        service_id=service_id,
    )

    console.print(f"[green]服务 {service_id} 启动中...[/green]")

    if wait:
        result = client.wait_for_status(
            poll_fn=lambda: client.get(DETAIL_PATH, workspace_id=workspace, service_id=service_id),
            target_statuses={"running"},
            failure_statuses={"failed"},
            interval=10,
        )
        data = result

    output(data, fmt=fmt, detail_fields=DETAIL_FIELDS, title="服务启动", status_key="status")


@app.command("stop")
def stop_service(
    service_id: str = typer.Argument(help="服务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """停止服务"""
    if not yes:
        confirm = typer.confirm(f"确认停止服务 {service_id}?")
        if not confirm:
            raise typer.Abort()

    client = PanguClient()
    data = client.post(
        START_STOP_PATH,
        workspace_id=workspace,
        json={"status": "stopped"},
        service_id=service_id,
    )

    console.print(f"[green]服务 {service_id} 停止中...[/green]")
    output(data, fmt=fmt, detail_fields=DETAIL_FIELDS, title="服务停止", status_key="status")


@app.command("logs")
def service_logs(
    service_id: str = typer.Argument(help="服务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查看服务运行日志"""
    client = PanguClient()
    data = client.post(RUNLOG_PATH, workspace_id=workspace, json={}, service_id=service_id)
    output(data, fmt=fmt)


@app.command("node-logs")
def service_node_logs(
    service_id: str = typer.Argument(help="服务 ID"),
    node_id: str = typer.Argument(help="节点 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查看指定节点运行日志"""
    client = PanguClient()
    data = client.post(
        NODE_RUNLOG_PATH,
        workspace_id=workspace,
        json={},
        service_id=service_id,
        model_node_id=node_id,
    )
    output(data, fmt=fmt)


@app.command("monitor")
def service_monitor(
    service_id: str = typer.Argument(help="服务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查看服务监控指标"""
    client = PanguClient()
    data = client.get(MONITOR_PATH, workspace_id=workspace, service_id=service_id)
    output(data, fmt=fmt)


@app.command("tasks")
def service_tasks(
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查看全局服务任务视图 (跨空间)"""
    client = PanguClient()
    data = client.get(TASKS_PATH)

    columns = [
        ("service_id", "服务 ID"),
        ("service_name", "名称"),
        ("status", "状态"),
        ("workspace_id", "空间 ID"),
    ]
    output(data, fmt=fmt, columns=columns, title="全局服务任务", status_key="status", id_key="service_id")


@app.command("usage")
def service_usage(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    start_time: Optional[str] = typer.Option(None, "--start", help="开始时间"),
    end_time: Optional[str] = typer.Option(None, "--end", help="结束时间"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查看推理资源使用统计"""
    client = PanguClient()
    params = {}
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time

    data = client.get(USAGE_PATH, workspace_id=workspace, params=params or None)
    output(data, fmt=fmt)
