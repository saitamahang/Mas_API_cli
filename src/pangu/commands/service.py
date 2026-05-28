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
SECRETS_PATH = "/v1/{project_id}/services/secrets"
EDGE_LB_PATH = "/v1/{project_id}/services/edge/loadbalancers"

# 资产查询路径（scaffold 用）
MODEL_ASSET_PATH = "/v1/{project_id}/workspaces/{workspace_id}/asset-manager/model-assets/{asset_id}"
MODEL_ASSET_EXT_PATH = "/v1/{project_id}/workspaces/{workspace_id}/asset-manager/model-assets-ext"

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
    asset_ids: Optional[list[str]] = None,
    asset_tag: Optional[str] = None,
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
    deployed_model: Optional[str] = None,
    task_config: Optional[str] = None,
    input_types: Optional[list[str]] = None,
    output_types: Optional[list[str]] = None,
    infer_version: Optional[str] = None,
    user_env: Optional[list[dict]] = None,
    https_secrets: Optional[str] = None,
    edge_node_port: Optional[int] = None,
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
        "asset_tag": asset_tag,
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
        "deployed_model": deployed_model,
        "task_config": task_config,
        "infer_version": infer_version,
        "https_secrets": https_secrets,
    }
    for k, v in overrides.items():
        if v is not None:
            body[k] = v

    if asset_ids is not None:
        body["asset_ids"] = asset_ids
    if input_types is not None:
        body["input_types"] = input_types
    if output_types is not None:
        body["output_types"] = output_types

    # service_config 处理
    if "service_config" not in body:
        body["service_config"] = {}
    if instances is not None:
        body["service_config"]["instance_count"] = instances
    if pool_id is not None:
        body["service_config"]["cluster_id"] = pool_id
    if user_env is not None:
        body["service_config"]["user_env"] = user_env
    if https_secrets is not None:
        body["service_config"]["https_secrets"] = https_secrets
    if edge_node_port is not None:
        body["service_config"]["edge_node_port"] = edge_node_port

    # model_config 处理
    if "model_config" not in body:
        body["model_config"] = {}
    if task_config is not None:
        body["model_config"]["task_config"] = task_config
    if input_types is not None:
        body["model_config"]["input_types"] = input_types
    if output_types is not None:
        body["model_config"]["output_types"] = output_types

    # infer_type 默认值
    if "infer_type" not in body:
        body["infer_type"] = "edge"

    # request_mode 默认值
    if "request_mode" not in body:
        body["request_mode"] = "sync"

    return body


def _auto_fill_from_asset(client: PanguClient, body: dict, workspace: Optional[str] = None) -> tuple[dict, list[str]]:
    """从 model-assets-ext 自动补全缺失字段（用户显式传入的优先），返回 (body, 补全字段名列表)"""
    asset_id = body.get("asset_id")
    if not asset_id:
        return body, []

    filled: list[str] = []
    svc_cfg = body.get("service_config", {})
    has_custom_spec = bool(svc_cfg.get("custom_spec"))
    has_user_env = bool(svc_cfg.get("user_env"))

    # 检查是否已有所有可从资产获取的字段
    has_all = all([
        body.get("asset_type"),
        body.get("arch"),
        body.get("device_type"),
        body.get("chip_type"),
        body.get("request_mode"),
        body.get("category"),
        body.get("asset_tag"),
    ])
    if has_all and has_custom_spec and has_user_env:
        return body, []

    try:
        ext_data = client.get(
            MODEL_ASSET_EXT_PATH,
            workspace_id=workspace,
            params={"asset_ids": [asset_id], "limit": 1},
        )
    except Exception:
        return body, []

    assets = (ext_data.get("assets") if isinstance(ext_data, dict) else None) or []
    if not assets or not isinstance(assets[0], dict):
        return body, []

    ma = assets[0].get("modelAsset") or {}
    if not isinstance(ma, dict):
        return body, []

    actions = ma.get("actions") or []
    if not actions:
        return body, []

    # 根据 infer_type 匹配对应 action（EDGE-DEPLOY / ONLINE-DEPLOY）
    target_action_type = "EDGE-DEPLOY" if body.get("infer_type") == "edge" else "ONLINE-DEPLOY"
    action_info: dict = {}
    for act in actions:
        if isinstance(act, dict) and act.get("action_type") == target_action_type:
            action_info = act
            break
    if not action_info:
        # 回退到第一个可用 action
        action_info = actions[0] if isinstance(actions[0], dict) else {}

    # resource / image 在 action.resources[0] 下
    resources = action_info.get("resources") or []
    resource_info = resources[0] if resources and isinstance(resources[0], dict) else {}
    image_info = resource_info.get("image") or {}

    # 补全顶层字段（仅当缺失时）
    if not body.get("asset_type") and ma.get("asset_type"):
        body["asset_type"] = ma["asset_type"]
        filled.append("asset_type")
    if not body.get("category") and ma.get("category"):
        body["category"] = ma["category"]
        filled.append("category")
    if not body.get("asset_tag") and action_info.get("asset_tag"):
        body["asset_tag"] = action_info["asset_tag"]
        filled.append("asset_tag")
    if not body.get("device_type"):
        body["device_type"] = resource_info.get("device_type") or image_info.get("device_type") or "NONE"
        filled.append("device_type")
    if not body.get("chip_type"):
        body["chip_type"] = resource_info.get("chip_type") or image_info.get("chip_type") or ""
        filled.append("chip_type")
    if not body.get("arch"):
        body["arch"] = image_info.get("arch") or ""
        filled.append("arch")
    if not body.get("request_mode"):
        body["request_mode"] = image_info.get("request_mode") or "sync"
        filled.append("request_mode")

    # 补全 service_config.custom_spec
    if not has_custom_spec:
        custom_spec: dict = {}
        cpu = resource_info.get("cpu")
        memory = resource_info.get("memory")
        card_count = resource_info.get("card_count")
        dev_type = body.get("device_type", "")
        if cpu is not None:
            custom_spec["cpu"] = cpu
        if memory is not None:
            custom_spec["memory"] = memory
        if card_count is not None:
            if dev_type == "GPU":
                custom_spec["gpu"] = card_count
            elif dev_type == "NPU":
                custom_spec["ascend"] = card_count
        if custom_spec:
            svc_cfg = body.setdefault("service_config", {})
            svc_cfg["custom_spec"] = custom_spec
            svc_cfg["specification"] = "custom"
            filled.append("custom_spec")

    # 补全 service_config.user_env（action_env 字段名：env_name / default_value / data_type）
    if not has_user_env:
        action_env = action_info.get("action_env") or []
        if action_env:
            user_env = []
            for env in action_env:
                if isinstance(env, dict):
                    user_env.append({
                        "key": env.get("env_name", ""),
                        "value": env.get("default_value", ""),
                        "type": env.get("data_type", "string"),
                        "modifiable": env.get("modifiable", False),
                        "displayable": env.get("displayable", True),
                        "env_type": "default",
                    })
            if user_env:
                body.setdefault("service_config", {})["user_env"] = user_env
                filled.append("user_env")

    return body, filled


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
        if assets and isinstance(assets[0], dict) and "asset_type" not in svc:
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
    if assets and isinstance(assets[0], dict) and "asset_type" not in data:
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
    asset_id: Optional[str] = typer.Option(None, "--asset-id", help="模型资产 ID (单资产部署，与 --asset-ids 二选一)"),
    asset_ids: Optional[list[str]] = typer.Option(None, "--asset-ids", help="多资产部署 ID 列表 (与 --asset-id 二选一)"),
    asset_tag: Optional[str] = typer.Option(None, "--asset-tag", help="资产标签，量化模型必填"),
    asset_type: Optional[str] = typer.Option(None, "--asset-type", help="模型类型: NLP/CV/MM/Predict/AI4Science/Profession"),
    arch: Optional[str] = typer.Option(None, "--arch", help="架构: ARM/X86"),
    infer_type: Optional[str] = typer.Option(None, "--infer-type", help="部署类型: online/edge"),
    device_type: Optional[str] = typer.Option(None, "--device-type", help="设备: NPU/GPU/NONE"),
    chip_type: Optional[str] = typer.Option(None, "--chip-type", help="芯片类型"),
    request_mode: Optional[str] = typer.Option(None, "--request-mode", help="请求模式: sync/async"),
    category: Optional[str] = typer.Option(None, "--category", help="来源: pangu/3rd/pangu-poc/pangu-iit/3rd-pangu"),
    pool_id: Optional[str] = typer.Option(None, "--pool-id", help="资源池 ID (在线/边缘资源池 ID，对应 service_config.cluster_id)"),
    instances: Optional[int] = typer.Option(None, "--instances", "-n", help="实例数 (1-128)"),
    elb_id: Optional[str] = typer.Option(None, "--elb-id", help="负载均衡 ID (边缘部署)"),
    scene: Optional[str] = typer.Option(None, "--scene", help="场景: Weather/Precip/Ocean/Ocean_Regional/Ocean_Ecology/Ocean_Swell/Pollution"),
    security_bar_type: Optional[str] = typer.Option(None, "--security-bar", help="安全护栏: ENABLE/DISABLE/NOT_SUPPORT"),
    security_bar_edition: Optional[str] = typer.Option(None, "--security-bar-edition", help="护栏版本: BASE/ADVANCED"),
    deployed_model: Optional[str] = typer.Option(None, "--deployed-model", help="模型部署唯一标识，长度 ≤64"),
    task_config: Optional[str] = typer.Option(None, "--task-config", help="异步模型作业配置参数 (XML 格式字符串)"),
    input_types: Optional[list[str]] = typer.Option(None, "--input-type", help="异步模型输入数据类型 (可多次传入，如 OBS)"),
    output_types: Optional[list[str]] = typer.Option(None, "--output-type", help="异步模型输出数据类型 (可多次传入，如 OBS)"),
    infer_version: Optional[str] = typer.Option(None, "--infer-version", help="推理版本，如 v1"),
    https_secrets: Optional[str] = typer.Option(None, "--https-secrets", help="HTTPS 证书 ID (边缘部署 NODE 模式)"),
    edge_node_port: Optional[int] = typer.Option(None, "--edge-node-port", help="边缘服务端口 (30000-40000，NODE 模式)"),
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
        asset_ids=asset_ids, asset_tag=asset_tag, asset_type=asset_type,
        arch=arch, infer_type=infer_type, device_type=device_type,
        chip_type=chip_type, request_mode=request_mode, category=category,
        pool_id=pool_id, instances=instances, elb_id=elb_id, scene=scene,
        security_bar_type=security_bar_type, security_bar_edition=security_bar_edition,
        deployed_model=deployed_model, task_config=task_config,
        input_types=input_types, output_types=output_types,
        infer_version=infer_version, https_secrets=https_secrets,
        edge_node_port=edge_node_port,
    )

    # 必填参数校验（对照 PDF §3.14.4）
    required = ["service_name", "arch", "infer_type"]
    missing = [k for k in required if not body.get(k)]
    if missing:
        console.print(f"[red]缺少必填参数: {', '.join(missing)}[/red]")
        raise typer.Exit(1)

    # asset_id / asset_ids 二选一
    has_asset = bool(body.get("asset_id")) or bool(body.get("asset_ids"))
    if not has_asset:
        console.print("[red]缺少资产参数: --asset-id 或 --asset-ids 至少提供一个[/red]")
        raise typer.Exit(1)

    # service_config 必填子字段
    svc_cfg = body.get("service_config", {})
    if not svc_cfg.get("instance_count"):
        console.print("[red]service_config.instance_count (实例数) 必填[/red]")
        raise typer.Exit(1)
    if not svc_cfg.get("cluster_id"):
        console.print("[red]service_config.cluster_id (资源池 ID) 必填，请通过 --pool-id 或 YAML 配置提供[/red]")
        raise typer.Exit(1)

    client = PanguClient()

    # 自动补全：从 model-assets-ext 查询缺失字段
    body, filled = _auto_fill_from_asset(client, body, workspace=workspace)
    if filled:
        console.print(f"[dim]已从模型资产信息自动补全: {', '.join(filled)}[/dim]")
    data = client.post(BASE_PATH, workspace_id=workspace, json=body)

    service_id = data.get("service_id", "")
    console.print(f"[green]服务部署已提交，service_id: {service_id}[/green]")

    if wait and service_id:
        console.print("等待部署完成...")
        try:
            data = client.wait_for_status(
                DETAIL_PATH,
                target_statuses=["running"],
                failure_statuses=["failed"],
                interval=15,
                timeout=3600,
                workspace_id=workspace,
                service_id=service_id,
            )
        except (RuntimeError, TimeoutError) as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

    output(
        data,
        fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title="服务部署",
        status_key="status",
    )


@app.command("scaffold")
def scaffold_deploy(
    asset_id: str = typer.Option(..., "--asset-id", help="模型资产 ID (必填)"),
    infer_type: str = typer.Option("edge", "--infer-type", help="部署类型: online/edge"),
    pool_id: Optional[str] = typer.Option(None, "--pool-id", help="资源池 ID (专属池必填)"),
    instances: int = typer.Option(1, "--instances", "-n", help="实例数 (1-128)"),
    service_name: Optional[str] = typer.Option(None, "--name", help="服务名称"),
    edge_access_mode: str = typer.Option("ELB", "--edge-access-mode", help="边缘访问模式: ELB/NODE/MONITOR-GATEWAY"),
    elb_id: Optional[str] = typer.Option(None, "--elb-id", help="负载均衡 ID（边缘 ELB 模式）"),
    https_secrets: Optional[str] = typer.Option(None, "--https-secrets", help="HTTPS 证书 ID（边缘 NODE 模式）"),
    infer_version: Optional[str] = typer.Option(None, "--infer-version", help="推理版本，如 v1"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    output: str = typer.Option("deploy.yaml", "--output", "-o", help="输出文件路径"),
):
    """生成部署服务 YAML 模板

    自动查询模型资产信息，填充 asset_type / category 等字段，
    未获取到的字段用 TODO 占位。生成后修改即可通过 `pangu service deploy --config` 提交。
    """
    client = PanguClient()

    # 1) 获取模型资产详情 (3.12.2)
    asset_detail = client.get(MODEL_ASSET_PATH, workspace_id=workspace, asset_id=asset_id)
    asset_type = asset_detail.get("asset_type", "")
    category = asset_detail.get("category", "pangu")
    asset_name = asset_detail.get("name") or asset_detail.get("asset_name", "")

    # 2) 获取模型扩展信息 (3.12.3)，提取 Resource / Image / Action 信息
    ext_data = client.get(
        MODEL_ASSET_EXT_PATH,
        workspace_id=workspace,
        params={"asset_ids": [asset_id], "limit": 1},
    )
    assets = (ext_data.get("assets") if isinstance(ext_data, dict) else None) or []
    resource_info: dict = {}
    image_info: dict = {}
    action_info: dict = {}
    if assets and isinstance(assets[0], dict):
        ma = assets[0].get("modelAsset") or {}
        if isinstance(ma, dict):
            actions = ma.get("actions") or []
            # 根据 infer_type 匹配对应 action
            target_action_type = "EDGE-DEPLOY" if infer_type == "edge" else "ONLINE-DEPLOY"
            for act in actions:
                if isinstance(act, dict) and act.get("action_type") == target_action_type:
                    action_info = act
                    break
            if not action_info and actions and isinstance(actions[0], dict):
                action_info = actions[0]
            # resource / image 在 action.resources[0] 下
            act_resources = action_info.get("resources") or []
            if act_resources and isinstance(act_resources[0], dict):
                resource_info = act_resources[0]
            image_info = resource_info.get("image") or {}

    # 自动提取字段（PDF 部署章节说明从 model-assets-ext 获取）
    device_type = resource_info.get("device_type") or image_info.get("device_type") or "TODO-NPU/GPU/NONE"
    chip_type = resource_info.get("chip_type") or image_info.get("chip_type") or ""
    arch = image_info.get("arch") or "TODO-ARM/X86"
    request_mode = image_info.get("request_mode") or "sync"
    asset_tag = action_info.get("asset_tag", "")

    # infer_type 与 action_type 匹配
    action_type = action_info.get("action_type", "")
    if infer_type == "online" and "EDGE" in str(action_type).upper():
        console.print("[yellow]警告: 所选模型 action_type 为 EDGE-DEPLOY，建议 --infer-type edge[/yellow]")
    if infer_type == "edge" and "ONLINE" in str(action_type).upper():
        console.print("[yellow]警告: 所选模型 action_type 为 ONLINE-DEPLOY，建议 --infer-type online[/yellow]")

    # custom_spec 字段（Resource 信息）
    cpu = resource_info.get("cpu")
    memory = resource_info.get("memory")
    card_count = resource_info.get("card_count")

    custom_spec: dict = {}
    if cpu is not None:
        custom_spec["cpu"] = cpu
    if memory is not None:
        custom_spec["memory"] = memory
    if card_count is not None:
        if device_type == "GPU":
            custom_spec["gpu"] = card_count
        elif device_type == "NPU":
            custom_spec["ascend"] = card_count

    # 默认值兜底
    if not custom_spec:
        custom_spec = {"cpu": 4, "memory": 8192}
        if device_type == "GPU":
            custom_spec["gpu"] = 1
        else:
            custom_spec["ascend"] = 1

    # user_env 字段（Action 信息中的 action_env，字段名：env_name / default_value / data_type）
    action_env = action_info.get("action_env") or []
    user_env = []
    for env in action_env:
        if isinstance(env, dict):
            user_env.append({
                "key": env.get("env_name", ""),
                "value": env.get("default_value", ""),
                "type": env.get("data_type", "string"),
                "modifiable": env.get("modifiable", False),
                "displayable": env.get("displayable", True),
                "env_type": "default",
            })

    # 3) 自动查询边缘部署依赖资源
    auto_elb_id = elb_id
    auto_secrets = https_secrets
    if infer_type == "edge":
        if edge_access_mode == "ELB" and not auto_elb_id and pool_id:
            try:
                lb_data = client.get(EDGE_LB_PATH, workspace_id=workspace, params={"cluster_id": pool_id})
                lbs = lb_data.get("load_balancers", [])
                if lbs and isinstance(lbs[0], dict):
                    auto_elb_id = lbs[0].get("id", "")
                    console.print(f"[dim]已自动获取负载均衡: {auto_elb_id}[/dim]")
            except Exception:
                pass
        if edge_access_mode == "NODE" and not auto_secrets:
            try:
                sec_data = client.get(SECRETS_PATH, workspace_id=workspace)
                secs = sec_data.get("secrets", [])
                if secs and isinstance(secs[0], dict):
                    auto_secrets = secs[0].get("id", "")
                    console.print(f"[dim]已自动获取证书: {auto_secrets}[/dim]")
            except Exception:
                pass

    # 4) 构造模板
    template: dict = {
        "service_name": service_name or asset_name or "TODO-请填写服务名称（≤64字符）",
        "service_desc": "",
        "asset_id": asset_id,
        "asset_type": asset_type or "TODO-NLP/CV/MM/Predict/AI4Science/Profession",
        "arch": arch,
        "infer_type": infer_type,
        "device_type": device_type,
        "request_mode": request_mode,
        "category": category,
        "service_config": {
            "instance_count": instances,
            "cluster_id": pool_id or "TODO-pangu pool list 获取资源池ID",
            "specification": "custom",
            "custom_spec": custom_spec,
        },
        "model_config": {},
    }

    if asset_tag:
        template["asset_tag"] = asset_tag
    if chip_type:
        template["chip_type"] = chip_type
    if infer_version:
        template["infer_version"] = infer_version

    # user_env 无条件添加（online/edge 都可能需要）
    if user_env:
        template["service_config"]["user_env"] = user_env

    # 边缘部署特有字段
    if infer_type == "edge":
        template["service_config"]["edge_access_mode"] = edge_access_mode
        if edge_access_mode == "ELB":
            template["service_config"]["elb_id"] = auto_elb_id or "TODO-执行 pangu service loadbalancers --cluster-id <pool_id> 获取"
        elif edge_access_mode == "NODE":
            template["service_config"]["edge_node_port"] = "TODO-30000~40000"
            template["service_config"]["https_secrets"] = auto_secrets or "TODO-执行 pangu service secrets 获取证书ID"

    # 科学计算场景
    if asset_type == "AI4Science":
        template["request_mode"] = "async"
        template["model_config"] = {
            "input_types": ["OBS"],
            "output_types": ["OBS"],
        }

    # 安全护栏
    template["security_bar_type"] = "NOT_SUPPORT"

    # 4) 输出
    yaml_text = yaml.dump(template, default_flow_style=False, allow_unicode=True, sort_keys=False)
    out_path = Path(output)
    out_path.write_text(yaml_text, encoding="utf-8")
    console.print(f"[green]部署模板已生成: {out_path.absolute()}[/green]")
    console.print("[dim]提示: 请检查 TODO 项并补齐后执行 pangu service deploy --config {}[/dim]".format(output))


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
        try:
            data = client.wait_for_status(
                DETAIL_PATH,
                target_statuses=["running"],
                failure_statuses=["failed"],
                interval=15,
                timeout=3600,
                workspace_id=workspace,
                service_id=service_id,
            )
        except (RuntimeError, TimeoutError) as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

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
        try:
            data = client.wait_for_status(
                DETAIL_PATH,
                target_statuses=["running"],
                failure_statuses=["failed"],
                interval=10,
                timeout=3600,
                workspace_id=workspace,
                service_id=service_id,
            )
        except (RuntimeError, TimeoutError) as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

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
    start_time: int = typer.Argument(help="开始时间 (毫秒时间戳)"),
    end_time: int = typer.Argument(help="结束时间 (毫秒时间戳)"),
    log_type: str = typer.Argument(help="查询类型: init(首次)/next(向下分页)/pre(向上分页)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    keyword: Optional[str] = typer.Option(None, "--keyword", help="关键词搜索"),
    line_num: Optional[int] = typer.Option(None, "--line-num", help="日志单行序列号 (分页查询时用)"),
    size: int = typer.Option(100, "--size", "-s", help="查询行数 (1-500)，默认 100"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查看服务运行日志"""
    body = {
        "start_time": start_time,
        "end_time": end_time,
        "type": log_type,
        "size": size,
    }
    if keyword:
        body["keyword"] = keyword
    if line_num is not None:
        body["line_num"] = line_num

    client = PanguClient()
    data = client.post(RUNLOG_PATH, workspace_id=workspace, json=body, service_id=service_id)
    output(data, fmt=fmt)


@app.command("node-logs")
def service_node_logs(
    service_id: str = typer.Argument(help="服务 ID"),
    node_id: str = typer.Argument(help="节点 ID"),
    start_time: int = typer.Argument(help="开始时间 (毫秒时间戳)"),
    end_time: int = typer.Argument(help="结束时间 (毫秒时间戳)"),
    log_type: str = typer.Argument(help="查询类型: init(首次)/next(向下分页)/pre(向上分页)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    keyword: Optional[str] = typer.Option(None, "--keyword", help="关键词搜索"),
    line_num: Optional[int] = typer.Option(None, "--line-num", help="日志单行序列号 (分页查询时用)"),
    size: int = typer.Option(100, "--size", "-s", help="查询行数 (1-500)，默认 100"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查看指定节点运行日志"""
    body = {
        "start_time": start_time,
        "end_time": end_time,
        "type": log_type,
        "size": size,
    }
    if keyword:
        body["keyword"] = keyword
    if line_num is not None:
        body["line_num"] = line_num

    client = PanguClient()
    data = client.post(
        NODE_RUNLOG_PATH,
        workspace_id=workspace,
        json=body,
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


@app.command("secrets")
def list_secrets(
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查看边缘 HTTPS 证书列表（用于 NODE 模式部署）"""
    client = PanguClient()
    data = client.get(SECRETS_PATH, workspace_id="0")

    secrets = data.get("secrets", [])
    columns = [
        ("id", "证书 ID"),
        ("name", "名称"),
        ("workspace_id", "工作空间"),
        ("create_time", "创建时间"),
    ]
    output(secrets, fmt=fmt, columns=columns, title="HTTPS 证书", id_key="id")


@app.command("loadbalancers")
def list_loadbalancers(
    cluster_id: str = typer.Option(..., "--cluster-id", help="边缘资源池 ID（pangu pool list --edge 获取）"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查看边缘负载均衡列表（用于 ELB 模式部署）"""
    client = PanguClient()
    params = {"cluster_id": cluster_id}
    data = client.get(EDGE_LB_PATH, workspace_id="0", params=params)

    lbs = data.get("load_balancers", [])
    # 展平 host_ips 为字符串
    for lb in lbs:
        ips = lb.get("host_ips")
        if isinstance(ips, list):
            lb["host_ips"] = ", ".join(str(ip) for ip in ips)

    columns = [
        ("id", "负载均衡 ID"),
        ("name", "名称"),
        ("cluster_name", "资源池"),
        ("scheme", "协议"),
        ("status", "状态"),
        ("host_ips", "IP 地址"),
    ]
    output(lbs, fmt=fmt, columns=columns, title="边缘负载均衡", status_key="status", id_key="id")
