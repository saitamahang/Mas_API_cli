"""盘古大模型平台管理 CLI 入口"""

from __future__ import annotations

from importlib.metadata import version as get_version
from typing import Optional

import typer
from rich.console import Console

from pangu.auth import AuthManager
from pangu.config import PanguConfig

try:
    __version__ = get_version("pangu")
except Exception:
    __version__ = "0.1.0"

app = typer.Typer(
    name="pangu",
    help="盘古大模型平台管理 CLI",
    no_args_is_help=True,
)
console = Console()


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        False, "--version", "-v", is_eager=True, help="显示版本号",
    ),
):
    if version:
        typer.echo(f"pangu {__version__}")
        raise typer.Exit()


# ---- 注册子命令 ----

from pangu.commands.config_cmd import app as config_app
app.add_typer(config_app, name="config")

from pangu.commands.workspace import app as workspace_app
app.add_typer(workspace_app, name="workspace")

from pangu.commands.pool import app as pool_app
app.add_typer(pool_app, name="pool")

from pangu.commands.model import app as model_app
app.add_typer(model_app, name="model")

from pangu.commands.service import app as service_app
app.add_typer(service_app, name="service")

from pangu.commands.training import app as training_app
app.add_typer(training_app, name="training")

from pangu.commands.dataset import app as dataset_app
app.add_typer(dataset_app, name="dataset")


# ---- 顶层认证命令 ----

auth_app = typer.Typer(help="认证管理")
app.add_typer(auth_app, name="auth")


@auth_app.command()
def login(
    password: Optional[str] = typer.Option(
        None, "--password", "-p", help="密码 (也可通过 PANGU_PASSWORD 环境变量传入)"
    ),
):
    """登录获取 Token"""
    config = PanguConfig.load()
    auth = AuthManager(config)
    try:
        auth.login(password=password)
        status = auth.status()
        console.print(f"[green]登录成功，Token 有效期: {status['remaining']}[/green]")
    except Exception as e:
        console.print(f"[red]登录失败: {e}[/red]")
        raise typer.Exit(1)


@auth_app.command()
def status():
    """查看认证状态"""
    config = PanguConfig.load()
    auth = AuthManager(config)
    info = auth.status()

    if info["mode"] == "apikey":
        state = "[green]已配置[/green]" if info["configured"] else "[red]未配置[/red]"
        console.print(f"认证模式: API Key ({state})")
    else:
        state = "[green]有效[/green]" if info["valid"] else "[red]无效/已过期[/red]"
        console.print(f"认证模式: Token ({state})")
        if info["valid"]:
            console.print(f"剩余有效期: {info['remaining']}")
        else:
            console.print("请运行 [bold]pangu auth login[/bold] 获取 Token")


# ---- 错误处理 ----

def _error_handler(func):
    """统一错误处理装饰器"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            console.print(f"[red]ERROR: {e}[/red]")
            raise typer.Exit(1)
    return wrapper


if __name__ == "__main__":
    app()
