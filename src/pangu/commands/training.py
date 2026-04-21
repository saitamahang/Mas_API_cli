"""训练任务管理命令 - pangu training"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console

from pangu.client import PanguClient
from pangu.output import output

app = typer.Typer(help="训练任务管理")
console = Console()

BASE      = "/v1/{project_id}/workspaces/{workspace_id}/model-train"
TASK_PATH = BASE + "/train-task/{task_id}"
TASKS_PATH = BASE + "/train-tasks"          # 批量删除
ACTION_PATH = BASE + "/train-task/{task_id}/action"
EXEC_PATH = BASE + "/execution/{execution_id}"
EXECS_PATH = BASE + "/executions/{execution_id}"  # metrics 用复数
MODELS_PATH = BASE + "/models"
PUBLISH_PATH = BASE + "/model/publish"
USAGE_PATH = BASE + "/resource-usage"
RUNNING_PATH = BASE + "/tasks"              # 资源池上运行的任务

DETAIL_FIELDS = [
    ("task_id",       "任务 ID"),
    ("task_name",     "名称"),
    ("task_status",   "状态"),
    ("model_type",    "模型类型"),
    ("train_type",    "训练类型"),
    ("train_process", "进度"),
    ("pool_node_count","节点数"),
    ("train_task_desc","描述"),
    ("create_time",   "创建时间"),
    ("update_time",   "更新时间"),
]

MODEL_COLUMNS = [
    ("model_id",    "模型 ID"),
    ("model_name",  "模型名称"),
    ("model_type",  "类型"),
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


@app.command("get")
def get_task(
    task_id: str = typer.Argument(help="训练任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
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


@app.command("create")
def create_task(
    config: Optional[str] = typer.Option(None, "--config", "-f", help="YAML 配置文件路径"),
    name: Optional[str] = typer.Option(None, "--name", help="任务名称 (task_name)"),
    asset_id: Optional[str] = typer.Option(None, "--asset-id", help="模型资产 ID"),
    model_id: Optional[str] = typer.Option(None, "--model-id", help="模型 ID (NLP/MM 必填)"),
    model_type: Optional[str] = typer.Option(None, "--model-type", help="NLP|MM|CV|Predict|AI4Science"),
    train_type: Optional[str] = typer.Option(None, "--train-type", help="SFT|PRETRAIN|LORA|DPO"),
    model_source: Optional[str] = typer.Option(None, "--model-source", help="pangu|third|pangu-third"),
    pool_id: Optional[str] = typer.Option(None, "--pool-id", help="资源池 ID"),
    nodes: Optional[int] = typer.Option(None, "--nodes", help="资源池节点数"),
    t_flops: Optional[int] = typer.Option(None, "--t-flops", help="总算力数 (卡数 × flavor)"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="任务描述"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    wait: bool = typer.Option(False, "--wait", help="等待任务完成"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """创建训练任务 (3.13.5)，可通过 --config 传入 YAML"""
    body: dict = _load_yaml(config) if config else {}

    # CLI 参数覆盖
    if name:             body["task_name"] = name
    if asset_id:         body["asset_id"] = asset_id
    if model_id:         body["model_id"] = model_id
    if model_type:       body["model_type"] = model_type
    if train_type:       body["train_type"] = train_type
    if model_source:     body["model_source"] = model_source
    if t_flops is not None: body["t_flops"] = t_flops
    if description:      body["train_task_desc"] = description
    if nodes is not None: body["pool_node_count"] = nodes

    if pool_id:
        rc = body.setdefault("resource_config", {})
        rc["pool_id"] = pool_id

    for req in ("task_name", "asset_id", "model_type", "train_type", "model_source", "t_flops"):
        if not body.get(req):
            console.print(f"[red]缺少必填字段: {req}[/red]")
            raise typer.Exit(1)

    client = PanguClient()
    data = client.post(BASE + "/train-task", workspace_id=workspace, json=body)
    task_id = data.get("task_id", "")

    output(data, fmt=fmt, detail_fields=DETAIL_FIELDS, title="训练任务已创建", status_key="task_status")

    if wait and task_id:
        console.print(f"[cyan]等待任务 {task_id} 完成...[/cyan]")
        final = client.wait_for_status(
            TASK_PATH,
            target_statuses=["completed", "failed", "stopped"],
            failure_statuses=["failed", "stopped"],
            status_key="task_status",
            workspace_id=workspace,
            task_id=task_id,
        )
        console.print(f"[green]任务完成，最终状态: {final.get('task_status')}[/green]")


@app.command("stop")
def stop_task(
    task_id: str = typer.Argument(help="训练任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
):
    """停止训练任务 (3.13.2)"""
    if not yes and not typer.confirm(f"确认停止任务 {task_id}?"):
        raise typer.Abort()
    client = PanguClient()
    client.post(ACTION_PATH, workspace_id=workspace, json={"action_name": "stop"}, task_id=task_id)
    console.print(f"[green]任务 {task_id} 已停止[/green]")


@app.command("retry")
def retry_task(
    task_id: str = typer.Argument(help="训练任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    wait: bool = typer.Option(False, "--wait", help="等待任务完成"),
):
    """重试失败的训练任务 (3.13.2)"""
    client = PanguClient()
    data = client.post(ACTION_PATH, workspace_id=workspace, json={"action_name": "retry"}, task_id=task_id)
    console.print(f"[green]任务 {task_id} 已重试[/green]")

    if wait:
        console.print(f"[cyan]等待任务完成...[/cyan]")
        final = client.wait_for_status(
            TASK_PATH,
            target_statuses=["completed", "failed", "stopped"],
            failure_statuses=["failed", "stopped"],
            status_key="task_status",
            workspace_id=workspace,
            task_id=task_id,
        )
        console.print(f"[green]最终状态: {final.get('task_status')}[/green]")


@app.command("delete")
def delete_task(
    task_ids: list[str] = typer.Argument(help="训练任务 ID（可传多个）"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
):
    """批量删除训练任务 (3.13.9)"""
    if not yes and not typer.confirm(f"确认删除 {len(task_ids)} 个任务?"):
        raise typer.Abort()
    client = PanguClient()
    id_list = ",".join(task_ids)
    data = client.delete(TASKS_PATH, workspace_id=workspace, params={"train_task_id_list": id_list})
    console.print(f"[green]成功删除: {data.get('success_num', '?')} 个，失败: {data.get('failed_num', '?')} 个[/green]")


@app.command("logs")
def task_logs(
    task_id: str = typer.Argument(help="训练任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    execution_id: Optional[str] = typer.Option(None, "--execution-id", help="执行 ID（从 get 详情获取）"),
    job_id: Optional[str] = typer.Option(None, "--job-id", help="步骤 Job ID（从 steps_execution 获取）"),
    node: str = typer.Option("worker-0", "--node", help="节点名称，如 worker-0"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查看训练日志 (3.13.4)

    需要先通过 pangu training get <task_id> 获取 execution_id 和 steps_execution 中的 job_id。
    """
    if not execution_id or not job_id:
        console.print("[yellow]正在自动获取 execution_id 和 job_id...[/yellow]")
        client = PanguClient()
        detail = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
        if not execution_id:
            execution_id = detail.get("execution_id", "")
        if not job_id:
            # 从 steps_execution 中提取第一个 job_id
            import json as _json
            steps = detail.get("steps_execution", "")
            if isinstance(steps, str) and steps:
                try:
                    steps = _json.loads(steps)
                except Exception:
                    steps = {}
            if isinstance(steps, dict):
                for step_name, step_info in steps.items():
                    if isinstance(step_info, dict) and step_info.get("job_id"):
                        job_id = step_info["job_id"]
                        console.print(f"  使用步骤 [{step_name}] job_id: {job_id}")
                        break

    if not execution_id or not job_id:
        console.print("[red]无法获取 execution_id 或 job_id，请通过 --execution-id 和 --job-id 手动指定[/red]")
        raise typer.Exit(1)

    client = PanguClient()
    path = BASE + "/execution/{execution_id}/training-jobs/{job_id}/tasks/{log_task_id}/preview"
    data = client.get(path, workspace_id=workspace, execution_id=execution_id, job_id=job_id, log_task_id=node)
    output(data, fmt=fmt)


@app.command("nodes")
def task_nodes(
    task_id: str = typer.Argument(help="训练任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    execution_id: Optional[str] = typer.Option(None, "--execution-id", help="执行 ID"),
    job_id: Optional[str] = typer.Option(None, "--job-id", help="步骤 Job ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查看训练节点信息 (3.13.6)"""
    if not execution_id or not job_id:
        client = PanguClient()
        detail = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
        if not execution_id:
            execution_id = detail.get("execution_id", "")
        if not job_id:
            import json as _json
            steps = detail.get("steps_execution", "")
            if isinstance(steps, str) and steps:
                try:
                    steps = _json.loads(steps)
                except Exception:
                    steps = {}
            if isinstance(steps, dict):
                for step_info in steps.values():
                    if isinstance(step_info, dict) and step_info.get("job_id"):
                        job_id = step_info["job_id"]
                        break

    if not execution_id or not job_id:
        console.print("[red]请通过 --execution-id 和 --job-id 手动指定[/red]")
        raise typer.Exit(1)

    client = PanguClient()
    path = BASE + "/execution/{execution_id}/training-jobs/{job_id}"
    data = client.get(path, workspace_id=workspace, execution_id=execution_id, job_id=job_id)
    output(data, fmt=fmt)


@app.command("metrics")
def task_metrics(
    task_id: str = typer.Argument(help="训练任务 ID"),
    model_type: str = typer.Option(..., "--model-type", help="模型类型: NLP|MM|CV|Predict|AI4Science"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    execution_id: Optional[str] = typer.Option(None, "--execution-id", help="执行 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查看训练指标 (3.13.1)"""
    if not execution_id:
        client = PanguClient()
        detail = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
        execution_id = detail.get("execution_id", "")

    if not execution_id:
        console.print("[red]无法获取 execution_id，请通过 --execution-id 手动指定[/red]")
        raise typer.Exit(1)

    client = PanguClient()
    path = BASE + "/executions/{execution_id}/metric"
    data = client.get(path, workspace_id=workspace, params={"model_type": model_type}, execution_id=execution_id)
    output(data, fmt=fmt)


@app.command("checkpoints")
def task_checkpoints(
    task_id: str = typer.Argument(help="训练任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    execution_id: Optional[str] = typer.Option(None, "--execution-id", help="执行 ID"),
    limit: Optional[int] = typer.Option(None, "--limit", help="分页大小"),
    page: Optional[int] = typer.Option(None, "--page", help="起始页"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查看断点 Checkpoint 列表 (3.13.10)"""
    if not execution_id:
        client = PanguClient()
        detail = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
        execution_id = detail.get("execution_id", "")

    if not execution_id:
        console.print("[red]无法获取 execution_id，请通过 --execution-id 手动指定[/red]")
        raise typer.Exit(1)

    client = PanguClient()
    path = BASE + "/execution/{execution_id}/checkpoints"
    params: dict = {}
    if limit: params["limit"] = limit
    if page:  params["page"] = page
    data = client.get(path, workspace_id=workspace, params=params or None, execution_id=execution_id)
    output(data, fmt=fmt)


@app.command("publish")
def publish_model(
    task_id: str = typer.Argument(help="训练任务 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    execution_id: Optional[str] = typer.Option(None, "--execution-id", help="执行 ID"),
    model_id: Optional[str] = typer.Option(None, "--model-id", help="模型 ID"),
    asset_name: str = typer.Option(..., "--asset-name", help="发布的资产名称（必填）"),
    visibility: str = typer.Option(..., "--visibility", help="可见性（必填）: current|all"),
    description: str = typer.Option("", "--description", "-d", help="描述"),
    category: str = typer.Option("3rd", "--category", help="模型来源: pangu|3rd"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """发布训练模型到资产中心 (3.13.7)"""
    client = PanguClient()

    if not execution_id or not model_id:
        detail = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
        if not execution_id:
            execution_id = detail.get("execution_id", "")
        if not model_id:
            model_id = detail.get("model_id", "")

    if not execution_id or not model_id:
        console.print("[red]请通过 --execution-id 和 --model-id 手动指定[/red]")
        raise typer.Exit(1)

    body: dict = {
        "execution_id": execution_id,
        "model_id": model_id,
        "asset_name": asset_name,
        "visibility": visibility,
        "description": description,
        "category": category,
    }

    data = client.post(PUBLISH_PATH, workspace_id=workspace, json=body)
    output(data, fmt=fmt)
    console.print("[green]模型已发布到资产中心[/green]")


@app.command("models")
def list_models(
    task_id: str = typer.Argument(help="训练任务 ID（用于自动获取 execution_id）"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    execution_id: Optional[str] = typer.Option(None, "--execution-id", help="执行 ID（必填，可自动从任务详情获取）"),
    model_type: Optional[str] = typer.Option(None, "--model-type", help="NLP|MM|CV|Predict|AI4Science"),
    action_type: Optional[str] = typer.Option(None, "--action-type", help="PRETRAIN|SFT|LORA|QUANTIZATION|DPO"),
    model_name: Optional[str] = typer.Option(None, "--name", help="按模型名称过滤"),
    status: Optional[str] = typer.Option(None, "--status", help="published|completed"),
    limit: Optional[int] = typer.Option(None, "--limit", help="每页数量"),
    page: Optional[int] = typer.Option(None, "--page", help="起始页"),
    fmt: str = typer.Option("table", "-o", "--output", help="输出格式"),
):
    """查看训练任务产生的模型列表 (3.13.8)，execution_id 必填"""
    client = PanguClient()

    if not execution_id:
        console.print("[yellow]正在自动获取 execution_id...[/yellow]")
        detail = client.get(TASK_PATH, workspace_id=workspace, task_id=task_id)
        execution_id = detail.get("execution_id", "")

    if not execution_id:
        console.print("[red]无法获取 execution_id，请通过 --execution-id 手动指定[/red]")
        raise typer.Exit(1)

    params: dict = {"execution_id": execution_id}
    if model_type:  params["model_type"] = model_type
    if action_type: params["action_type"] = action_type
    if model_name:  params["model_name"] = model_name
    if status:      params["status"] = status
    if limit:       params["limit"] = limit
    if page:        params["page"] = page

    data = client.get(MODELS_PATH, workspace_id=workspace, params=params)
    output(data, fmt=fmt, columns=MODEL_COLUMNS, list_key="models", title="训练模型列表", status_key="status", id_key="model_id")


@app.command("usage")
def task_usage(
    start_time: str = typer.Option(..., "--start-time", help="开始时间（必填，如 2024-01-01T00:00:00）"),
    end_time: str = typer.Option(..., "--end-time", help="结束时间（必填）"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查询时间范围内训练任务资源用量 (3.13.12)，start_time 和 end_time 必填"""
    client = PanguClient()
    data = client.get(USAGE_PATH, workspace_id=workspace, params={"start_time": start_time, "end_time": end_time})
    output(data, fmt=fmt)


@app.command("model-detail")
def model_detail(
    model_id: str = typer.Option(..., "--model-id", help="模型 ID（必填）"),
    model_type: str = typer.Option(..., "--model-type", help="模型类型（必填）: NLP|MM|CV|Predict|AI4Science"),
    train_type: str = typer.Option(..., "--train-type", help="训练类型（必填）: SFT|PRETRAIN|LORA|DPO"),
    model_source: str = typer.Option(..., "--model-source", help="模型来源（必填）: pangu|third|pangu-third"),
    strategy: Optional[str] = typer.Option(None, "--strategy", help="策略（可选）"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """获取模型详情，用于创建训练任务前查询 task_parameter 等参数 (3.13.11)"""
    client = PanguClient()
    body: dict = {
        "model_id": model_id,
        "model_type": model_type,
        "train_type": train_type,
        "model_source": model_source,
    }
    if strategy:
        body["strategy"] = strategy
    data = client.post(BASE + "/model-detail", workspace_id=workspace, json=body)
    output(data, fmt=fmt)


@app.command("running")
def running_tasks(
    pool_id: str = typer.Argument(help="资源池 ID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="工作空间 ID"),
    node_ip: Optional[str] = typer.Option(None, "--node-ip", help="资源池节点 IP"),
    fmt: str = typer.Option("json", "-o", "--output", help="输出格式"),
):
    """查询指定资源池上运行的训练任务 (3.13.13)"""
    client = PanguClient()
    params: dict = {"pool_id": pool_id}
    if node_ip: params["node_ip"] = node_ip

    data = client.get(RUNNING_PATH, workspace_id=workspace, params=params)
    output(data, fmt=fmt)
