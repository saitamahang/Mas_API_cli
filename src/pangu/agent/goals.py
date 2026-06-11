"""Goal boundaries for agent-safe workflows."""

from __future__ import annotations

from typing import Any

from pangu.agent.errors import AgentError


DATASET_READY = "dataset_ready"
TRAINING_SUBMITTED = "training_submitted"
TRAINING_COMPLETED = "training_completed"
MODEL_PUBLISHED = "model_published"
DEPLOYMENT_SUBMITTED = "deployment_submitted"
SERVICE_RUNNING = "service_running"
STOP_ACTION = "stop"

GOALS = [
    DATASET_READY,
    TRAINING_SUBMITTED,
    TRAINING_COMPLETED,
    MODEL_PUBLISHED,
    DEPLOYMENT_SUBMITTED,
    SERVICE_RUNNING,
]
GOAL_ORDER = {goal: index for index, goal in enumerate(GOALS)}
DEFAULT_GOAL_BY_KIND = {
    "dataset_list": DATASET_READY,
    "dataset_import": DATASET_READY,
    "dataset_publish": DATASET_READY,
    "training": TRAINING_SUBMITTED,
    "deployment": DEPLOYMENT_SUBMITTED,
}


def default_goal_for_kind(kind: str | None) -> str:
    return DEFAULT_GOAL_BY_KIND.get(kind or "", TRAINING_SUBMITTED)


def normalize_goal(goal: str | None, default: str) -> str:
    value = (goal or default).strip()
    if value not in GOAL_ORDER:
        raise AgentError(
            "invalid_goal",
            f"不支持的 workflow goal: {value}",
            "choose_supported_goal",
            {"supported_goals": GOALS},
        )
    return value


def goal_from_state(state: dict[str, Any]) -> str:
    goal = normalize_goal(state.get("goal"), default_goal_for_kind(state.get("kind")))
    state["goal"] = goal
    return goal


def goal_reached(goal: str, milestone: str) -> bool:
    return GOAL_ORDER[milestone] >= GOAL_ORDER[goal]


def with_goal_next_action(
    state: dict[str, Any],
    payload: dict[str, Any],
    *,
    continue_action: str,
    milestone: str | None = None,
) -> dict[str, Any]:
    goal = goal_from_state(state)
    reached = bool(milestone and goal_reached(goal, milestone))
    result = dict(payload)
    result["goal"] = goal
    if milestone:
        result["milestone"] = milestone
    result["goal_reached"] = reached
    result["terminal"] = reached
    result["next_action"] = STOP_ACTION if reached else continue_action
    return result


def transient_goal_state(kind: str, goal: str | None, default: str | None = None) -> dict[str, Any]:
    return {
        "kind": kind,
        "goal": normalize_goal(goal, default or default_goal_for_kind(kind)),
    }
