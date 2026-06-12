"""Helpers for resolving published model assets."""

from __future__ import annotations

from typing import Any


PUBLISHED_ASSET_SOURCE = "Publish"


def flatten_asset_ext(item: dict[str, Any]) -> dict[str, Any]:
    ma = item.get("modelAsset") or {}
    merged = dict(ma) if isinstance(ma, dict) else dict(item)
    for key in (
        "can_deploy",
        "can_train",
        "can_delete",
        "can_eval",
        "can_quantize",
        "can_export",
        "model_id",
        "is_used",
        "publish_info",
        "subscribe_info",
    ):
        if key in item:
            merged[key] = item[key]
    return merged


def published_asset_query(asset_name: str | None = None, *, current_workspace: bool = True) -> dict[str, Any]:
    params: dict[str, Any] = {
        "limit": 1000,
        "offset": 0,
        "asset_source": PUBLISHED_ASSET_SOURCE,
    }
    if current_workspace:
        params["workspace_source"] = "current"
    if asset_name:
        params["asset_name"] = asset_name
    return params


def select_published_asset(
    assets: list[dict[str, Any]],
    *,
    model_id: str | None = None,
    asset_name: str | None = None,
) -> dict[str, Any] | None:
    model_id = str(model_id or "")
    asset_name = str(asset_name or "")

    if model_id:
        by_model = [row for row in assets if str(row.get("model_id") or "") == model_id]
        if asset_name:
            named = [row for row in by_model if str(row.get("asset_name") or row.get("name") or "") == asset_name]
            if len(named) == 1:
                return named[0]
        if len(by_model) == 1:
            return by_model[0]

    if asset_name:
        by_name = [row for row in assets if str(row.get("asset_name") or row.get("name") or "") == asset_name]
        if len(by_name) == 1:
            return by_name[0]

    return None
