"""训练任务管理命令 - pangu training

对应 API 参考文档《训练任务管理》3.13.1 ~ 3.13.13 全部接口。
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import List, Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table

from pangu.client import PanguClient
from pangu.output import output

app = typer.Typer(help="训练任务管理")
console = Console()

BASE            = "/v1/{project_id}/workspaces/{workspace_id}/model-train"
# 3.13.3 查询详情 / 3.13.5 创建（POST 无 {task_id}）
TASK_PATH       = BASE + "/train-task/{task_id}"
CREATE_PATH     = BASE + "/train-task"
# 3.13.2 停止/重试
ACTION_PATH     = BASE + "/train-task/{task_id}/action"
# 3.13.9 批量删除
TASKS_PATH      = BASE + "/train-tasks"
# 3.13.1 获取 metrics
METRIC_PATH     = BASE + "/executions/{execution_id}/metric"
# 3.13.4 获取日志
LOG_PATH        = BASE + "/execution/{execution_id}/training-jobs/{job_id}/tasks/{log_task_id}/preview"
# 3.13.6 获取节点信息
NODE_PATH       = BASE + "/execution/{execution_id}/training-jobs/{job_id}"
# 3.13.7 发布模型
PUBLISH_PATH    = BASE + "/model/publish"
# 3.13.8 获取已发布的模型列表
MODELS_PATH     = BASE + "/models"
# 3.13.10 查询断点列表
CHECKPOINT_PATH = BASE + "/execution/{execution_id}/checkpoints"
# 3.13.11 获取模型详情（用于构造 task_parameter）
MODEL_DETAIL_PATH = BASE + "/model-detail"
# 3.13.12 资源用量
USAGE_PATH      = BASE + "/resource-usage"
# 3.13.13 资源池运行中任务
RUNNING_PATH    = BASE + "/tasks"


# ==================== 枚举帮助文本（按 PDF 取值范围） ====================
# 复用给多个命令的长字符串，避免散落各处改一处漏一处。
HELP_MODEL_TYPE  = "模型类型: NLP (NLP大模型) | MM (多模态模型) | CV (CV模型) | Predict (预测模型) | AI4Science (科学计算模型)"
HELP_TRAIN_TYPE  = "训练类型: SFT (全量微调) | PRETRAIN (预训练) | LORA (lora微调) | DPO (DPO强化学习) | RFT (RFT强化学习)"
HELP_MODEL_SRC          = "模型来源 [3.13.5 create 接口]: pangu (盘古预置模型) | third (三方模型) | pangu-third (盘古预置三方模型)"
# 注意：3.13.11 获取模型详情 / scaffold 用的是 SYSTEM|USER，与 create 接口的 model_source 不是同一套取值，不能混用
HELP_MODEL_SRC_DETAIL   = "模型来源 [3.13.11 model-detail / scaffold 接口]: SYSTEM (盘古发布的预置模型) | USER (训练任务产生的模型)"
HELP_ACTION_TYPE = "操作类型: PRETRAIN (预训练) | SFT (全量微调) | LORA (lora微调) | QUANTIZATION (量化) | DPO (DPO强化学习)"
HELP_VISIBILITY  = "可见性: current (仅当前空间) | all (全部空间)"
HELP_CATEGORY    = ("模型资产来源: pangu (盘古大模型) | 3rd (用户导入的三方大模型) | "
                   "pangu-poc (POC 版盘古大模型) | pangu-iit (工业智能中枢模型) | 3rd-pangu (盘古服务所提供的三方大模型)")
HELP_MODEL_STAT  = "模型状态: published (已发布) | unpublished (未发布)"
HELP_PLOG_LEVEL  = "plog 日志级别: -1 (不开启) | 0 (info) | 1 (debug) | 2 (warning) | 3 (error)"

# 终态集合（用于 --wait）
FINAL_TASK_STATUS = ["completed", "failed", "stopped"]


DETAIL_FIELDS = [
    ("task_id",         "任务 ID"),
    ("task_name",       "名称"),
    ("task_status",     "状态"),
    ("train_process",   "进度"),
    ("model_type",      "模型类型"),
    ("train_type",      "训练类型"),
    ("model_id",        "模型 ID"),
    ("parent_model",    "父模型"),
    ("dataset_id",      "训练数据集 ID"),
    ("dataset_name",    "训练数据集"),
    ("eval_dataset_name","验证数据集"),
    ("pool_node_count", "节点数"),
    ("flavor",          "算力规格"),
    ("t_flops",         "总算力"),
    ("execution_id",    "执行 ID"),
    ("train_cost_time", "耗时(ms)"),
    ("train_task_desc", "描述"),
    ("create_time",     "创建时间"),
    ("update_time",     "更新时间"),
]

MODEL_COLUMNS = [
    ("model_id",    "模型 ID"),
    ("model_name",  "模型名称"),
    ("model_type",  "模型类型"),
    ("action_type", "操作类型"),
    ("status",      "状态"),
    ("create_time", "创建时间"),
]


def _load_yaml(config_file: str) -> dict:
    p = Path(config_file)
    if not p.exists():
        console.print(f"[red]配置文件不存在: {config_file}[/red]")
        raise typer.Exit(1)
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _inject_train_flavor(parameters: list, flavor_id: str, pool_id: str) -> list:
    """[HC] 把资源池注入到 task_parameter.parameters 的 train_flavor 超参中。

    HC 环境下资源池不走顶层 resource_config，而是作为 train_flavor 超参：
        {"name": "train_flavor", "value": {"flavor_id": "<规格>", "pool_id": "<pool-xxx>"}}

    - 若 model-detail 已返回 train_flavor 占位项（按 name 或 format=train_flavor 匹配），则就地更新 value
    - 否则 append 一项
    """
    new_value = {"flavor_id": flavor_id, "pool_id": pool_id}
    found = False
    out = []
    for p in parameters or []:
        if isinstance(p, dict) and (p.get("name") == "train_flavor" or p.get("format") == "train_flavor"):
            np = dict(p)
            np["value"] = new_value
            out.append(np)
            found = True
        else:
            out.append(p)
    if not found:
        out.append({"name": "train_flavor", "value": new_value})
    return out


def _paramdef_to_runtime(param: dict) -> dict:
    """把 model-detail 返回的"参数定义"转成 create 请求体所需的"运行时参数"。

    workflow_info.parameters 里每一项是参数 *定义*（含 default/constraint/enum 等元信息），
    而 3.13.5 创建训练任务请求体的 task_parameter.parameters 里每一项需要带上一个 `value` 字段
    （PDF §3.13.5 请求示例每条参数都同时包含 default 与 value）。

    规则：
      - 已有 value → 保留不动（避免覆盖用户/上游已设置的值）
      - format == "train_flavor" → value = {"flavor_id": "", "pool_id": ""}
        （HC 资源池对象；值从 pangu pool list 获取，后续由 _inject_train_flavor 覆盖）
      - 有 default  → value = default（与 PDF 示例一致）
      - 无 default  → value = None（YAML 中显示为 null，提醒用户必须手动填写）
    """
    if not isinstance(param, dict):
        return param
    out = dict(param)
    if "value" in out:
        return out
    if out.get("format") == "train_flavor" or out.get("name") == "train_flavor":
        out["value"] = {
            "flavor_id": "TODO-参考 model-detail 中 train_flavor 的取值范围，例 1*ascend-snt9b",
            "pool_id":   "TODO-pangu pool list 获取 pool-xxxxx",
        }
    else:
        out["value"] = out.get("default")
    return out


def _build_task_parameter(workflow_info: dict, env_type: str = "HCS", dataset_obs_url: Optional[str] = None) -> dict:
    """从 model-detail 的 workflow_info 组装 create 请求体里的 task_parameter。

    - HCS / HC：task_parameter 均包含 parameters / storages / data_requirements
    - workflow_info 中的 extend / assets / data / steps / policy 等其他字段不携带
    - HC 环境下 data_requirements 每个对象需补 value / realValue（含 object_type + obs_url）
    """
    wi = workflow_info or {}
    params = [_paramdef_to_runtime(p) for p in (wi.get("parameters") or [])]

    data_reqs = wi.get("data_requirements") or []
    if env_type == "HC":
        enriched = []
        for dr in data_reqs:
            if isinstance(dr, dict):
                dr_copy = dict(dr)
                obs_url = dataset_obs_url or "TODO-通过 pangu dataset get <dataset_name> 查询 sample_path 并去掉 obs:/ 前缀"
                val = {"object_type": ["DIRECTORY"], "obs_url": obs_url}
                dr_copy["value"] = val
                dr_copy["realValue"] = dict(val)  # 独立拷贝，避免 YAML 锚点/别名
                enriched.append(dr_copy)
            else:
                enriched.append(dr)
        data_reqs = enriched

    return {
        "parameters":        params,
        "storages":          wi.get("storages") or [],
        "data_requirements": data_reqs,
    }


def _extract_first_job_id(detail: dict) -> str:
    """从训练任务详情的 steps_execution 中取第一个 job_id（字符串或已解析的 dict 都兼容）"""
    steps = detail.get("steps_execution", "")
    if isinstance(steps, str) and steps:
        try:
            steps = _json.loads(steps)
        except Exception:
            return ""
    if isinstance(steps, dict):
        for step_info in steps.values():
            if isinstance(step_info, dict) and step_info.get("job_id"):
                return step_info["job_id"]
    return ""


# ------------------------------ get / stop / retry / delete ------------------------------

@app.command("get")
def get_task(
    task_id: str = typer.Argument(help="训练任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式: table (表格) | json | yaml"),
):
    """查询训练任务详情 (3.13.3)"""
    client = PanguClient()
    data = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
    output(
        data, fmt=fmt,
        detail_fields=DETAIL_FIELDS,
        title=f"训练任务: {data.get('task_name', '')}",
        status_key="task_status",
    )


@app.command("stop")
def stop_task(
    task_id: str = typer.Argument(help="训练任务 ID (任务状态需为 running / pending)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
):
    """停止训练任务 (3.13.2, action_name=stop)"""
    if not yes and not typer.confirm(f"确认停止任务 {task_id}?"):
        raise typer.Abort()
    client = PanguClient()
    client.post(ACTION_PATH, workspace_id=workspace, json={"action_name": "stop"}, task_id=task_id)
    console.print(f"[green]任务 {task_id} 已提交停止[/green]")


@app.command("retry")
def retry_task(
    task_id: str = typer.Argument(help="训练任务 ID (任务状态需为 failed)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    wait: bool = typer.Option(False, "--wait", help="等待任务跑到终态 (completed/failed/stopped)"),
):
    """重试失败的训练任务 (3.13.2, action_name=retry)"""
    client = PanguClient()
    client.post(ACTION_PATH, workspace_id=workspace, json={"action_name": "retry"}, task_id=task_id)
    console.print(f"[green]任务 {task_id} 已重试[/green]")

    if wait:
        console.print("[cyan]等待任务完成...[/cyan]")
        final = client.wait_for_status(
            TASK_PATH,
            target_statuses=FINAL_TASK_STATUS,
            failure_statuses=["failed", "stopped"],
            status_key="task_status",
            workspace_id=workspace,
            task_id=task_id,
        )
        console.print(f"[green]最终状态: {final.get('task_status')}[/green]")


@app.command("delete")
def delete_task(
    task_ids: List[str] = typer.Argument(help="训练任务 ID，可传多个"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
):
    """批量删除训练任务 (3.13.9)"""
    if not yes and not typer.confirm(f"确认删除 {len(task_ids)} 个任务?"):
        raise typer.Abort()
    client = PanguClient()
    data = client.delete(
        TASKS_PATH, workspace_id=workspace,
        params={"train_task_id_list": ",".join(task_ids)},
    )
    console.print(f"[green]成功删除: {data.get('success_num', '?')} 个，失败: {data.get('failed_num', '?')} 个[/green]")


# ------------------------------ scaffold ------------------------------

@app.command("scaffold")
def scaffold(
    model_id: str = typer.Option(..., "--model-id", help="模型 ID，预置模型时 = asset_id"),
    model_type: str = typer.Option(..., "--model-type", help="(必填) " + HELP_MODEL_TYPE),
    train_type: str = typer.Option(..., "--train-type", help="(必填) " + HELP_TRAIN_TYPE),
    model_source: str = typer.Option(..., "--model-source", help="(必填) " + HELP_MODEL_SRC_DETAIL),
    create_model_source: Optional[str] = typer.Option(None, "--create-model-source", help="写入 YAML 的 create 接口 model_source [可选] " + HELP_MODEL_SRC + "；不传则按 SYSTEM→pangu / USER→third 自动映射"),
    strategy: Optional[str] = typer.Option(None, "--strategy", help="策略 (可选)"),
    asset_id: Optional[str] = typer.Option(None, "--asset-id", help="已知的 asset_id，直接填入模板；不传则留 TODO 占位"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    out_file: Optional[str] = typer.Option(None, "--out", help="写入到指定文件；不传则打印到 stdout (便于 `> train.yaml`)"),
    dataset_name: Optional[str] = typer.Option(None, "--dataset-name", help="数据集名称，HC 环境下用于自动查询 OBS 路径填充 data_requirements"),
    dataset_catalog: str = typer.Option("ORIGINAL", "--dataset-catalog", help="数据集类别: ORIGINAL (导入产生) | PROCESS (加工产生) | PUBLISH (发布产生)"),
):
    """生成训练任务 YAML 模板（含 task_parameter，可直接改后喂给 create）

    内部调用 model-detail 拿到 workflow_info.parameters 作为 task_parameter，
    其余必填字段用 TODO 占位。生成后只需补齐 asset_id / task_name / 资源配置即可提交。
    """
    client = PanguClient()
    detail_body: dict = {
        "model_id":     model_id,
        "model_type":   model_type,
        "train_type":   train_type,
        "model_source": model_source,
    }
    if strategy:
        detail_body["strategy"] = strategy

    env_type = (client.config.env_type or "HCS").upper()
    if env_type == "HC":
        detail = client.get(MODEL_DETAIL_PATH, workspace_id=workspace, params=detail_body)
    else:
        detail = client.post(MODEL_DETAIL_PATH, workspace_id=workspace, json=detail_body)

    # HC 环境下：如有 dataset_name，自动查 OBS 路径用于填充 data_requirements
    dataset_obs_url = None
    if env_type == "HC" and dataset_name:
        try:
            ds_detail = client.get(
                "/v1/{project_id}/workspaces/{workspace_id}/data-management/dataset/{dataset_name}",
                workspace_id=workspace,
                params={"catalog": dataset_catalog},
                dataset_name=dataset_name,
            )
            sample_path = ds_detail.get("sample_path", "")
            for prefix in ("obs://", "obs:/"):
                if sample_path.startswith(prefix):
                    sample_path = sample_path[len(prefix):]
                    break
            dataset_obs_url = sample_path or None
            if dataset_obs_url:
                console.print(f"[cyan]已查询数据集 {dataset_name} OBS 路径: {dataset_obs_url}[/cyan]")
        except Exception as e:
            console.print(f"[yellow]查询数据集 {dataset_name} 详情失败: {e}，data_requirements 中 obs_url 将使用 TODO 占位[/yellow]")

    workflow_info = detail.get("workflow_info") or {}
    task_parameter = _build_task_parameter(workflow_info, env_type=env_type, dataset_obs_url=dataset_obs_url)
    parameters = task_parameter["parameters"]

    # YAML 中 model_source 是给 3.13.5 create 用的（pangu|third|pangu-third），
    # 与上面 model-detail 调用使用的 SYSTEM|USER 不是同一套取值，必须分开
    if create_model_source:
        body_model_source = create_model_source
    elif model_source.upper() == "SYSTEM":
        body_model_source = "pangu"
    elif model_source.upper() == "USER":
        body_model_source = "third"  # 用户自训产出的模型走 third；如属于盘古预置三方模型请显式 --create-model-source pangu-third
    else:
        body_model_source = model_source  # 兜底：用户传了非标值也透传


    # 根据 model-detail 返回，先取若干字段做默认占位（避免 user 漏传）
    suggested_asset_id = asset_id or detail.get("asset_id") or "TODO-pangu model list 获取 asset_id"

    # 公共骨架：3.13.5 PDF 中所有顶层可选字段都列上 TODO，让用户清楚有哪些选项
    common_top: dict = {
        "task_name":              "TODO-请填写任务名称（中文/字母/数字/中划线/下划线，不以数字开头，≤64）",
        "asset_id":               suggested_asset_id,
        "model_id":               model_id,
        "model_type":             model_type,
        "train_type":             train_type,
        "model_source":           body_model_source,
        "model_name":             "",  # 可选，不填走默认
        "train_task_desc":        "",
        # 数据集（可选，按需填）
        "dataset_id":             "",
        "dataset_name":           "",
        "dataset_version_id":     "",
        "eval_dataset_id":        "",
        "eval_dataset_name":      "",
        "eval_dataset_version_id":"",
        "dataset_split_ratio":    None,  # 1~50；不需要可删除
        # 断点续训（可选）
        "checkpoint_id":          "",
        "checkpoint_config": {
            # PDF §3.13.5 CheckpointConfig，需要时取消注释/补值；不需要保留 {} 即可
            # "save_checkpoints_max":  0,   # >0 开启断点续训并保存指定数量；0 关闭，-1 无限
            # "skipped_steps":         0,   # 续训时跳过的步数
            # "restore_training":      0,   # 0 重训 / 1 续训
            # "checkpoint_publish_info": {  # 断点发布
            #     "checkpoint_id": "", "visibility": "current",
            #     "asset_name": "", "description": "",
            # },
        },
        # SFS Turbo 加速（可选，仅 HCS）
        "sfs_config": {
            "model_sfs_enable":   False,
            "dataset_sfs_enable": False,
            "dataset_preload":    False,
        },
        # 量化场景（可选）
        "output_artifact_name":   "",
        "quantization_type":      "",
        # 强化学习 RLHF 场景（当前接口注明"不支持"，保留占位说明）
        "reward_model_id":        "",
        # 三方模型环境变量（可选，model_source=third/pangu-third 时使用）
        "task_env":               {},
        # 日志
        "plog_level":             -1,
        "is_input_finished":      1,
        # 训练运行参数（含 storages / data_requirements / parameters[每条带 value]）
        "task_parameter":         task_parameter,
    }

    if env_type == "HC":
        # HC：资源池作为 train_flavor 超参注入 task_parameter.parameters
        # 这里 _inject_train_flavor 会就地更新或追加 train_flavor 项；保留兄弟字段
        common_top["task_parameter"]["parameters"] = _inject_train_flavor(
            parameters,
            flavor_id="TODO-flavor_id 字符串，例 1*ascend-snt9b（参考 model-detail 中 train_flavor 的取值范围）",
            pool_id="TODO-pangu pool list 获取 pool-xxxxx",
        )
        # HC 不使用顶层 pool_node_count / flavor / t_flops / resource_config
        skeleton = common_top
    else:
        # HCS：资源池走顶层 resource_config + pool_node_count / flavor / t_flops
        common_top.update({
            "pool_node_count": 1,
            "flavor":          313,
            "t_flops":         "TODO-卡数 × flavor，或在 create 时给齐 --nodes/--flavor-id/--flavor 自动推导",
            # PDF §3.13.5 ResourceConfig 全字段；非必填项保留占位让用户按需取舍
            "resource_config": {
                "pool_type":       "private",                    # public | private（默认 private）
                "chip_type":       "TODO-如 Snt9B3 / Snt9B4",
                "pool_id":         "TODO-pangu pool list 获取 (专属池必填，公共池留空字符串)",
                "pool_name":       "",
                "flavor_id":       "TODO-专属池取 1|2|4|8",
                "flavor_name":     "",
                "node_count":      1,    # flavor_id=8 且 >1 即多机多卡
                "fp16":            None, # 313 / 280 等
                "t_flops":         None, # ResourceConfig 内的 t_flops（Double）
                "training_unit":   None, # 训练单元
            },
        })
        skeleton = common_top

    text = yaml.safe_dump(skeleton, allow_unicode=True, sort_keys=False)
    if out_file:
        Path(out_file).write_text(text, encoding="utf-8")
        console.print(
            f"[green]已写入 {out_file}（含 {len(parameters)} 个训练参数 / "
            f"{len(task_parameter['storages'])} 个存储项 / "
            f"{len(task_parameter['data_requirements'])} 个数据要求项）[/green]"
        )
        console.print(
            "[cyan]下一步：编辑其中 TODO 项（必填字段标注在 PDF §3.13.5），"
            f"然后 `pangu training create -f {out_file} --dry-run` 预览[/cyan]"
        )
    else:
        typer.echo(text)


# ------------------------------ create ------------------------------

@app.command("create")
def create_task(
    config: Optional[str] = typer.Option(None, "--config", "-f", help="YAML 配置文件路径 (推荐，task_parameter 较复杂必须通过文件传入)"),
    # 基本信息
    name: Optional[str] = typer.Option(None, "--name", help="任务名称 (task_name，必填；可含中文/字母/数字/中划线/下划线，不以数字开头，≤64)"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="任务描述 (train_task_desc)"),
    # 模型 & 训练类型
    asset_id: Optional[str] = typer.Option(None, "--asset-id", help="模型资产 ID，取自资产列表 (必填)"),
    model_id: Optional[str] = typer.Option(None, "--model-id", help="训练模型 ID (NLP/MM 必填；预置模型时=asset_id，训练后模型取自已发布模型列表)"),
    model_type: Optional[str] = typer.Option(None, "--model-type", help="(必填) " + HELP_MODEL_TYPE),
    train_type: Optional[str] = typer.Option(None, "--train-type", help="(必填，默认 SFT) " + HELP_TRAIN_TYPE),
    model_source: Optional[str] = typer.Option(None, "--model-source", help="(必填) " + HELP_MODEL_SRC),
    model_name: Optional[str] = typer.Option(None, "--model-name", help="模型名称 (可选)"),
    output_artifact_name: Optional[str] = typer.Option(None, "--output-artifact-name", help="任务输出产物名称 (量化场景使用)"),
    quantization_type: Optional[str] = typer.Option(None, "--quantization-type", help="量化算法类型，例如 QUANTIZATION-W8A8C"),
    # 数据集
    dataset_id: Optional[str] = typer.Option(None, "--dataset-id", help="训练数据集 ID (取自查询数据集详情 v1)"),
    dataset_name: Optional[str] = typer.Option(None, "--dataset-name", help="训练数据集名称 (取自查询数据集详情 v1 的 name)"),
    dataset_version_id: Optional[str] = typer.Option(None, "--dataset-version-id", help="训练数据集版本 ID"),
    eval_dataset_id: Optional[str] = typer.Option(None, "--eval-dataset-id", help="验证数据集 ID"),
    eval_dataset_name: Optional[str] = typer.Option(None, "--eval-dataset-name", help="验证数据集名称"),
    eval_dataset_version_id: Optional[str] = typer.Option(None, "--eval-dataset-version-id", help="验证数据集版本 ID"),
    dataset_split_ratio: Optional[int] = typer.Option(None, "--dataset-split-ratio", help="训练/验证数据集分割比率，取值 1~50 (整体范围 0-100)"),
    # 断点续训
    checkpoint_id: Optional[str] = typer.Option(None, "--checkpoint-id", help="断点续训场景的恢复点 UUID (取自查询断点接口)"),
    # 资源（HCS 走顶层 resource_config；HC 作为 train_flavor 超参注入 task_parameter）
    pool_id: Optional[str] = typer.Option(None, "--pool-id", help="资源池 ID — HCS: 写入 resource_config.pool_id (公共池为空，专属池必填)；HC: 写入 task_parameter 中的 train_flavor.value.pool_id (必填)"),
    pool_type: Optional[str] = typer.Option(None, "--pool-type", help="[HCS] 资源池类型: public (公共池) | private (专属池，默认)"),
    chip_type: Optional[str] = typer.Option(None, "--chip-type", help="[HCS] 资源规格类型，取自 model-detail 接口的 chip_type，如 Snt9B3 / Snt9B4"),
    flavor_id: Optional[str] = typer.Option(None, "--flavor-id", help="[HCS] 规格卡数，专属池取 1 | 2 | 4 | 8"),
    nodes: Optional[int] = typer.Option(None, "--nodes", help="[HCS] 资源池节点数 pool_node_count，默认 1；flavor_id=8 时 >1 即多机多卡 (0-10000)"),
    flavor: Optional[int] = typer.Option(None, "--flavor", help="[HCS] 资源池算力规格，常见 313 | 280 (0-10000)"),
    t_flops: Optional[int] = typer.Option(None, "--t-flops", help="[HCS 必填] 总算力 = 卡数 × flavor；不传且同时传了 --nodes / --flavor-id / --flavor 时自动按 nodes × flavor_id × flavor 推导"),
    train_flavor: Optional[str] = typer.Option(None, "--train-flavor", help="[HC] 训练规格 flavor_id 字符串，写入 task_parameter 中的 train_flavor.value.flavor_id；取自 model-detail 返回的规格表，例 1*ascend-snt9b"),
    # 其他
    plog_level: Optional[int] = typer.Option(None, "--plog-level", help=HELP_PLOG_LEVEL + " (默认 -1)"),
    is_input_finished: Optional[int] = typer.Option(None, "--is-input-finished", help="训练参数是否已全部输入 (默认 1)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    wait: bool = typer.Option(False, "--wait", help="等待任务跑到终态 (completed/failed/stopped)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只组装并打印请求体 (YAML)，不实际提交 API；skill 预检/调试用"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式: table | json | yaml"),
):
    """创建训练任务 (3.13.5)

    task_parameter 字段结构复杂（见 model-detail 接口的 workflow_info.parameters），
    建议将完整请求体写入 YAML 后通过 --config 传入，CLI 参数用于覆盖/补齐常用字段。

    资源池设置随 env_type 不同：
      - HCS：顶层 resource_config + pool_node_count / flavor / t_flops
      - HC ：作为 train_flavor 超参写入 task_parameter.parameters，
             value = {"flavor_id": "<规格>", "pool_id": "<pool-xxx>"}
    """
    client = PanguClient()
    env_type = (client.config.env_type or "HCS").upper()

    body: dict = _load_yaml(config) if config else {}

    # 命令行覆盖 YAML
    if name:                     body["task_name"]             = name
    if description:              body["train_task_desc"]       = description
    if asset_id:                 body["asset_id"]              = asset_id
    if model_id:                 body["model_id"]              = model_id
    if model_type:               body["model_type"]            = model_type
    if train_type:               body["train_type"]            = train_type
    if model_source:             body["model_source"]          = model_source
    if model_name:               body["model_name"]            = model_name
    if output_artifact_name:     body["output_artifact_name"]  = output_artifact_name
    if quantization_type:        body["quantization_type"]     = quantization_type
    if dataset_id:               body["dataset_id"]            = dataset_id
    if dataset_name:             body["dataset_name"]          = dataset_name
    if dataset_version_id:       body["dataset_version_id"]    = dataset_version_id
    if eval_dataset_id:          body["eval_dataset_id"]       = eval_dataset_id
    if eval_dataset_name:        body["eval_dataset_name"]     = eval_dataset_name
    if eval_dataset_version_id:  body["eval_dataset_version_id"] = eval_dataset_version_id
    if dataset_split_ratio is not None: body["dataset_split_ratio"] = dataset_split_ratio
    if checkpoint_id:            body["checkpoint_id"]         = checkpoint_id
    if nodes is not None:        body["pool_node_count"]       = nodes
    if flavor is not None:       body["flavor"]                = flavor
    if t_flops is not None:      body["t_flops"]               = t_flops
    if plog_level is not None:   body["plog_level"]            = plog_level
    if is_input_finished is not None: body["is_input_finished"] = is_input_finished

    if env_type == "HC":
        # HC：把 --pool-id / --train-flavor 注入 task_parameter.parameters 的 train_flavor 项
        if pool_id or train_flavor:
            tp = body.setdefault("task_parameter", {})
            params = tp.get("parameters") or []
            # 取已有 train_flavor.value 作为基底，命令行只覆盖给出的字段
            existing = {}
            for p in params:
                if isinstance(p, dict) and (p.get("name") == "train_flavor" or p.get("format") == "train_flavor"):
                    existing = dict(p.get("value") or {})
                    break
            if train_flavor: existing["flavor_id"]  = train_flavor
            if pool_id:      existing["pool_id"] = pool_id
            tp["parameters"] = _inject_train_flavor(
                params,
                flavor_id=existing.get("flavor_id", ""),
                pool_id=existing.get("pool_id", ""),
            )
        # HC 不应出现 HCS 专有的顶层资源字段，给出明确提示而不是默默丢弃
        for hcs_only in ("resource_config", "pool_node_count", "flavor", "t_flops"):
            if hcs_only in body:
                console.print(f"[yellow]env_type=HC：忽略 HCS 专有字段 {hcs_only}（HC 走 task_parameter.train_flavor）[/yellow]")
                body.pop(hcs_only, None)
    else:
        # HCS：resource_config 子对象单独合并
        if any(v is not None for v in (pool_id, pool_type, chip_type, flavor_id)):
            rc = body.setdefault("resource_config", {})
            if pool_id:   rc["pool_id"]   = pool_id
            if pool_type: rc["pool_type"] = pool_type
            if chip_type: rc["chip_type"] = chip_type
            if flavor_id: rc["flavor_id"] = flavor_id

        # t_flops 自动推导：用户没传 t_flops 但给齐了 nodes / flavor_id / flavor 时，按 PDF 公式（卡数 × flavor）推导
        if body.get("t_flops") in (None, 0):
            rc_for_calc = body.get("resource_config") or {}
            n  = body.get("pool_node_count")
            fi = rc_for_calc.get("flavor_id")
            fv = body.get("flavor")
            try:
                n, fi, fv = int(n), int(fi), int(fv)
                body["t_flops"] = n * fi * fv
                console.print(f"[cyan]自动推导 t_flops = nodes({n}) × flavor_id({fi}) × flavor({fv}) = {body['t_flops']}[/cyan]")
            except (TypeError, ValueError):
                pass  # 缺任一项就不推，留给下面必填校验报错

    # 必填校验：HCS 多 t_flops；HC 不需要 t_flops（资源走 task_parameter）
    required = ["asset_id", "task_name", "model_type", "train_type", "model_source", "task_parameter"]
    if env_type != "HC":
        required.append("t_flops")
    for req in required:
        if body.get(req) in (None, "", {}, []):
            console.print(f"[red]缺少必填字段: {req}[/red]")
            if req == "task_parameter":
                console.print("[yellow]task_parameter 结构较复杂，请先调 `pangu training scaffold` 或 `model-detail` 获取模板[/yellow]")
            if req == "t_flops":
                console.print("[yellow]未传 --t-flops 且 --nodes / --flavor-id / --flavor 未同时给齐，无法自动推导[/yellow]")
            raise typer.Exit(1)

    # HC 额外校验：task_parameter 内必须有 train_flavor 且 pool_id 非空
    if env_type == "HC":
        params = (body.get("task_parameter") or {}).get("parameters") or []
        tf = next((p for p in params if isinstance(p, dict) and (p.get("name") == "train_flavor" or p.get("format") == "train_flavor")), None)
        if not tf or not (tf.get("value") or {}).get("pool_id"):
            console.print("[red]env_type=HC：task_parameter.parameters 中缺少 train_flavor 或其 pool_id 为空[/red]")
            console.print("[yellow]通过 --pool-id [+ --train-flavor] 注入，或在 YAML 中直接补齐[/yellow]")
            raise typer.Exit(1)

    # 提交前清理：scaffold 模板里的 None 占位值（如未填 dataset_split_ratio / fp16 / training_unit 等）
    # 直接发到 API 会变成 null，部分接口对可选字段的 null 不友好。这里递归剔除 None。
    # 只清 None；空字符串/空 dict/空 list 用户可能有意保留，不动。
    def _strip_nulls(obj):
        if isinstance(obj, dict):
            return {k: _strip_nulls(v) for k, v in obj.items() if v is not None}
        if isinstance(obj, list):
            return [_strip_nulls(v) for v in obj]
        return obj
    body = _strip_nulls(body)

    if dry_run:
        console.print("[cyan]--dry-run：以下为将提交的请求体（未发送到 API）[/cyan]")
        typer.echo(yaml.safe_dump(body, allow_unicode=True, sort_keys=False))
        return

    data = client.post(CREATE_PATH, workspace_id=workspace, json=body)
    task_id = data.get("task_id", "")

    output(data, fmt=fmt, detail_fields=DETAIL_FIELDS, title="训练任务已创建", status_key="task_status")

    if wait and task_id:
        console.print(f"[cyan]等待任务 {task_id} 完成...[/cyan]")
        final = client.wait_for_status(
            TASK_PATH,
            target_statuses=FINAL_TASK_STATUS,
            failure_statuses=["failed", "stopped"],
            status_key="task_status",
            workspace_id=workspace,
            task_id=task_id,
        )
        console.print(f"[green]最终状态: {final.get('task_status')}[/green]")


# ------------------------------ logs / nodes / metrics / checkpoints ------------------------------

@app.command("logs")
def task_logs(
    task_id: str = typer.Argument(help="训练任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    execution_id: Optional[str] = typer.Option(None, "--execution-id", help="执行 ID，不传则从任务详情自动获取"),
    job_id: Optional[str] = typer.Option(None, "--job-id", help="步骤 job_id，不传则取 steps_execution 中第一个"),
    node: str = typer.Option("worker-0", "--node", help="日志节点名，如 worker-0 / worker-1 (取自 nodes 接口)"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查看训练日志 (3.13.4)"""
    client = PanguClient()
    if not execution_id or not job_id:
        console.print("[yellow]自动拉取 execution_id / job_id...[/yellow]")
        detail = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
        execution_id = execution_id or detail.get("execution_id", "")
        job_id       = job_id       or _extract_first_job_id(detail)

    if not execution_id or not job_id:
        console.print("[red]无法自动获取 execution_id 或 job_id，请通过 --execution-id / --job-id 手动指定[/red]")
        raise typer.Exit(1)

    data = client.get(
        LOG_PATH, workspace_id=workspace,
        execution_id=execution_id, job_id=job_id, log_task_id=node,
    )
    output(data, fmt=fmt)


@app.command("nodes")
def task_nodes(
    task_id: str = typer.Argument(help="训练任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    execution_id: Optional[str] = typer.Option(None, "--execution-id", help="执行 ID，不传则自动获取"),
    job_id: Optional[str] = typer.Option(None, "--job-id", help="步骤 job_id，不传则取 steps_execution 第一个"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """获取训练任务某一步执行的节点信息 (3.13.6)，用于查日志时拿 worker 节点名"""
    client = PanguClient()
    if not execution_id or not job_id:
        detail = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
        execution_id = execution_id or detail.get("execution_id", "")
        job_id       = job_id       or _extract_first_job_id(detail)

    if not execution_id or not job_id:
        console.print("[red]请通过 --execution-id / --job-id 手动指定[/red]")
        raise typer.Exit(1)

    data = client.get(NODE_PATH, workspace_id=workspace, execution_id=execution_id, job_id=job_id)
    output(data, fmt=fmt)


def _render_loss_curve(loss_points: list, width: int = 100, height: int = 14) -> None:
    """在终端用 Unicode Braille 点阵绘制 loss-epoch 曲线。

    - 采用 Braille (U+2800..U+28FF) 点阵：每个字符格内含 2×4 共 8 个子像素，
      相比 `●` 的稀疏散点，曲线连续且不会出现字符间缝隙（这才是真正的"连成线"）。
    - Y 轴固定从 0 开始，上限 = max(loss) × 1.10（留 10% 余量）。
    - X 轴固定宽度 width 字符（等效 width*2 子像素），按迭代轮次等分。
    - 相邻数据点之间用 Bresenham 算法在高分辨率画布上连线。

    注：Git Bash / Windows Terminal / iTerm2 / macOS Terminal 均支持 Braille 字符；
        若终端字体缺失 Braille 字形，会显示为占位方块（罕见）。
    """
    pts = [(p.get("epoch", i), float(p.get("loss", 0.0)))
           for i, p in enumerate(loss_points) if isinstance(p, dict)]
    if not pts:
        console.print("[yellow]无 loss 数据[/yellow]")
        return

    values = [v for _, v in pts]
    epochs = [e for e, _ in pts]
    n = len(values)

    raw_max = max(values) if values else 1.0
    vmax = raw_max * 1.10 if raw_max > 0 else 1.0  # vmin = 0 固定

    # 高分辨率画布：每个字符格 = 2 列 × 4 行 Braille 子像素
    hres_w = width * 2
    hres_h = height * 4
    grid_bits = [[0] * width for _ in range(height)]  # 每格存 8-bit braille 点阵

    # Unicode Braille 点位 -> 位偏移：
    #   (子列, 子行)        dot    bit
    #   (0,0)               1       0
    #   (0,1)               2       1
    #   (0,2)               3       2
    #   (0,3)               7       6
    #   (1,0)               4       3
    #   (1,1)               5       4
    #   (1,2)               6       5
    #   (1,3)               8       7
    dot_bits = [
        [0, 3],  # sub_row 0
        [1, 4],  # sub_row 1
        [2, 5],  # sub_row 2
        [6, 7],  # sub_row 3
    ]

    def _set_pixel(hx: int, hy: int) -> None:
        if 0 <= hx < hres_w and 0 <= hy < hres_h:
            cx, sx = divmod(hx, 2)
            cy, sy = divmod(hy, 4)
            grid_bits[cy][cx] |= 1 << dot_bits[sy][sx]

    def _draw_line(x0: int, y0: int, x1: int, y1: int) -> None:
        dx = abs(x1 - x0); dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            _set_pixel(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy; x0 += sx
            if e2 < dx:
                err += dx; y0 += sy

    # 数据点 -> 高分辨率坐标（按迭代序号等分 X 轴）
    hxys: list[tuple[int, int]] = []
    for i, v in enumerate(values):
        hx = 0 if n == 1 else int(round(i * (hres_w - 1) / (n - 1)))
        hy = int(round((1 - v / vmax) * (hres_h - 1)))
        hy = max(0, min(hres_h - 1, hy))
        hxys.append((hx, hy))

    for i in range(len(hxys) - 1):
        _draw_line(hxys[i][0], hxys[i][1], hxys[i + 1][0], hxys[i + 1][1])
    # 单点情况至少画一个像素
    if len(hxys) == 1:
        _set_pixel(hxys[0][0], hxys[0][1])

    console.print(
        f"[bold cyan]Loss-Epoch 曲线[/bold cyan]  "
        f"samples={n}  epoch={min(epochs)}→{max(epochs)}  "
        f"loss max={raw_max:.4f} / min={min(values):.4f} / last={values[-1]:.4f}"
    )
    for y in range(height):
        if y == 0:
            label = f"{vmax:6.3f} "
        elif y == height - 1:
            label = f"{0.0:6.3f} "
        elif y == height // 2:
            label = f"{vmax / 2:6.3f} "
        else:
            label = "       "
        row_chars = "".join(chr(0x2800 + grid_bits[y][x]) for x in range(width))
        console.print(f"[dim]{label}[/dim]│[cyan]{row_chars}[/cyan]")

    # X 轴 + 刻度
    console.print("       └" + "─" * width)

    def _epoch_at(frac: float) -> int:
        idx = int(round(frac * (n - 1))) if n > 1 else 0
        return epochs[max(0, min(n - 1, idx))]

    positions = [0, width // 4, width // 2, (3 * width) // 4, width - 1]
    fracs = [0.0, 0.25, 0.5, 0.75, 1.0]
    labels = [f"e{_epoch_at(f)}" for f in fracs]
    tick_line = [" "] * width
    for p in positions:
        if 0 <= p < width:
            tick_line[p] = "│"
    console.print("       [dim]" + "".join(tick_line) + "[/dim]")
    label_line = [" "] * width
    for p, lab in zip(positions, labels):
        start = max(0, min(width - len(lab), p - len(lab) // 2))
        for j, ch in enumerate(lab):
            if start + j < width:
                label_line[start + j] = ch
    console.print("       [dim]" + "".join(label_line) + "[/dim]")


def _render_metric_bars(metric: dict, bar_width: int = 30) -> None:
    """用 Rich Table + 进度条渲染每个类别的 precision / recall。"""
    if not metric or not isinstance(metric, dict):
        console.print("[yellow]无 metric 数据[/yellow]")
        return

    def _bar(pct_raw) -> str:
        try:
            pct = max(0.0, min(100.0, float(pct_raw)))
        except (TypeError, ValueError):
            return "[dim]  N/A[/dim]"
        filled = int(round(bar_width * pct / 100))
        color = "green" if pct >= 80 else "yellow" if pct >= 50 else "red"
        bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * (bar_width - filled)}[/dim]"
        return f"{bar}  [bold]{pct:5.1f}%[/bold]"

    table = Table(
        title="分类指标 Precision / Recall",
        show_lines=True,           # 行与行之间加分隔线
        padding=(0, 2),            # 每列左右各留 2 空格
        title_style="bold cyan",
        border_style="dim",
    )
    table.add_column("类别", style="bold", no_wrap=True, min_width=10)
    table.add_column("Precision", justify="left", no_wrap=True, min_width=bar_width + 10)
    table.add_column("Recall",    justify="left", no_wrap=True, min_width=bar_width + 10)

    # "all" 置顶，其余按名称排序
    keys = sorted(metric.keys(), key=lambda k: (k != "all", str(k)))
    for cls in keys:
        m = metric.get(cls) or {}
        if not isinstance(m, dict):
            continue
        # 兼容 API 拼写 "percision"
        p = m.get("precision", m.get("percision"))
        r = m.get("recall")
        row_style = "bold magenta" if cls == "all" else None
        table.add_row(str(cls), _bar(p), _bar(r), style=row_style)
    console.print(table)


@app.command("metrics")
def task_metrics(
    task_id: str = typer.Argument(help="训练任务 ID"),
    model_type: str = typer.Option(..., "--model-type", help="(必填) " + HELP_MODEL_TYPE),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    execution_id: Optional[str] = typer.Option(None, "--execution-id", help="执行 ID，不传则自动获取"),
    fmt: str = typer.Option(
        "chart", "-o", "--output",
        help="输出格式：chart(默认，终端绘制 loss 曲线 + precision/recall 进度条) | "
             "json(供 skill/agent 读取原始 JSON) | yaml | table",
    ),
):
    """查询训练任务指标 loss / metric (3.13.1)

    - 默认 chart：loss-epoch 二维曲线 + 每个类别的 precision/recall 进度条（标注百分比）
    - skill/agent 请用 -o json 读取结构化原始数据
    """
    client = PanguClient()
    if not execution_id:
        detail = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
        execution_id = detail.get("execution_id", "")

    if not execution_id:
        console.print("[red]无法获取 execution_id，请通过 --execution-id 手动指定[/red]")
        raise typer.Exit(1)

    data = client.get(
        METRIC_PATH, workspace_id=workspace,
        params={"model_type": model_type}, execution_id=execution_id,
    )

    if fmt in ("json", "yaml", "id"):
        output(data, fmt=fmt)
        return

    loss = data.get("loss") if isinstance(data, dict) else None
    metric = data.get("metric") if isinstance(data, dict) else None
    _render_loss_curve(loss or [])
    console.print()
    _render_metric_bars(metric or {})


@app.command("checkpoints")
def task_checkpoints(
    task_id: str = typer.Argument(help="训练任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    execution_id: Optional[str] = typer.Option(None, "--execution-id", help="执行 ID，不传则自动获取"),
    limit: Optional[int] = typer.Option(None, "--limit", help="分页大小 (1-1000)"),
    page: Optional[int] = typer.Option(None, "--page", help="起始页 (1-1000)"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查询执行任务的断点列表 (3.13.10)，用于断点续训"""
    client = PanguClient()
    if not execution_id:
        detail = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
        execution_id = detail.get("execution_id", "")
    if not execution_id:
        console.print("[red]无法获取 execution_id，请通过 --execution-id 手动指定[/red]")
        raise typer.Exit(1)

    params: dict = {}
    if limit: params["limit"] = limit
    if page:  params["page"]  = page
    data = client.get(CHECKPOINT_PATH, workspace_id=workspace, params=params or None, execution_id=execution_id)
    output(data, fmt=fmt)


# ------------------------------ publish / models ------------------------------

@app.command("publish")
def publish_model(
    task_id: str = typer.Argument(help="训练任务 ID (用于自动拉取 execution_id / model_id)"),
    asset_name: str = typer.Option(..., "--asset-name", help="发布到资产中心的资产名称 (必填)"),
    visibility: str = typer.Option(..., "--visibility", help="(必填) " + HELP_VISIBILITY),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    execution_id: Optional[str] = typer.Option(None, "--execution-id", help="执行 ID，不传则自动获取"),
    model_id: Optional[str] = typer.Option(None, "--model-id", help="模型 ID，不传则自动获取"),
    category: str = typer.Option("pangu", "--category", help="(默认 pangu) " + HELP_CATEGORY),
    description: str = typer.Option("", "--description", "-d", help="资产描述"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """发布训练模型到资产中心 (3.13.7)"""
    client = PanguClient()

    if not execution_id or not model_id:
        detail = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
        execution_id = execution_id or detail.get("execution_id", "")
        model_id     = model_id     or detail.get("model_id", "")
    if not execution_id or not model_id:
        console.print("[red]无法自动获取 execution_id 或 model_id，请手动指定[/red]")
        raise typer.Exit(1)

    body = {
        "execution_id": execution_id,
        "model_id":     model_id,
        "asset_name":   asset_name,
        "visibility":   visibility,
        "description":  description,
        "category":     category,
    }
    data = client.post(PUBLISH_PATH, workspace_id=workspace, json=body)
    output(data, fmt=fmt)
    console.print(f"[green]模型已发布到资产中心，model_id={data.get('model_id', '')}[/green]")


@app.command("models")
def list_models(
    task_id: str = typer.Argument(help="训练任务 ID (用于自动获取 execution_id)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    execution_id: Optional[str] = typer.Option(None, "--execution-id", help="执行 ID (必填，不传则自动获取)"),
    model_type: Optional[str] = typer.Option(None, "--model-type", help=HELP_MODEL_TYPE),
    action_type: Optional[str] = typer.Option(None, "--action-type", help=HELP_ACTION_TYPE),
    model_name: Optional[str] = typer.Option(None, "--name", help="按模型名称过滤"),
    status: Optional[str] = typer.Option(None, "--status", help=HELP_MODEL_STAT),
    weather_job_type: Optional[str] = typer.Option(None, "--weather-job-type", help="气象作业类型 (AI 科学计算大模型使用)"),
    weather_data_config: Optional[str] = typer.Option(None, "--weather-data-config", help="气象数据配置 (AI 科学计算大模型使用)"),
    limit: Optional[int] = typer.Option(None, "--limit", help="分页大小 (1-1000)"),
    page: Optional[int] = typer.Option(None, "--page", help="起始页 (1-1000)"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """获取训练任务产出的模型列表 (3.13.8)"""
    client = PanguClient()
    if not execution_id:
        detail = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
        execution_id = detail.get("execution_id", "")
    if not execution_id:
        console.print("[red]无法自动获取 execution_id，请通过 --execution-id 手动指定[/red]")
        raise typer.Exit(1)

    params: dict = {"execution_id": execution_id}
    if model_type:          params["model_type"]         = model_type
    if action_type:         params["action_type"]        = action_type
    if model_name:          params["model_name"]         = model_name
    if status:              params["status"]             = status
    if weather_job_type:    params["weather_job_type"]   = weather_job_type
    if weather_data_config: params["weather_data_config"] = weather_data_config
    if limit:               params["limit"]              = limit
    if page:                params["page"]               = page

    data = client.get(MODELS_PATH, workspace_id=workspace, params=params)
    output(data, fmt=fmt, columns=MODEL_COLUMNS, list_key="models",
           title="训练模型列表", status_key="status", id_key="model_id")


# ------------------------------ model-detail / usage / running ------------------------------

@app.command("model-detail")
def model_detail(
    model_id: str = typer.Option(..., "--model-id", help="模型 ID (必填)"),
    model_type: str = typer.Option(..., "--model-type", help="(必填) " + HELP_MODEL_TYPE),
    train_type: str = typer.Option(..., "--train-type", help="(必填) " + HELP_TRAIN_TYPE),
    model_source: str = typer.Option(..., "--model-source", help="(必填) " + HELP_MODEL_SRC_DETAIL),
    strategy: Optional[str] = typer.Option(None, "--strategy", help="策略 (可选)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """获取训练参数模板 (3.13.11 model-detail)

    返回 workflow_info（含 parameters / storages / data_requirements / assets / steps / policy 等），
    用于构造 `pangu training create` 的 `task_parameter` 字段。
    ⚠️ 这是训练场景专用接口，与 `pangu model get`（3.12.2 资产元数据查询）完全不同，严禁混用。
    """
    client = PanguClient()
    body = {
        "model_id":     model_id,
        "model_type":   model_type,
        "train_type":   train_type,
        "model_source": model_source,
    }
    if strategy:
        body["strategy"] = strategy

    env_type = (client.config.env_type or "HCS").upper()
    if env_type == "HC":
        data = client.get(MODEL_DETAIL_PATH, workspace_id=workspace, params=body)
    else:
        data = client.post(MODEL_DETAIL_PATH, workspace_id=workspace, json=body)
    output(data, fmt=fmt)


@app.command("usage")
def task_usage(
    start_time: str = typer.Option(..., "--start-time", help="(必填) 起始时间，格式 YYYY-MM-DDTHH:MM:SS"),
    end_time: str = typer.Option(..., "--end-time", help="(必填) 结束时间，格式 YYYY-MM-DDTHH:MM:SS"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查询时间范围内训练任务资源用量 (3.13.12)"""
    client = PanguClient()
    data = client.get(USAGE_PATH, workspace_id=workspace, params={"start_time": start_time, "end_time": end_time})
    output(data, fmt=fmt)


@app.command("running")
def running_tasks(
    pool_id: str = typer.Argument(help="资源池 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    node_ip: Optional[str] = typer.Option(None, "--node-ip", help="资源池节点 IP (可选，按节点筛)"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查询指定资源池/节点上正在运行的训练任务 (3.13.13)"""
    client = PanguClient()
    params: dict = {"pool_id": pool_id}
    if node_ip:
        params["node_ip"] = node_ip
    data = client.get(RUNNING_PATH, workspace_id=workspace, params=params)
    output(data, fmt=fmt)
