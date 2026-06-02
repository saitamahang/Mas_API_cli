"""资产管理命令 - pangu model list/get/list-ext/export/export-tasks

对应 API 参考文档《资产管理》3.12.1 ~ 3.12.5 全部接口。
"""

from __future__ import annotations

from typing import List, Optional

import typer
from rich.console import Console

from pangu.client import PanguClient
from pangu.output import output

app = typer.Typer(help="模型资产管理")
console = Console()


TRAIN_ACTIONS = {
    "PRETRAIN", "SFT", "LORA", "DPO", "RLHF",
    "TRANSFORM", "QUANTIZATION", "EVALUATION",
}
DEPLOY_ACTIONS = {"ONLINE-DEPLOY", "EDGE-DEPLOY"}


def _extract_resource_info(data: dict) -> tuple[list[dict], list[dict]]:
    """从资产详情 data['actions'] 提取训练和部署资源规格信息。

    同一 action_type 下若 resources 包含多种 arch，会按 arch 拆分多行展示，
    确保用户能看到全部可用架构（如 ARM + X86）。

    Returns:
        (train_rows, deploy_rows)
    """
    from collections import defaultdict

    actions = data.get("actions") or []
    train_rows: list[dict] = []
    deploy_rows: list[dict] = []

    for act in actions:
        if not isinstance(act, dict):
            continue
        action_type = act.get("action_type", "")
        if action_type in TRAIN_ACTIONS:
            target = train_rows
        elif action_type in DEPLOY_ACTIONS:
            target = deploy_rows
        else:
            continue

        resources = act.get("resources") or []
        # 按 arch 分组收集 chip_type / cpu / memory
        arch_groups: dict[str, dict] = defaultdict(lambda: {
            "chip_types": [], "cpus": [], "mems": [],
        })

        for res in resources:
            if not isinstance(res, dict):
                continue
            img = res.get("image") or {}
            arch = img.get("arch") if isinstance(img, dict) else ""
            # 训练资源池默认 ARM；部署按实际提取
            if not arch:
                arch = "ARM" if action_type in TRAIN_ACTIONS else "未知"

            g = arch_groups[arch]
            ct = res.get("chip_type")
            if ct and ct not in g["chip_types"]:
                g["chip_types"].append(ct)

            try:
                cpu = int(res.get("cpu", 0))
                if cpu:
                    g["cpus"].append(cpu)
            except (TypeError, ValueError):
                pass

            try:
                mem = int(res.get("memory", 0))
                if mem:
                    g["mems"].append(mem)
            except (TypeError, ValueError):
                pass

        for arch, g in arch_groups.items():
            specs: list[str] = []
            if g["cpus"]:
                specs.append(f"CPU: {g['cpus'][0]}")
            if g["mems"]:
                specs.append(f"Memory: {g['mems'][0]}Mi")

            target.append({
                "action_type": action_type,
                "chip_types": g["chip_types"],
                "arch": arch,
                "spec": ", ".join(specs) if specs else "-",
            })

    return train_rows, deploy_rows

# ---- 路径（严格对应 PDF URI）----
BASE_PATH         = "/v1/{project_id}/workspaces/{workspace_id}/asset-manager/model-assets"
DETAIL_PATH       = BASE_PATH + "/{asset_id}"                          # 3.12.2
EXT_PATH          = "/v1/{project_id}/workspaces/{workspace_id}/asset-manager/model-assets-ext"  # 3.12.3
EXPORT_SITE_PATH  = BASE_PATH + "/{asset_id}/export-site"              # 3.12.4
MIGRATE_TASKS_PATH = BASE_PATH + "/migrate/tasks"                      # 3.12.5

# ---- 枚举帮助文本 ----
HELP_ACTION_TYPE = (
    "操作类型：PRETRAIN(预训练)|SFT(SFT微调)|RLHF(强化学习)|TRANSFORM(转换)|"
    "QUANTIZATION(量化)|EVALUATION(评测)|ONLINE-DEPLOY(在线部署)|EDGE-DEPLOY(边缘部署)"
)
HELP_ASSET_TYPE = (
    "模型类型：NLP(NLP大模型)|CV(CV大模型)|MM(多模态)|AI4Science(科学计算)|"
    "Predict(预测)|Profession(专业)；3.12.3 支持多值(逗号分隔)"
)
HELP_SUB_ASSET_TYPE = (
    "模型子类型（按需设置）：\n"
    "  CV：SS|IC|ED|OVD|PE|AD|ObjectDetection|OpticalCharacterRecogniton|OpenVocabularySegmentation|RD\n"
    "  科学计算：Weather_1h|Weather_3h|Weather_6h|Weather_24h|Precip_6h|"
    "Ocean_Regional_24h|Ocean_Ecology_24h|Ocean_Swell_24h|Ocean_24h\n"
    "  多模态：Img2Txt\n"
    "  预测：AnomalyDetection|Classification|TimeSeries|Regression|StructurePredict|"
    "IntegratingModelDataDriven\n"
    "  Profession：NLP\n"
    "  组件：package|script|PostProcessingCode"
)
HELP_ASSET_SOURCE_V1 = "资产来源(3.12.1)：Preset(预置)|Publish(本空间)|Import(导入)|AI Hub(订阅)"
HELP_ASSET_SOURCE_V3 = "资产来源(3.12.3)：Preset(预置)|Publish(发布)|Import(导入)|AIGallery(订阅)"
HELP_ASSET_FEATURE = "资产特性：NLP=7B|38B|135B；科学计算=1h|3h|6h|24h 或 hashcode"
HELP_CATEGORY = "分类：pangu|3rd|pangu-poc|pangu-iit|3rd-pangu"
HELP_CATEGORY_V1 = "分类(3.12.1)：pangu|3rd"
HELP_WORKSPACE_SOURCE = "空间来源：current(本空间)|others(其他空间)"
HELP_VISIBILITY = "可见性：all(全空间)|current(本空间)"
HELP_ASSET_ACTION = (
    "按操作类型过滤，多值逗号分隔。训练：PRETRAIN|SFT|LORA|DPO|RLHF|TRANSFORM|QUANTIZATION；"
    "部署：ONLINE-DEPLOY|EDGE-DEPLOY"
)
HELP_SORT = "排序：asc(升序)|desc(降序)"
HELP_DIRECTION = "迁移任务类型：import|preset_import|export|publish|subscribe"
HELP_MIGRATE_STATUS = (
    "迁移任务状态：Success(成功)|Failed(失败)|Importing(导入中)|Exporting(导出中)|"
    "Publishing(发布中)|Subscribing(订阅中)|Copying(拷贝中)|OnShelf(已上架)|OffShelf(已下架)|"
    "Cancelled(已取消)|Expired(到期)|Cancelled-SubscribeSupported|Expired-SubscribeSupported"
)
HELP_MIGRATE_TYPE = "模型类型过滤：model(模型)|assembly(组件)"

# ---- 表格列 ----
LIST_COLUMNS = [
    ("asset_id",       "资产 ID"),
    ("asset_name",     "名称"),
    ("asset_version",  "版本"),
    ("asset_type",     "类型"),
    ("asset_source",   "来源"),
]

LIST_EXT_COLUMNS = [
    ("asset_id",       "资产 ID"),
    ("asset_name",     "名称"),
    ("asset_version",  "版本"),
    ("asset_type",     "类型"),
    ("asset_source",   "来源"),
    ("can_train",      "可训练"),
    ("can_deploy",     "可部署"),
]

SIMPLE_COLUMNS = [
    ("asset_id",      "资产 ID"),
    ("asset_name",    "名称"),
    ("asset_version", "版本"),
    ("asset_tag",     "标签"),
    ("asset_type",    "类型"),
    ("asset_source",  "来源"),
    ("can_train",     "可训练"),
    ("can_deploy",    "可部署"),
    ("model_id",      "模型 ID"),
]

DETAIL_FIELDS = [
    ("asset_id",             "资产 ID"),
    ("root_asset_id",        "来源预置资产 ID"),
    ("asset_name",           "名称"),
    ("asset_name_en",        "英文名称"),
    ("asset_desc",           "描述"),
    ("asset_version",        "内核版本"),
    ("external_version",     "对外版本"),
    ("asset_type",           "类型"),
    ("sub_asset_type",       "子类型"),
    ("asset_code",           "族谱编码"),
    ("asset_source",         "来源"),
    ("asset_feature",        "特性"),
    ("category",             "分类"),
    ("storage_type",         "存储类型"),
    ("asset_location",       "OBS 位置"),
    ("asset_config_location","配置路径"),
    ("is_available",         "对外可见"),
    ("visibility",           "可见性"),
    ("security_policy",      "安全策略"),
    ("encode_type",          "编码方式"),
    ("creator",              "创建者"),
    ("user_id",              "创建者 ID"),
    ("project_id",           "项目 ID"),
    ("workspace_id",         "空间 ID"),
    ("dataset_id",           "关联数据集"),
    ("execute_id",           "工作流 ID"),
    ("create_time",          "创建时间"),
    ("update_time",          "更新时间"),
]

MIGRATE_TASK_COLUMNS = [
    ("task_id",      "任务 ID"),
    ("asset_id",     "资产 ID"),
    ("asset_type",   "类型"),
    ("direction",    "方向"),
    ("status",       "状态"),
    ("create_time",  "创建时间"),
]


# ---------------------------------------------------------------------------
# 3.12.1 查询指定空间内的模型资产列表
# ---------------------------------------------------------------------------
@app.command("list")
def list_models(
    workspace: Optional[str]    = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    action_type: Optional[str]  = typer.Option(None, "--action-type", help=HELP_ACTION_TYPE),
    asset_ids: Optional[List[str]] = typer.Option(None, "--asset-id", help="资产 ID 过滤（可多次传入）"),
    asset_type: Optional[str]   = typer.Option(None, "--type", "-t", help=HELP_ASSET_TYPE),
    sub_asset_type: Optional[str] = typer.Option(None, "--sub-type", help=HELP_SUB_ASSET_TYPE),
    sub_asset_type_snip: Optional[str] = typer.Option(None, "--sub-type-snip", help="子类型模糊搜索（仅科学计算生效，如 Weather / Ocean）"),
    asset_source: Optional[str] = typer.Option(None, "--source", help=HELP_ASSET_SOURCE_V1),
    asset_feature: Optional[str] = typer.Option(None, "--feature", help=HELP_ASSET_FEATURE),
    user_id: Optional[str]      = typer.Option(None, "--user-id", help="发布用户 ID"),
    asset_code: Optional[str]   = typer.Option(None, "--asset-code", help="模型编码，如 Pangu-NLP-N1-xxx"),
    workspace_source: Optional[str] = typer.Option(None, "--workspace-source", help=HELP_WORKSPACE_SOURCE),
    category: Optional[str]     = typer.Option(None, "--category", help=HELP_CATEGORY_V1),
    is_op_user: Optional[bool]  = typer.Option(None, "--op-user/--no-op-user", help="是否承载租户 (1/0)；传 user_id 时必须 --no-op-user"),
    simple: bool = typer.Option(False, "--simple", help="简洁模式，只显示核心字段"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式 table|json|yaml|id"),
):
    """查询指定空间内的模型资产列表 (3.12.1)

    响应为 Array<Array<ModelAsset>>，已自动拍平为平坦列表展示。
    """
    client = PanguClient()
    params: dict = {}
    if action_type:          params["action_type"] = action_type
    if asset_ids:            params["asset_ids"] = asset_ids
    if asset_type:           params["asset_type"] = asset_type
    if sub_asset_type:       params["sub_asset_type"] = sub_asset_type
    if sub_asset_type_snip:  params["sub_asset_type_snip"] = sub_asset_type_snip
    if asset_source:         params["asset_source"] = asset_source
    if asset_feature:        params["asset_feature"] = asset_feature
    if user_id:              params["user_id"] = user_id
    if asset_code:           params["asset_code"] = asset_code
    if workspace_source:     params["workspace_source"] = workspace_source
    if category:             params["category"] = category
    if is_op_user is not None: params["is_op_user"] = str(is_op_user).lower()

    data = client.get(BASE_PATH, workspace_id=workspace, params=params or None)

    # 3.12.1 响应形如 Array<Array<ModelAsset>> —— 拍平
    flat: list = []
    if isinstance(data, list):
        for elem in data:
            if isinstance(elem, list):
                flat.extend(elem)
            elif isinstance(elem, dict):
                flat.append(elem)
    elif isinstance(data, dict):
        flat = [data]
    columns = SIMPLE_COLUMNS if simple else LIST_COLUMNS
    output(flat, fmt=fmt, columns=columns, title="模型资产", id_key="asset_id")


# ---------------------------------------------------------------------------
# 3.12.2 查询指定空间内的模型资产详情
# ---------------------------------------------------------------------------
@app.command("get")
def get_model(
    asset_id: str = typer.Argument(help="资产 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    action_asset_tag: Optional[str] = typer.Option(None, "--action-asset-tag", help="按模型标签过滤，如 NLP-N1-PERTRAIN"),
    all_actions: bool = typer.Option(False, "--all-actions", help="展示模型支持的全部 actions（默认按需展示）"),
    show_resources: bool = typer.Option(False, "--show-resources", help="展示该资产支持的资源规格及对应资源池查询参数"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式 table|json|yaml"),
):
    """查询模型资产详情 (3.12.2)

    返回资产元数据（asset_name / model_type / actions 等）。
    ⚠️ 如需获取训练参数模板（含 workflow_info / parameters），请用
       `pangu training model-detail`（3.13.11），本命令不能用于构造训练请求体。
    """
    client = PanguClient()
    params: dict = {}
    if action_asset_tag: params["action_asset_tag"] = action_asset_tag
    if all_actions:      params["is_all_action"] = "true"

    data = client.get(DETAIL_PATH, workspace_id=workspace, asset_id=asset_id, params=params or None)

    # --show-resources 模式：解析 actions 里的资源规格并展示
    if show_resources:
        if not isinstance(data, dict):
            console.print("[red]返回数据异常，无法解析资源规格[/red]")
            raise typer.Exit(1)

        train_rows, deploy_rows = _extract_resource_info(data)

        # 先给所有 row 生成 pool_cmd（json / table 共用）
        for row in train_rows:
            chips = " ".join(f"--chip-type {ct}" for ct in row["chip_types"])
            arch = f"--arch {row['arch']}" if row["arch"] else ""
            row["pool_cmd"] = f"pangu pool list {chips} {arch} --job-type Train".strip()

        for row in deploy_rows:
            chips = " ".join(f"--chip-type {ct}" for ct in row["chip_types"])
            arch = f"--arch {row['arch']}" if row["arch"] else ""
            if row["action_type"] == "EDGE-DEPLOY":
                row["pool_cmd"] = f"pangu pool list {chips} {arch} --edge".strip()
            else:
                row["pool_cmd"] = f"pangu pool list {chips} {arch} --job-type Infer".strip()

        if fmt in ("json", "yaml"):
            output({
                "asset_id": asset_id,
                "train_options": train_rows,
                "deploy_options": deploy_rows,
            }, fmt=fmt)
            return

        if not train_rows and not deploy_rows:
            console.print("[yellow]该资产未找到训练或部署相关的资源规格信息[/yellow]")
            return

        from rich.table import Table

        def _print_table(title: str, rows: list[dict]) -> None:
            console.print(f"\n[bold]{title}[/bold]\n")
            table = Table(show_header=True, header_style="bold")
            table.add_column("方式")
            table.add_column("芯片类型")
            table.add_column("架构")
            table.add_column("资源规格")
            for row in rows:
                table.add_row(
                    row["action_type"],
                    ", ".join(row["chip_types"]) or "-",
                    row["arch"] or "-",
                    row["spec"],
                )
            console.print(table)

        if train_rows:
            _print_table(f"资产 {asset_id} 支持的训练资源", train_rows)
            console.print("\n[bold]对应资源池查询命令:[/bold]")
            for row in train_rows:
                console.print(f"  [cyan]训练({row['action_type']}):[/cyan] {row['pool_cmd']}")

        if deploy_rows:
            _print_table(f"资产 {asset_id} 支持的部署资源", deploy_rows)
            console.print("\n[bold]对应资源池查询命令:[/bold]")
            for row in deploy_rows:
                label = "边缘部署" if row["action_type"] == "EDGE-DEPLOY" else "在线部署"
                console.print(f"  [cyan]{label}:[/cyan] {row['pool_cmd']}")
        console.print()
        return

    output(
        data,
        fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title=f"模型: {data.get('asset_name', '')}",
    )


# ---------------------------------------------------------------------------
# 3.12.3 获取模型列表（含部署/训练能力判定）
# ---------------------------------------------------------------------------
@app.command("list-ext")
def list_ext(
    workspace: Optional[str]    = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    limit: int                  = typer.Option(10, "--limit", help="分页大小 (0-1000000)，默认 10"),
    offset: int                 = typer.Option(0, "--offset", help="起始偏移 (0-1000000)，默认 0"),
    asset_ids: Optional[List[str]] = typer.Option(None, "--asset-id", help="资产 ID 过滤（可多次传入）"),
    asset_name: Optional[str]   = typer.Option(None, "--name", help="按资产名称精确过滤"),
    asset_name_snip: Optional[str] = typer.Option(None, "--name-snip", help="按资产名称模糊匹配"),
    asset_source: Optional[str] = typer.Option(None, "--source", help=HELP_ASSET_SOURCE_V3),
    asset_type: Optional[str]   = typer.Option(None, "--type", "-t", help=HELP_ASSET_TYPE),
    sub_asset_type: Optional[str] = typer.Option(None, "--sub-type", help=HELP_SUB_ASSET_TYPE),
    visibility: Optional[str]   = typer.Option(None, "--visibility", help=HELP_VISIBILITY),
    workspace_source: Optional[str] = typer.Option(None, "--workspace-source", help=HELP_WORKSPACE_SOURCE),
    category: Optional[str]     = typer.Option(None, "--category", help=HELP_CATEGORY),
    asset_feature: Optional[str] = typer.Option(None, "--feature", help=HELP_ASSET_FEATURE),
    sort: Optional[str]         = typer.Option(None, "--sort", help=HELP_SORT),
    asset_action: Optional[str] = typer.Option(None, "--asset-action", help=HELP_ASSET_ACTION),
    simple: bool = typer.Option(False, "--simple", help="简洁模式，只显示核心字段"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式 table|json|yaml|id"),
):
    """获取模型列表（含 can_deploy/can_train/is_used 等能力标识, 3.12.3）

    响应为 {total, assets:[ModelAssetExt{modelAsset:{...}, can_*, model_id, is_used}]}，
    已将嵌套的 modelAsset 字段展平到顶层，方便表格展示。
    """
    client = PanguClient()
    params: dict = {"limit": limit, "offset": offset}
    if asset_ids:        params["asset_ids"] = asset_ids
    if asset_name:       params["asset_name"] = asset_name
    if asset_name_snip:  params["asset_name_snip"] = asset_name_snip
    if asset_source:     params["asset_source"] = asset_source
    if asset_type:       params["asset_type"] = asset_type
    if sub_asset_type:   params["sub_asset_type"] = sub_asset_type
    if visibility:       params["visibility"] = visibility
    if workspace_source: params["workspace_source"] = workspace_source
    if category:         params["category"] = category
    if asset_feature:    params["asset_feature"] = asset_feature
    if sort:             params["sort"] = sort
    if asset_action:     params["asset_action"] = asset_action

    data = client.get(EXT_PATH, workspace_id=workspace, params=params)

    # 将 modelAsset 展平到顶层，方便表格显示
    assets = (data.get("assets") if isinstance(data, dict) else None) or []
    flat_assets = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        ma = item.get("modelAsset") or {}
        merged = dict(ma) if isinstance(ma, dict) else {}
        for k in (
            "can_deploy", "can_train", "can_delete", "can_eval",
            "can_quantize", "can_export", "model_id", "is_used",
            "publish_info", "subscribe_info",
        ):
            if k in item:
                merged[k] = item[k]
        flat_assets.append(merged)

    # json/yaml 给 agent 原始数据；table/id 给人类看展平后的
    if fmt in ("json", "yaml"):
        if simple:
            # 简洁模式：只保留 SIMPLE_COLUMNS 对应的字段
            keep_keys = {k for k, _ in SIMPLE_COLUMNS}
            simple_assets = [
                {k: v for k, v in item.items() if k in keep_keys}
                for item in flat_assets
            ]
            output({"total": data.get("total"), "assets": simple_assets}, fmt=fmt)
        else:
            output(data, fmt=fmt)
        return

    columns = SIMPLE_COLUMNS if simple else LIST_EXT_COLUMNS
    title = f"模型资产 (完整)  total={data.get('total')}" if isinstance(data, dict) else "模型资产 (完整)"
    output(flat_assets, fmt=fmt, columns=columns, title=title, id_key="asset_id")


# ---------------------------------------------------------------------------
# 3.12.4 导出 ModelArts Site 平台格式资产
# ---------------------------------------------------------------------------
@app.command("export")
def export_model(
    asset_id: str = typer.Argument(help="资产 ID（取自 model-assets 列表响应）"),
    export_obs_path: str = typer.Option(
        ..., "--export-obs-path",
        help="(必填) 导出目的 OBS 路径，格式 obs://{桶名}/{文件夹名}/",
    ),
    esn: str = typer.Option(
        ..., "--esn",
        help="(必填) ESN 码，长度 1-64，字母/数字/下划线/连字符；由导入方提供",
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """导出模型为 ModelArts Site 格式 (3.12.4, GET /.../{asset_id}/export-site)

    响应含 download_url，仅供 ModelArts Site 平台使用。
    """
    client = PanguClient()
    params = {"export_obs_path": export_obs_path, "esn": esn}
    data = client.get(EXPORT_SITE_PATH, workspace_id=workspace, asset_id=asset_id, params=params)
    output(data, fmt=fmt)
    if isinstance(data, dict) and data.get("download_url"):
        console.print(f"[green]导出成功[/green] download_url=[cyan]{data['download_url']}[/cyan]")


# ---------------------------------------------------------------------------
# 3.12.5 查询模型导出/迁移任务列表
# ---------------------------------------------------------------------------
@app.command("export-tasks")
def export_tasks(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    limit: int  = typer.Option(10, "--limit", help="分页大小 (0-1000000)，默认 10"),
    offset: int = typer.Option(0, "--offset", help="起始偏移，默认 0"),
    status: Optional[str]    = typer.Option(None, "--status", help=HELP_MIGRATE_STATUS),
    direction: Optional[str] = typer.Option(None, "--direction", help=HELP_DIRECTION),
    sort_by: Optional[str]   = typer.Option(None, "--sort-by", help=HELP_SORT),
    task_type: Optional[str] = typer.Option(None, "--type", help=HELP_MIGRATE_TYPE),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式 table|json|yaml"),
):
    """查询模型迁移/导出任务列表 (3.12.5, GET /asset-manager/model-assets/migrate/tasks)

    覆盖 import/preset_import/export/publish/subscribe 等迁移方向。
    """
    client = PanguClient()
    params: dict = {"limit": limit, "offset": offset}
    if status:    params["status"] = status
    if direction: params["direction"] = direction
    if sort_by:   params["sort_by"] = sort_by
    if task_type: params["type"] = task_type

    data = client.get(MIGRATE_TASKS_PATH, workspace_id=workspace, params=params)
    title = f"迁移任务  count={data.get('count')}" if isinstance(data, dict) else "迁移任务"
    output(
        data, fmt=fmt,
        columns=MIGRATE_TASK_COLUMNS,
        list_key="migrate_tasks",
        title=title,
        status_key="status",
        id_key="task_id",
    )
