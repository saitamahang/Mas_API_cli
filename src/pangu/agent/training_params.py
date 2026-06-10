"""Training parameter helpers for agent-safe workflows."""

from __future__ import annotations

from typing import Any

from pangu.agent.errors import AgentError


def resolve_training_override_from_body(
    body: dict[str, Any],
    scenario: dict[str, Any],
    param_key: str,
    value: Any,
) -> tuple[str, str]:
    """Return the actual model parameter name and CLI override string."""
    params = (body.get("task_parameter") or {}).get("parameters") or []
    candidates = scenario["training"].get(f"{param_key}_param_names") or [param_key]
    for param in params:
        if not isinstance(param, dict):
            continue
        for field in ("name", "format"):
            name = param.get(field)
            if name in candidates:
                return name, f"{name}={value}"
    raise AgentError(
        "training_param_not_found",
        f"训练 YAML 中未找到可覆盖参数 {param_key}，候选字段: {', '.join(candidates)}",
        "adjust_scenario_param_names_or_regenerate_yaml",
    )
