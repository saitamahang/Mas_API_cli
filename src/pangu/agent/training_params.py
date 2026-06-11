"""Training parameter helpers for agent-safe workflows."""

from __future__ import annotations

import json
from typing import Any

from pangu.agent.errors import AgentError

PROTECTED_PARAM_NAMES = {"train_flavor"}


def parse_training_param_value(value: str) -> Any:
    """Parse a CLI parameter value using JSON when possible."""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value


def encode_training_param_value(value: Any) -> str:
    """Encode a value so the wrapped pangu CLI parses it back to the same type."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _parameters_from_body(body: dict[str, Any]) -> list[dict[str, Any]]:
    params = (body.get("task_parameter") or {}).get("parameters") or []
    return [p for p in params if isinstance(p, dict)]


def parameter_key(param: dict[str, Any]) -> str:
    return str(param.get("name") or param.get("format") or "")


def is_protected_param(param: dict[str, Any]) -> bool:
    names = {str(param.get("name") or ""), str(param.get("format") or "")}
    return bool(names & PROTECTED_PARAM_NAMES)


def list_training_parameters_from_body(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Return compact, indexed training parameters safe to show to an agent."""
    rows = []
    metadata_fields = (
        "label",
        "description",
        "desc",
        "type",
        "data_type",
        "format",
        "constraint",
        "constraints",
        "enum",
        "options",
        "min",
        "max",
        "required",
    )
    for idx, param in enumerate(_parameters_from_body(body), start=1):
        key = parameter_key(param)
        if not key:
            continue
        row = {
            "index": idx,
            "key": key,
            "editable": not is_protected_param(param),
        }
        for field in ("name", "format", "value", "default"):
            if param.get(field) not in (None, "", [], {}):
                row[field] = param.get(field)
        for field in metadata_fields:
            if field not in row and param.get(field) not in (None, "", [], {}):
                row[field] = param.get(field)
        if not row["editable"]:
            row["reason"] = "managed_by_agent_workflow"
        rows.append(row)
    return rows


def _lookup_param(params: list[dict[str, Any]], raw_key: str) -> dict[str, Any]:
    if raw_key.isdigit():
        index = int(raw_key)
        if index < 1 or index > len(params):
            raise AgentError(
                "training_param_index_not_found",
                f"训练参数索引不存在: {index}",
                "run_train_params_and_choose_existing_index",
                {"received_index": index, "parameter_count": len(params)},
            )
        return params[index - 1]

    matches = [
        param
        for param in params
        if raw_key in {str(param.get("name") or ""), str(param.get("format") or "")}
    ]
    if not matches:
        raise AgentError(
            "training_param_not_found",
            f"训练参数不存在: {raw_key}",
            "run_train_params_and_choose_existing_parameter",
            {"received_param": raw_key},
        )
    if len(matches) > 1:
        raise AgentError(
            "training_param_ambiguous",
            f"训练参数名称不唯一: {raw_key}",
            "use_parameter_index_from_train_params",
            {"received_param": raw_key, "matches": len(matches)},
        )
    return matches[0]


def resolve_training_param_overrides_from_body(
    body: dict[str, Any],
    specs: list[str] | None,
) -> list[dict[str, Any]]:
    """Validate and convert user overrides into wrapped CLI --param strings."""
    if not specs:
        return []
    params = _parameters_from_body(body)
    overrides = []
    seen: set[str] = set()
    for spec in specs:
        if "=" not in spec:
            raise AgentError(
                "invalid_training_param_override",
                f"--param 格式错误: {spec}，应为 name=value 或 index=value",
                "use_train_params_then_pass_param_key_value",
                {"received_param": spec},
            )
        raw_key, raw_value = spec.split("=", 1)
        raw_key = raw_key.strip()
        if not raw_key:
            raise AgentError(
                "invalid_training_param_override",
                f"--param 格式错误: {spec}，参数名或索引不能为空",
                "use_train_params_then_pass_param_key_value",
                {"received_param": spec},
            )
        param = _lookup_param(params, raw_key)
        if is_protected_param(param):
            key = parameter_key(param)
            raise AgentError(
                "protected_training_param",
                f"训练参数 {key} 由 agent workflow 管理，不能通过 --param 覆盖",
                "use_workflow_option_for_protected_param",
                {"received_param": raw_key, "param": key},
            )
        key = parameter_key(param)
        if not key:
            raise AgentError(
                "training_param_without_key",
                f"训练参数 {raw_key} 缺少 name/format，不能覆盖",
                "choose_another_parameter_or_update_model_metadata",
                {"received_param": raw_key},
            )
        if key in seen:
            raise AgentError(
                "duplicate_training_param_override",
                f"训练参数重复覆盖: {key}",
                "pass_each_training_param_once",
                {"param": key},
            )
        value = parse_training_param_value(raw_value)
        value_text = encode_training_param_value(value)
        seen.add(key)
        overrides.append(
            {
                "input": spec,
                "param": key,
                "value": value,
                "override": f"{key}={value_text}",
            }
        )
    return overrides


def resolve_training_override_from_body(
    body: dict[str, Any],
    scenario: dict[str, Any],
    param_key: str,
    value: Any,
) -> tuple[str, str]:
    """Return the actual model parameter name and CLI override string."""
    params = _parameters_from_body(body)
    candidates = scenario["training"].get(f"{param_key}_param_names") or [param_key]
    for param in params:
        for field in ("name", "format"):
            name = param.get(field)
            if name in candidates:
                return name, f"{name}={encode_training_param_value(value)}"
    raise AgentError(
        "training_param_not_found",
        f"训练 YAML 中未找到可覆盖参数 {param_key}，候选字段: {', '.join(candidates)}",
        "adjust_scenario_param_names_or_regenerate_yaml",
    )
