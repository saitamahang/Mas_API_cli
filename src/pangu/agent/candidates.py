"""Compact candidate pagination for agent-safe workflows."""

from __future__ import annotations

from typing import Any

from pangu.agent.errors import AgentError


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50

CANDIDATE_FIELDS: dict[str, tuple[str, ...]] = {
    "models": (
        "index",
        "asset_name",
        "asset_id",
        "model_id",
        "asset_type",
        "sub_asset_type",
        "asset_source",
        "can_train",
        "can_deploy",
        "create_time",
    ),
    "datasets": (
        "index",
        "name",
        "dataset_id",
        "id",
        "catalog",
        "modal",
        "content_type",
        "status",
        "record_num",
        "size",
        "create_time",
        "update_time",
    ),
    "sources": (
        "index",
        "name",
        "dataset_id",
        "id",
        "catalog",
        "modal",
        "content_type",
        "status",
        "record_num",
        "size",
        "create_time",
        "update_time",
    ),
    "pools": (
        "index",
        "pool_name",
        "pool_id",
        "pool_type",
        "status",
        "chip_type",
        "processor",
        "arch",
        "option_index",
    ),
    "deploy_options": (
        "index",
        "action_type",
        "arch",
        "chip_types",
        "spec",
        "pool_cmd",
    ),
}


def normalize_page_size(page_size: int) -> int:
    if page_size < 1:
        raise AgentError("invalid_page_size", "page_size 必须大于等于 1", "pass_valid_page_size")
    return min(page_size, MAX_PAGE_SIZE)


def compact_candidate(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    fields = CANDIDATE_FIELDS.get(kind)
    if not fields:
        raise AgentError("unsupported_candidate_kind", f"不支持的候选类型: {kind}", "choose_supported_candidate_kind")
    compact = {key: row.get(key) for key in fields if row.get(key) not in (None, "", [], {})}
    if "index" in row and "index" not in compact:
        compact["index"] = row["index"]
    return compact


def candidate_page(kind: str, rows: list[dict[str, Any]], page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
    if page < 1:
        raise AgentError("invalid_page", "page 必须大于等于 1", "pass_valid_page")
    page_size = normalize_page_size(page_size)
    total = len(rows)
    total_pages = (total + page_size - 1) // page_size if total else 0
    if total and page > total_pages:
        raise AgentError("invalid_page", f"page {page} 超出总页数 {total_pages}", "choose_existing_page")
    start = (page - 1) * page_size
    end = start + page_size
    items = [compact_candidate(kind, row) for row in rows[start:end] if isinstance(row, dict)]
    return {
        "kind": kind,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_more": bool(total_pages and page < total_pages),
        kind: items,
    }


def page_metadata(kind: str, rows: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    page_data = candidate_page(kind, rows, page=page, page_size=page_size)
    return {
        "kind": kind,
        "page": page_data["page"],
        "page_size": page_data["page_size"],
        "total": page_data["total"],
        "total_pages": page_data["total_pages"],
        "has_more": page_data["has_more"],
    }
