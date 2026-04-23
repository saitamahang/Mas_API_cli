"""数据集管理命令 - pangu dataset list/get/delete/import/publish/..."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer
import yaml
from rich.console import Console

from pangu.client import PanguClient
from pangu.output import output

app = typer.Typer(help="数据集管理")
console = Console()

# v2 列表接口（带分页、过滤、总数）
LIST_PATH        = "/v2/{project_id}/workspaces/{workspace_id}/data-management/datasets"
# v2 详情
DETAIL_PATH_V2   = "/v2/{project_id}/workspaces/{workspace_id}/data-management/datasets/{dataset_name}"
# 批量查询
BATCH_GET_PATH   = "/v1/{project_id}/workspaces/{workspace_id}/data-management/datasets"
# 批量删除（软删）
BATCH_DELETE_PATH = "/v1/{project_id}/workspaces/{workspace_id}/data-management/dataset/batch-delete"
# 彻底删除
PERM_DELETE_PATH = "/v1/{project_id}/workspaces/{workspace_id}/data-management/dataset/permanent-delete"
# 数据血缘
LINEAGE_PATH     = "/v1/{project_id}/workspaces/{workspace_id}/data-management/lineages"
# 数据导入任务
IMPORT_JOBS_PATH = "/v1/{project_id}/workspaces/{workspace_id}/data-extraction/import-jobs"
# 数据发布任务
PUBLISH_JOBS_PATH = "/v1/{project_id}/workspaces/{workspace_id}/data-publish/jobs"
# 数据加工任务
PROCESS_JOBS_PATH = "/v2/{project_id}/workspaces/{workspace_id}/data-cleaning/jobs"
# 算子列表
OPERATORS_PATH   = "/v1/{project_id}/workspaces/{workspace_id}/operator-manager/operator-list"

# content_type -> 允许的 file_format（按官方文档的固定对应关系）
# 导入时若 content_type 命中此表，file_format 必须为指定值；未传则自动补齐。
CONTENT_TYPE_FILE_FORMAT: dict[str, str] = {
    "IMAGE_OBJECT_DETECTION":       "PASCAL",    # 物体检测
    "IMAGE_CLASSIFICATION":         "IMAGE_TXT", # 图像分类
    "IMAGE_ANOMALY_DETECTION":      "IMAGE_TXT", # 异常检测
    "IMAGE_SEMANTIC_SEGMENTATION":  "IMAGE_PNG", # 语义分割
    "IMAGE_INSTANCE_SEGMENTATION":  "IMAGE_XML", # 实例分割
}


LIST_COLUMNS = [
    ("id",           "数据集 ID"),
    ("name",         "名称"),
    ("catalog",      "类别"),
    ("modal",        "模态"),
    ("content_type", "内容类型"),
    ("status",       "状态"),
    ("record_num",   "样本数"),
    ("size",         "大小(Byte)"),
    ("create_time",  "创建时间"),
]

DETAIL_FIELDS = [
    ("dataset_id",   "数据集 ID"),
    ("name",         "名称"),
    ("catalog",      "类别"),
    ("status",       "状态"),
    ("dataset_desc", "描述"),
    ("modal",        "模态"),
    ("content_type", "内容类型"),
    ("file_format",  "文件格式"),
    ("file_source",  "文件来源"),
    ("record_num",   "样本数"),
    ("file_num",     "文件数"),
    ("size",         "大小(Byte)"),
    ("sample_path",  "OBS 路径"),
    ("creator",      "创建人"),
    ("create_time",  "创建时间"),
    ("update_time",  "更新时间"),
    ("is_global",    "全空间可见"),
    ("industry",     "行业"),
    ("language",     "语言"),
]


# ------------------------------ list ------------------------------

@app.command("list")
def list_datasets(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    catalog: Optional[str] = typer.Option(None, "--catalog", "-c", help="类别: ORIGINAL (导入产生) | PROCESS (加工产生) | PUBLISH (发布产生)"),
    name: Optional[str] = typer.Option(None, "--name", help="按名称模糊搜索"),
    status: Optional[List[str]] = typer.Option(None, "--status", help="状态 (可多次传入): ONLINE | OFFLINE"),
    content_type: Optional[List[str]] = typer.Option(None, "--content-type", help=(
        "内容类型 (可多次传入): "
        "SINGLE_QA (单轮问答) | SINGLE_QA_MAN (单轮问答人设) | MULTI_QA (多轮问答) | MULTI_QA_MAN (多轮问答人设) | "
        "QA_SORTING (问答排序) | DPO_QA (偏好优化DPO) | DPO_QA_MAN (偏好优化DPO人设) | "
        "PLAIN_TXT (文档) | WEB_PAGE (网页) | PRE_TRAINED_TEXT (预训练文本) | "
        "VIDEO (视频) | VIDEO_CLIP_ANNOTATION (视频剪辑标注) | VIDEO_UNDERSTANDING (视频理解) | "
        "VIDEO_EVENT_DETECTION (事件检测) | VIDEO_CLASSIFICATION (视频分类) | "
        "TIME_SERIES_PREDICT (时序) | REGRESSION_CLASSIFICATION (回归分类) | "
        "IMAGE (仅图片) | IMAGE_AND_CAPTION (图片+Caption) | IMAGE_AND_QA (图片+QA对) | "
        "IMAGE_AND_CV_ANNOTATION (图片+CV标注) | IMAGE_OBJECT_DETECTION (物体检测) | "
        "IMAGE_CLASSIFICATION (图像分类) | IMAGE_ANOMALY_DETECTION (异常检测) | "
        "IMAGE_SEMANTIC_SEGMENTATION (语义分割) | IMAGE_POSE_ESTIMATION (姿态估计) | "
        "IMAGE_INSTANCE_SEGMENTATION (实例分割) | IMAGE_CHANGE_DETECTION (变化检测) | "
        "OCEAN_WEATHER (气象) | CUSTOMIZATION (自定义)"
    )),
    modal: Optional[str] = typer.Option(None, "--modal", help="模态: TEXT (文本) | IMAGE (图片) | VIDEO (视频) | AUDIO (音频) | WEATHER (气象) | PREDICT (预测) | OTHER (其他)"),
    file_source: Optional[str] = typer.Option(None, "--file-source", help="文件来源: OBS (自己的 OBS 桶路径) | LOCAL (本地终端文件目录) | GALLERY (AIhub 订阅数据集)"),
    file_format: Optional[str] = typer.Option(None, "--file-format", help=(
        "文件格式: JSONL | TXT | CSV | HTML | MOBI | EPUB | DOCX | PDF | "
        "MP4 | AVI | AVI_MP4 | JPGS_JSONL | TAR | IMAGE | "
        "JPG_TXT | JPEG_TXT | PNG_TXT | BMP_TXT | "
        "JPG_XML | JPEG_XML | PNG_XML | BMP_XML | "
        "PASCAL | YOLO | "
        "IMAGE_JSON | IMAGE_PNG | IMAGE_TXT | IMAGE_XML | "
        "VIDEO_JSON | VIDEO_TXT | USER_DEFINED"
    )),
    creator: Optional[str] = typer.Option(None, "--creator", help="创建人，模糊搜索"),
    mine: bool = typer.Option(False, "--mine", help="只看我创建的"),
    show_deleted: bool = typer.Option(False, "--show-deleted", help="包含已删除"),
    sort_by: str = typer.Option("create_time", "--sort-by", help="排序字段: create_time (创建时间) | size (大小) | record_num (样本数)"),
    sort_type: str = typer.Option("desc", "--sort-type", help="排序方向: asc (升序) | desc (降序)"),
    limit: int = typer.Option(20, "--limit", help="每页数量，取值范围 1-1000，默认 20"),
    offset: int = typer.Option(0, "--offset", help="起始偏移，从 0 开始"),
    page: Optional[int] = typer.Option(None, "--page", help="页码，从 1 开始，优先级高于 --offset"),
    all_pages: bool = typer.Option(False, "--all", help="自动翻页拉取全部结果（忽略 --limit/--offset/--page）"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式: table (表格) | json | yaml | id (仅 ID 列表)"),
):
    """查询数据集列表（v2 接口，支持分页、过滤、一键拉全量）"""
    client = PanguClient()

    if page is not None:
        if page < 1:
            console.print("[red]--page 必须 >= 1[/red]")
            raise typer.Exit(1)
        offset = (page - 1) * limit

    def _params(off: int, lim: int) -> dict:
        p: dict = {
            "limit":     lim,
            "offset":    off,
            "sort_by":   sort_by,
            "sort_type": sort_type,
            "mine":      str(mine).lower(),
            "show_deleted": str(show_deleted).lower(),
        }
        if catalog:       p["catalog"] = catalog
        if name:          p["name"] = name
        if status:        p["status"] = status
        if content_type:  p["content_type"] = content_type
        if modal:         p["modal"] = modal
        if file_source:   p["file_source"] = file_source
        if file_format:   p["file_format"] = file_format
        if creator:       p["creator"] = creator
        return p

    if all_pages:
        # 翻页拉取全量
        items: list = []
        cur = 0
        page_size = max(100, limit)  # 翻页时用较大批次减少请求数
        total = None
        while True:
            resp = client.get(LIST_PATH, workspace_id=workspace, params=_params(cur, page_size))
            batch = resp.get("datasets") or []
            items.extend(batch)
            total = resp.get("count", total)
            cur += len(batch)
            if not batch or (total is not None and cur >= total):
                break
            if len(batch) < page_size:
                break
        console.print(f"[cyan]共拉取 {len(items)} 条 (total={total})[/cyan]")
        data = {"datasets": items, "count": len(items)}
    else:
        data = client.get(LIST_PATH, workspace_id=workspace, params=_params(offset, limit))
        total = data.get("count", 0)
        shown = len(data.get("datasets") or [])
        if fmt == "table":
            console.print(
                f"[cyan]显示 {shown} 条 / 共 {total} 条  "
                f"(limit={limit}, offset={offset})  "
                f"→ 使用 --page N 翻页，或 --all 拉取全部[/cyan]"
            )

    output(
        data,
        fmt=fmt,
        columns=LIST_COLUMNS,
        list_key="datasets",
        title="数据集",
        status_key="status",
        id_key="id",
    )


# ------------------------------ get ------------------------------

@app.command("get")
def get_dataset(
    dataset_name: str = typer.Argument(help="数据集名称"),
    catalog: str = typer.Option("ORIGINAL", "--catalog", "-c", help="类别 (必填): ORIGINAL (导入产生) | PROCESS (加工产生) | PUBLISH (发布产生)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式: table (表格) | json | yaml"),
):
    """查询数据集详情（按名称+类别）"""
    client = PanguClient()
    data = client.get(
        DETAIL_PATH_V2,
        workspace_id=workspace,
        params={"catalog": catalog},
        dataset_name=dataset_name,
    )
    output(
        data,
        fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title=f"数据集: {data.get('name', dataset_name)}",
        status_key="status",
    )


@app.command("get-by-ids")
def batch_get(
    dataset_ids: List[str] = typer.Argument(help="数据集 ID 列表，可传多个"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式: table (表格) | json | yaml | id (仅 ID 列表)"),
):
    """按 ID 批量查询数据集详情"""
    client = PanguClient()
    data = client.post(
        BATCH_GET_PATH,
        workspace_id=workspace,
        json={"dataset_ids": list(dataset_ids)},
    )
    output(
        data,
        fmt=fmt,
        columns=LIST_COLUMNS,
        list_key="datasets",
        title=f"批量查询结果 (共 {data.get('total_count', 0)} 条)",
        status_key="status",
        id_key="dataset_id",
    )


# ------------------------------ delete ------------------------------

@app.command("delete")
def delete_datasets(
    dataset_names: List[str] = typer.Argument(help="数据集名称，可传多个"),
    catalog: str = typer.Option("ORIGINAL", "--catalog", "-c", help="类别: ORIGINAL (导入产生) | PROCESS (加工产生) | PUBLISH (发布产生)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式: json | yaml | table"),
):
    """批量删除数据集（软删除，可恢复）"""
    if not yes:
        if not typer.confirm(f"确认删除 {len(dataset_names)} 个数据集 (catalog={catalog})?"):
            raise typer.Abort()

    body = {"datasets": [{"dataset_name": n, "catalog": catalog} for n in dataset_names]}
    client = PanguClient()
    data = client.post(BATCH_DELETE_PATH, workspace_id=workspace, json=body)
    output(data, fmt=fmt)
    console.print(f"[green]已提交删除 {len(dataset_names)} 个数据集[/green]")


@app.command("purge")
def purge_dataset(
    dataset_name: str = typer.Argument(help="数据集名称"),
    catalog: str = typer.Option("ORIGINAL", "--catalog", "-c", help="类别: ORIGINAL (导入产生) | PROCESS (加工产生) | PUBLISH (发布产生)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    delete_obs: bool = typer.Option(False, "--delete-obs", help="同时删除 OBS 源文件（危险操作，文件不可恢复）"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
):
    """彻底清除数据集（不可恢复）"""
    if not yes:
        msg = f"[警告] 彻底清除数据集 {dataset_name} (catalog={catalog})"
        if delete_obs:
            msg += " 并删除 OBS 源文件"
        msg += "? 此操作不可恢复!"
        if not typer.confirm(msg):
            raise typer.Abort()

    body = {
        "dataset_name": dataset_name,
        "catalog":      catalog,
        "delete_obs":   delete_obs,
    }
    client = PanguClient()
    client.post(PERM_DELETE_PATH, workspace_id=workspace, json=body)
    console.print(f"[green]数据集 {dataset_name} 已彻底清除[/green]")


# ------------------------------ import ------------------------------

@app.command("import")
def import_data(
    name: Optional[str] = typer.Option(None, "--name", help="数据集名称（必填，可来自配置文件）"),
    obs_path: Optional[str] = typer.Option(None, "--obs-path", help="OBS 数据路径，格式 bucket-name/path/ (不含 obs:// 前缀；若传入 obs://... 会自动剥离)"),
    content_type: Optional[str] = typer.Option(None, "--content-type", help=(
        "内容类型 (必填): "
        "SINGLE_QA (单轮问答) | SINGLE_QA_MAN (单轮问答人设) | MULTI_QA (多轮问答) | MULTI_QA_MAN (多轮问答人设) | "
        "QA_SORTING (问答排序) | DPO_QA (偏好优化DPO) | DPO_QA_MAN (偏好优化DPO人设) | "
        "PLAIN_TXT (文档) | WEB_PAGE (网页) | PRE_TRAINED_TEXT (预训练文本) | "
        "VIDEO (视频) | VIDEO_CLIP_ANNOTATION (视频剪辑标注) | VIDEO_UNDERSTANDING (视频理解) | "
        "VIDEO_EVENT_DETECTION (事件检测) | VIDEO_CLASSIFICATION (视频分类) | "
        "TIME_SERIES_PREDICT (时序) | REGRESSION_CLASSIFICATION (回归分类) | "
        "IMAGE (仅图片) | IMAGE_AND_CAPTION (图片+Caption) | IMAGE_AND_QA (图片+QA对) | "
        "IMAGE_AND_CV_ANNOTATION (图片+CV标注) | IMAGE_OBJECT_DETECTION (物体检测→PASCAL) | "
        "IMAGE_CLASSIFICATION (图像分类→IMAGE_TXT) | IMAGE_ANOMALY_DETECTION (异常检测→IMAGE_TXT) | "
        "IMAGE_SEMANTIC_SEGMENTATION (语义分割→IMAGE_PNG) | IMAGE_POSE_ESTIMATION (姿态估计) | "
        "IMAGE_INSTANCE_SEGMENTATION (实例分割→IMAGE_XML) | IMAGE_CHANGE_DETECTION (变化检测) | "
        "OCEAN_WEATHER (气象) | CUSTOMIZATION (自定义)。"
        "标“→”的 content_type 与 file_format 固定关联，未传 --file-format 时自动补齐"
    )),
    file_source: str = typer.Option("OBS", "--file-source", help="文件来源: OBS (自己的 OBS 桶路径) | LOCAL (本地终端文件目录) | GALLERY (AIhub 订阅数据集)"),
    file_format: Optional[str] = typer.Option(None, "--file-format", help=(
        "文件格式: JSONL | TXT | CSV | HTML | MOBI | EPUB | DOCX | PDF | "
        "MP4 | AVI | AVI_MP4 | JPGS_JSONL | TAR | IMAGE | "
        "JPG_TXT | JPEG_TXT | PNG_TXT | BMP_TXT | "
        "JPG_XML | JPEG_XML | PNG_XML | BMP_XML | "
        "PASCAL | YOLO | "
        "IMAGE_JSON | IMAGE_PNG | IMAGE_TXT | IMAGE_XML | "
        "VIDEO_JSON | VIDEO_TXT | USER_DEFINED。"
        "图像类 content_type 与 file_format 固定关联，未传则自动补齐；传入不匹配值会报错"
    )),
    desc: Optional[str] = typer.Option(None, "--desc", help="数据集描述"),
    config: Optional[str] = typer.Option(None, "--config", "-f", help="YAML 配置文件路径，命令行参数覆盖文件内值"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    wait: bool = typer.Option(False, "--wait", help="等待导入完成（阻塞轮询，直到 SUCCESS/FAILED/STOPPED）"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式: json | yaml | table"),
):
    """创建数据导入任务"""
    client = PanguClient()

    body: dict = {}
    if config:
        p = Path(config)
        if not p.exists():
            console.print(f"[red]配置文件不存在: {config}[/red]")
            raise typer.Exit(1)
        with p.open(encoding="utf-8") as f:
            body.update(yaml.safe_load(f) or {})

    # 命令行参数覆盖配置文件
    if name:          body["name"] = name
    if obs_path:      body["obs_path"] = obs_path
    if content_type:  body["content_type"] = content_type
    if file_source:   body.setdefault("file_source", file_source)
    if file_format:   body["file_format"] = file_format
    if desc:          body["desc"] = desc

    missing = [k for k in ("name", "obs_path", "content_type") if not body.get(k)]
    if missing:
        console.print(f"[red]缺少必填项: {', '.join(missing)}[/red]")
        raise typer.Exit(1)

    # API 要求 obs_path 为 bucket/path 形式，自动剥离 obs:// 前缀做兼容
    if body["obs_path"].startswith("obs://"):
        stripped = body["obs_path"][len("obs://"):]
        console.print(f"[cyan]已剥离 obs:// 前缀: {body['obs_path']} → {stripped}[/cyan]")
        body["obs_path"] = stripped

    # content_type 与 file_format 的固定关联校验：命中表则必须匹配，未传则自动补齐
    required_fmt = CONTENT_TYPE_FILE_FORMAT.get(body["content_type"])
    if required_fmt:
        actual_fmt = body.get("file_format")
        if actual_fmt and actual_fmt != required_fmt:
            console.print(
                f"[red]content_type={body['content_type']} 要求 file_format={required_fmt}，"
                f"当前传入 {actual_fmt}[/red]"
            )
            raise typer.Exit(1)
        if not actual_fmt:
            body["file_format"] = required_fmt
            console.print(f"[cyan]自动设置 file_format={required_fmt} (由 content_type 决定)[/cyan]")

    data = client.post(IMPORT_JOBS_PATH, workspace_id=workspace, json=body)
    job_id = data.get("id", "")
    output(data, fmt=fmt)
    console.print(f"[green]导入任务已创建: {job_id}[/green]")

    if wait and job_id:
        status_path = IMPORT_JOBS_PATH + f"/{job_id}"
        console.print("[cyan]等待导入完成...[/cyan]")
        final = client.wait_for_status(
            status_path,
            target_statuses=["SUCCESS"],
            failure_statuses=["FAILED", "STOPPED"],
            status_key="status",
            workspace_id=workspace,
        )
        console.print(f"[green]导入完成，状态: {final.get('status')}[/green]")


# ------------------------------ publish ------------------------------

@app.command("publish")
def publish_dataset(
    publish_name: str = typer.Option(..., "--publish-name", help="发布后数据集名称（必填）"),
    source_names: List[str] = typer.Option(..., "--source-name", help="来源数据集名称（必填，可多次传入以合并发布多个数据集）"),
    source_catalog: str = typer.Option("ORIGINAL", "--source-catalog", help="来源类别 (所有 --source-name 共用): ORIGINAL (导入产生) | PROCESS (加工产生) | PUBLISH (发布产生)"),
    file_content_type: str = typer.Option(..., "--file-content-type", help=(
        "内容类型 (必填): "
        "SINGLE_QA (单轮问答) | SINGLE_QA_MAN (单轮问答人设) | MULTI_QA (多轮问答) | MULTI_QA_MAN (多轮问答人设) | "
        "QA_SORTING (问答排序) | DPO_QA (偏好优化DPO) | DPO_QA_MAN (偏好优化DPO人设) | "
        "PLAIN_TXT (文档) | WEB_PAGE (网页) | PRE_TRAINED_TEXT (预训练文本) | "
        "VIDEO (视频) | VIDEO_CLIP_ANNOTATION (视频剪辑标注) | VIDEO_UNDERSTANDING (视频理解) | "
        "VIDEO_EVENT_DETECTION (事件检测) | VIDEO_CLASSIFICATION (视频分类) | "
        "TIME_SERIES_PREDICT (时序) | REGRESSION_CLASSIFICATION (回归分类) | "
        "IMAGE (仅图片) | IMAGE_AND_CAPTION (图片+Caption) | IMAGE_AND_QA (图片+QA对) | "
        "IMAGE_AND_CV_ANNOTATION (图片+CV标注) | IMAGE_OBJECT_DETECTION (物体检测) | "
        "IMAGE_CLASSIFICATION (图像分类) | IMAGE_ANOMALY_DETECTION (异常检测) | "
        "IMAGE_SEMANTIC_SEGMENTATION (语义分割) | IMAGE_POSE_ESTIMATION (姿态估计) | "
        "IMAGE_INSTANCE_SEGMENTATION (实例分割) | IMAGE_CHANGE_DETECTION (变化检测) | "
        "OCEAN_WEATHER (气象) | CUSTOMIZATION (自定义)"
    )),
    publish_format: str = typer.Option("PANGU", "--publish-format", help="发布格式: DEFAULT (标准格式) | PANGU (盘古格式，默认) | USER_DEFINED (自定义格式)"),
    is_global: bool = typer.Option(False, "--global", help="全空间可见"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="描述"),
    config: Optional[str] = typer.Option(None, "--config", "-f", help="YAML 配置文件路径，命令行参数覆盖文件内值"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式: json | yaml | table"),
):
    """发布数据集（创建数据发布任务）"""
    client = PanguClient()

    # 逐个查询数据集详情，补齐 dataset_id（API 非必填，但带上便于服务端定位与审计）
    datasets_payload: list[dict] = []
    for nm in source_names:
        detail = client.get(
            DETAIL_PATH_V2,
            workspace_id=workspace,
            params={"catalog": source_catalog},
            dataset_name=nm,
        )
        ds_id = detail.get("dataset_id") or detail.get("id") or ""
        if not ds_id:
            console.print(f"[yellow]警告: 数据集 {nm} (catalog={source_catalog}) 未查到 dataset_id，仍按名称发布[/yellow]")
        datasets_payload.append({
            "dataset_id":   ds_id,
            "dataset_name": nm,
            "catalog":      source_catalog,
        })

    body: dict = {
        "job_type":          "CIRCULATION",
        "publish_name":      publish_name,
        "file_content_type": file_content_type,
        "is_global":         is_global,
        "datasets":          datasets_payload,
    }
    if description:    body["description"] = description
    body["publish_format"] = publish_format

    if config:
        p = Path(config)
        if not p.exists():
            console.print(f"[red]配置文件不存在: {config}[/red]")
            raise typer.Exit(1)
        with p.open(encoding="utf-8") as f:
            body.update(yaml.safe_load(f) or {})

    data = client.post(PUBLISH_JOBS_PATH, workspace_id=workspace, json=body)
    output(data, fmt=fmt)
    console.print(f"[green]发布任务已创建: {data.get('id', '')}[/green]")


# ------------------------------ process ------------------------------

@app.command("process")
def process_dataset(
    source_name: str = typer.Option(..., "--source-name", help="待加工数据集名称（必填）"),
    source_catalog: str = typer.Option("ORIGINAL", "--source-catalog", help="来源类别: ORIGINAL (导入产生) | PROCESS (加工产生) | PUBLISH (发布产生)"),
    operator_catalog: str = typer.Option("SYS", "--operator-catalog", help="算子来源: SYS (预置算子) | USER (用户自定义算子)"),
    config: str = typer.Option(..., "--config", "-f", help="YAML 配置文件路径（必填，包含 task_operators 等）"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式: json | yaml | table"),
):
    """创建数据加工任务（task_operators 配置项较多，建议走 YAML）"""
    client = PanguClient()

    p = Path(config)
    if not p.exists():
        console.print(f"[red]配置文件不存在: {config}[/red]")
        raise typer.Exit(1)
    with p.open(encoding="utf-8") as f:
        body: dict = yaml.safe_load(f) or {}

    body.setdefault("source_dataset_name", source_name)
    body.setdefault("source_dataset_catalog", source_catalog)
    body.setdefault("operator_catalog", operator_catalog)

    if not body.get("task_operators"):
        console.print("[red]配置文件缺少 task_operators[/red]")
        raise typer.Exit(1)

    data = client.post(PROCESS_JOBS_PATH, workspace_id=workspace, json=body)
    output(data, fmt=fmt)
    console.print(f"[green]加工任务已创建: {data.get('job_id', '')}[/green]")


@app.command("operators")
def list_operators(
    catalog: Optional[str] = typer.Option(None, "--catalog", help="算子来源: SYS (预置算子) | USER (用户自定义算子)"),
    modal: Optional[str] = typer.Option(None, "--modal", help="模态: TEXT (文本) | IMAGE (图片) | VIDEO (视频) | AUDIO (音频)"),
    category: Optional[List[str]] = typer.Option(None, "--category", help="算子类型 (可多次传入): DL (数据打标) | DT (数据转换) | DS (数据抽样) | DE (数据提取) | DF (数据过滤) | OTHER (其他)"),
    mine: bool = typer.Option(False, "--mine", help="只看我创建的"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式: json | yaml | table"),
):
    """查询加工算子列表（响应为一级分类→二级分类→算子的嵌套结构）"""
    client = PanguClient()
    params: dict = {}
    if catalog:  params["catalog"] = catalog
    if modal:    params["modal"] = modal
    if category: params["category"] = category
    if mine:     params["mine"] = "true"

    data = client.get(OPERATORS_PATH, workspace_id=workspace, params=params or None)
    output(data, fmt=fmt)


# ------------------------------ lineage ------------------------------

@app.command("lineage")
def dataset_lineage(
    from_path: str = typer.Argument(help="来源数据集的 OBS 路径，格式 obs://bucket/path/"),
    limit: int = typer.Option(100, "--limit", help="返回血缘数量上限，取值范围 1-1000，默认 100"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式: json | yaml | table"),
):
    """查询 OBS 路径关联的数据血缘"""
    client = PanguClient()
    params = {"from_path": from_path, "limit": limit}
    data = client.get(LINEAGE_PATH, workspace_id=workspace, params=params)
    output(data, fmt=fmt)
