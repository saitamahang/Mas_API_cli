"""输出格式化模块 - table/json/yaml/id 输出，状态颜色高亮"""

from __future__ import annotations

import json
import sys
from typing import Any, Optional, Sequence

import yaml
from rich.console import Console
from rich.table import Table

console = Console()

# 状态 → 颜色映射
STATUS_COLORS = {
    # 正常/成功
    "running": "green",
    "completed": "green",
    "0": "green",  # workspace status=0 正常
    # 进行中
    "init": "yellow",
    "pending": "yellow",
    "deploying": "yellow",
    "creating": "yellow",
    "updating": "yellow",
    "stopping": "yellow",
    "deleting": "yellow",
    "1": "yellow",  # workspace status=1 删除中
    # 告警
    "concerning": "bright_yellow",
    # 失败
    "failed": "red",
    "error": "red",
    # 已停止/已删除
    "stopped": "dim",
    "2": "dim",  # workspace status=2 已删除
}

# workspace status 数字 → 文本
WORKSPACE_STATUS = {0: "正常", 1: "删除中", 2: "已删除"}


def colorize_status(status: Any) -> str:
    """给状态值加颜色标记 (rich markup)"""
    s = str(status).lower()
    color = STATUS_COLORS.get(s, "white")
    # workspace 数字状态转文本
    if isinstance(status, int) and status in WORKSPACE_STATUS:
        label = WORKSPACE_STATUS[status]
    else:
        label = str(status)
    return f"[{color}]{label}[/{color}]"


def print_json_output(data: Any) -> None:
    """JSON 格式输出"""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def print_yaml_output(data: Any) -> None:
    """YAML 格式输出"""
    print(yaml.dump(data, default_flow_style=False, allow_unicode=True), end="")


def print_id_output(data: Any, id_key: str = "id") -> None:
    """只输出 ID"""
    if isinstance(data, list):
        for item in data:
            print(item.get(id_key, ""))
    elif isinstance(data, dict):
        print(data.get(id_key, ""))
    else:
        print(data)


def print_table(
    data: Sequence[dict],
    columns: list[tuple[str, str]],
    title: Optional[str] = None,
    status_key: Optional[str] = None,
) -> None:
    """打印 rich 表格

    Args:
        data: 数据列表
        columns: [(字段名, 表头)] 列表
        title: 表格标题
        status_key: 状态字段名，自动高亮
    """
    table = Table(title=title, show_lines=False)
    for _, header in columns:
        table.add_column(header)

    for row in data:
        cells = []
        for field, _ in columns:
            value = row.get(field, "")
            if field == status_key and value is not None:
                cells.append(colorize_status(value))
            else:
                cells.append(str(value) if value is not None else "")
        table.add_row(*cells)

    console.print(table)


def print_detail(
    data: dict,
    fields: list[tuple[str, str]],
    title: Optional[str] = None,
    status_key: Optional[str] = None,
) -> None:
    """打印详情面板（key-value 格式）

    Args:
        data: 资源详情字典
        fields: [(字段名, 显示名)] 列表
        title: 面板标题
        status_key: 状态字段名，自动高亮
    """
    table = Table(
        title=title,
        show_header=False,
        show_lines=False,
        pad_edge=False,
        box=None,
    )
    table.add_column("Key", style="bold cyan", min_width=20)
    table.add_column("Value")

    for field, label in fields:
        value = data.get(field, "")
        if field == status_key and value is not None:
            display = colorize_status(value)
        else:
            display = str(value) if value is not None else ""
        table.add_row(label, display)

    console.print(table)


def output(
    data: Any,
    fmt: str = "table",
    columns: Optional[list[tuple[str, str]]] = None,
    detail_fields: Optional[list[tuple[str, str]]] = None,
    title: Optional[str] = None,
    status_key: Optional[str] = None,
    id_key: str = "id",
    list_key: Optional[str] = None,
) -> None:
    """统一输出入口

    Args:
        data: API 返回数据
        fmt: 输出格式 (table/json/yaml/id)
        columns: 列表模式的列定义 [(field, header)]
        detail_fields: 详情模式的字段定义 [(field, label)]
        title: 标题
        status_key: 状态字段
        id_key: ID 字段名
        list_key: 列表数据在响应中的 key (如 "workspaces", "services")
    """
    if fmt == "json":
        print_json_output(data)
        return

    if fmt == "yaml":
        print_yaml_output(data)
        return

    if fmt == "id":
        items = data.get(list_key, data) if list_key and isinstance(data, dict) else data
        print_id_output(items, id_key=id_key)
        return

    # table 模式
    if isinstance(data, dict) and list_key and list_key in data:
        # 列表响应
        items = data[list_key]
        count = data.get("count", len(items))
        if title:
            title = f"{title} (共 {count} 条)"
        if columns:
            print_table(items, columns, title=title, status_key=status_key)
        else:
            print_json_output(items)
    elif isinstance(data, list):
        if columns:
            print_table(data, columns, title=title, status_key=status_key)
        else:
            print_json_output(data)
    elif isinstance(data, dict):
        # 单条详情
        if detail_fields:
            print_detail(data, detail_fields, title=title, status_key=status_key)
        else:
            print_json_output(data)
    else:
        console.print(str(data))
