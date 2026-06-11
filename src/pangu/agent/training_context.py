"""Training context consistency checks for agent-safe workflows."""

from __future__ import annotations

from typing import Any

from pangu.agent.errors import AgentError


CARD_TO_FLAVOR_ID = {
    1: "modelarts.pool.visual.xlarge",
    2: "modelarts.pool.visual.2xlarge",
    4: "modelarts.pool.visual.4xlarge",
    8: "modelarts.pool.visual.8xlarge",
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _train_flavor(body: dict[str, Any]) -> dict[str, Any]:
    params = (body.get("task_parameter") or {}).get("parameters") or []
    for param in params:
        if not isinstance(param, dict):
            continue
        if param.get("name") == "train_flavor" or param.get("format") == "train_flavor":
            value = param.get("value")
            return value if isinstance(value, dict) else {}
    return {}


def expected_training_context(state: dict[str, Any]) -> dict[str, Any]:
    selection = state.get("selection") or {}
    model = selection.get("model") or {}
    dataset = selection.get("dataset") or {}
    pool = selection.get("pool") or {}
    cards = selection.get("cards")
    try:
        cards_int = int(cards) if cards is not None else None
    except (TypeError, ValueError):
        cards_int = None
    return {
        "model": {
            "asset_id": _clean(model.get("asset_id")),
            "model_id": _clean(model.get("model_id")),
            "asset_name": _clean(model.get("asset_name")),
        },
        "dataset": {
            "dataset_id": _clean(dataset.get("dataset_id") or dataset.get("id")),
            "name": _clean(dataset.get("name")),
        },
        "pool": {
            "pool_id": _clean(pool.get("pool_id")),
            "pool_name": _clean(pool.get("pool_name")),
        },
        "resources": {
            "cards": cards_int,
            "flavor_id": CARD_TO_FLAVOR_ID.get(cards_int or 0, ""),
        },
    }


def actual_training_context(body: dict[str, Any]) -> dict[str, Any]:
    resource_config = body.get("resource_config") or {}
    train_flavor = _train_flavor(body)
    return {
        "model": {
            "asset_id": _clean(body.get("asset_id")),
            "model_id": _clean(body.get("model_id")),
            "asset_name": _clean(body.get("model_name")),
        },
        "dataset": {
            "dataset_id": _clean(body.get("dataset_id")),
            "name": _clean(body.get("dataset_name")),
        },
        "pool": {
            "pool_id": _clean(resource_config.get("pool_id") or train_flavor.get("pool_id")),
        },
        "resources": {
            "flavor_id": _clean(resource_config.get("flavor_id") or train_flavor.get("flavor_id")),
            "pool_node_count": body.get("pool_node_count"),
        },
    }


def _compare(
    mismatches: list[dict[str, Any]],
    field: str,
    expected: Any,
    actual: Any,
) -> None:
    if expected in (None, "") or actual in (None, ""):
        return
    if expected != actual:
        mismatches.append({"field": field, "expected": expected, "actual": actual})


def validate_training_context(state: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Ensure the generated YAML still belongs to the selected training context."""
    if not state.get("selection"):
        raise AgentError(
            "training_context_missing",
            "缺少训练选择上下文，请先运行 train scaffold",
            "rerun_train_scaffold",
        )

    expected = expected_training_context(state)
    actual = actual_training_context(body)
    mismatches: list[dict[str, Any]] = []

    _compare(mismatches, "model.asset_id", expected["model"]["asset_id"], actual["model"]["asset_id"])
    _compare(mismatches, "model.model_id", expected["model"]["model_id"], actual["model"]["model_id"])
    _compare(mismatches, "model.asset_name", expected["model"]["asset_name"], actual["model"]["asset_name"])
    _compare(mismatches, "dataset.dataset_id", expected["dataset"]["dataset_id"], actual["dataset"]["dataset_id"])
    _compare(mismatches, "dataset.name", expected["dataset"]["name"], actual["dataset"]["name"])
    _compare(mismatches, "pool.pool_id", expected["pool"]["pool_id"], actual["pool"]["pool_id"])
    _compare(mismatches, "resources.flavor_id", expected["resources"]["flavor_id"], actual["resources"]["flavor_id"])

    if mismatches:
        raise AgentError(
            "training_context_mismatch",
            "训练 YAML 与当前 scaffold 选择不一致。换模型、数据集、资源池或 cards 后必须重新运行 train scaffold。",
            "rerun_train_scaffold",
            {
                "mismatches": mismatches,
                "expected_context": expected,
                "actual_context": actual,
            },
        )
    return actual
