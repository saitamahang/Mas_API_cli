"""配置管理命令 - pangu config init/set/show/use-workspace"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from pangu.config import PanguConfig, CONFIG_DIR

app = typer.Typer(help="配置管理")
console = Console()


@app.command()
def init(
    non_interactive: bool = typer.Option(False, "--non-interactive", "-n", help="非交互模式，通过选项直接传入所有值"),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", help="盘古服务 APIG 域名"),
    iam_endpoint: Optional[str] = typer.Option(None, "--iam-endpoint", help="IAM 认证域名"),
    auth_mode: Optional[str] = typer.Option(None, "--auth-mode", help="认证模式: token | apikey"),
    username: Optional[str] = typer.Option(None, "--username", help="用户名 (token 模式)"),
    domain_name: Optional[str] = typer.Option(None, "--domain-name", help="租户名 (token 模式)"),
    project_name: Optional[str] = typer.Option(None, "--project-name", help="项目名称 (token 模式)"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API Key (apikey 模式)"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="项目 ID"),
    workspace_id: Optional[str] = typer.Option(None, "--workspace-id", help="默认工作空间 ID"),
    password: Optional[str] = typer.Option(None, "--password", help="登录密码 (可选，明文存储)"),
):
    """初始化配置（默认交互式，加 -n 则非交互）"""
    config = PanguConfig.load()

    if non_interactive:
        # 非交互模式：直接应用选项值，缺少必填项则报错
        if endpoint is not None:
            config.endpoint = endpoint
        if iam_endpoint is not None:
            config.iam_endpoint = iam_endpoint
        if auth_mode is not None:
            config.auth_mode = auth_mode
        if username is not None:
            config.username = username
        if domain_name is not None:
            config.domain_name = domain_name
        if project_name is not None:
            config.project_name = project_name
        if api_key is not None:
            config.api_key = api_key
        if project_id is not None:
            config.project_id = project_id
        if workspace_id is not None:
            config.default_workspace_id = workspace_id
        if password is not None:
            config.password = password

        # 校验必填项
        missing = config.validate_required("endpoint", "project_id")
        if config.auth_mode == "token":
            missing += config.validate_required("iam_endpoint", "username", "domain_name", "project_name")
        elif config.auth_mode == "apikey":
            missing += config.validate_required("api_key")
        if missing:
            console.print(f"[red]缺少必填项: {', '.join(missing)}[/red]")
            raise typer.Exit(1)

        config.save()
        console.print(f"[green]配置已保存到 {CONFIG_DIR / 'config.yaml'}[/green]")
        return

    # 交互模式：选项值作为默认值，仍可交互修改
    console.print("[bold]盘古 CLI 配置初始化[/bold]\n")

    config.endpoint = typer.prompt(
        "盘古服务 APIG 域名 (如 pangulargemodels.sa-fb-1.out.a3.com)",
        default=endpoint or config.endpoint or "",
    )
    config.iam_endpoint = typer.prompt(
        "IAM 认证域名 (如 iam-apigateway-proxy.sa-fb-1.out.a3.com)",
        default=iam_endpoint or config.iam_endpoint or "",
    )

    config.auth_mode = typer.prompt(
        "认证模式 (token/apikey)",
        default=auth_mode or config.auth_mode or "token",
    )

    if config.auth_mode == "token":
        config.username = typer.prompt("用户名", default=username or config.username or "")
        config.domain_name = typer.prompt("租户名", default=domain_name or config.domain_name or "")
        config.project_name = typer.prompt("项目名称", default=project_name or config.project_name or "")
    else:
        config.api_key = typer.prompt("API Key", default=api_key or config.api_key or "")

    config.project_id = typer.prompt("项目 ID", default=project_id or config.project_id or "")
    config.default_workspace_id = typer.prompt(
        "默认工作空间 ID (可选)",
        default=workspace_id or config.default_workspace_id or "",
    )

    config.save()
    console.print(f"\n[green]配置已保存到 {CONFIG_DIR / 'config.yaml'}[/green]")


@app.command("set")
def set_value(key: str, value: str):
    """设置配置项"""
    config = PanguConfig.load()
    try:
        config.set(key, value)
        config.save()
        console.print(f"[green]{key} = {value}[/green]")
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        console.print(f"可用配置项: {', '.join(config.model_fields.keys())}")
        raise typer.Exit(1)


@app.command()
def show():
    """显示当前配置"""
    config = PanguConfig.load()

    table = Table(title="当前配置", show_lines=False)
    table.add_column("配置项", style="bold cyan")
    table.add_column("值")

    for key, field in config.model_fields.items():
        value = getattr(config, key)
        # 脱敏处理
        display = str(value)
        if key in ("api_key", "password") and value:
            display = value[:2] + "***" + value[-2:] if len(value) > 4 else "***"
        table.add_row(key, display)

    console.print(table)


@app.command("use-workspace")
def use_workspace(workspace_id: str):
    """切换默认工作空间"""
    config = PanguConfig.load()
    config.default_workspace_id = workspace_id
    config.save()
    console.print(f"[green]默认工作空间已切换为: {workspace_id}[/green]")
