"""Utility helpers for agent-safe commands."""

from __future__ import annotations

import contextlib
import io
import json
from json import JSONDecoder
from typing import Any, Callable

import typer

from pangu.agent.errors import AgentError


def success(**kwargs: Any) -> dict[str, Any]:
    data = {"ok": True}
    data.update(kwargs)
    return data


def failure(error: AgentError) -> dict[str, Any]:
    data = {
        "ok": False,
        "code": error.code,
        "message": error.message,
        "next_action": error.next_action,
    }
    if error.details:
        data["details"] = error.details
    return data


def print_json(data: Any) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


def run_quietly(func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
    """Call an existing Typer command function while capturing console output."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            func(*args, **kwargs)
    except typer.Exit as e:
        output = (stdout.getvalue() + stderr.getvalue()).strip()
        raise AgentError(
            "wrapped_command_failed",
            output or f"命令退出，exit_code={e.exit_code}",
            "inspect_wrapped_command_error",
        ) from e
    except Exception as e:
        output = (stdout.getvalue() + stderr.getvalue()).strip()
        message = f"{e}"
        if output:
            message = f"{message}\n{output}"
        raise AgentError("wrapped_command_failed", message, "inspect_wrapped_command_error") from e
    return stdout.getvalue() + stderr.getvalue()


def extract_first_json(text: str) -> Any:
    decoder = JSONDecoder()
    for i, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[i:])
            return value
        except ValueError:
            continue
    raise AgentError("json_parse_failed", "未能从命令输出中解析 JSON", "inspect_wrapped_command_output")
