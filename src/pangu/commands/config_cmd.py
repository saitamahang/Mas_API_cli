"""配置管理命令 - pangu config init/set/show/use-workspace"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from pangu.config import PanguConfig

app = typer.Typer(help="配置管理")
console = Console()


@app.command()
def init():
    """交互式初始化配置"""
    config = PanguConfig.load()

    console.print("[bold]盘古 CLI 配置初始化[/bold]\n")

    config.endpoint = typer.prompt(
        "盘古服务 APIG 域名 (如 pangulargemodels.sa-fb-1.out.a3.com)",
        default=config.endpoint or "",
    )
    config.iam_endpoint = typer.prompt(
        "IAM 认证域名 (如 iam-apigateway-proxy.sa-fb-1.out.a3.com)",
        default=config.iam_endpoint or "",
    )

    config.auth_mode = typer.prompt(
        "认证模式 (token/apikey)",
        default=config.auth_mode or "token",
    )

    if config.auth_mode == "token":
        config.username = typer.prompt("用户名", default=config.username or "")
        config.domain_name = typer.prompt("租户名", default=config.domain_name or "")
        config.project_name = typer.prompt("项目名称", default=config.project_name or "")
    else:
        config.api_key = typer.prompt("API Key", default=config.api_key or "")

    config.project_id = typer.prompt("项目 ID", default=config.project_id or "")
    config.default_workspace_id = typer.prompt(
        "默认工作空间 ID (可选)",
        default=config.default_workspace_id or "",
    )

    config.save()
    console.print(f"\n[green]配置已保存到 {config.CONFIG_DIR / 'config.yaml'}[/green]")


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
        if key in ("api_key",) and value:
            display = value[:6] + "***" + value[-4:] if len(value) > 10 else "***"
        table.add_row(key, display)

    console.print(table)


@app.command("use-workspace")
def use_workspace(workspace_id: str):
    """切换默认工作空间"""
    config = PanguConfig.load()
    config.default_workspace_id = workspace_id
    config.save()
    console.print(f"[green]默认工作空间已切换为: {workspace_id}[/green]")
