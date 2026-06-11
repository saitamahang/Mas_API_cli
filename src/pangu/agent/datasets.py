"""Dataset readiness helpers for agent-safe workflows."""

from __future__ import annotations

from typing import Any

from pangu.agent.errors import AgentError


READY_DATASET_STATUS = "ONLINE"
DATASET_JOB_FAILURE_STATUSES = ["FAILED", "STOPPED"]


def dataset_identifier(row: dict[str, Any]) -> str:
    return str(row.get("dataset_id") or row.get("id") or "")


def expected_training_content_type(scenario: dict[str, Any]) -> str:
    dataset = scenario["dataset"]
    return str(dataset.get("publish", {}).get("file_content_type") or "")


def extract_job_id(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    return str(data.get("id") or data.get("job_id") or "")


def validate_training_dataset_ready(row: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    dataset = scenario["dataset"]
    expected_catalog = dataset["training_catalog"]
    expected_content_type = expected_training_content_type(scenario)
    mismatches: list[dict[str, Any]] = []

    actual_id = dataset_identifier(row)
    if not actual_id:
        mismatches.append({"field": "dataset_id", "expected": "non_empty", "actual": ""})

    actual_catalog = row.get("catalog")
    if actual_catalog != expected_catalog:
        mismatches.append({"field": "catalog", "expected": expected_catalog, "actual": actual_catalog})

    actual_status = row.get("status")
    if actual_status != READY_DATASET_STATUS:
        mismatches.append({"field": "status", "expected": READY_DATASET_STATUS, "actual": actual_status})

    actual_content_type = row.get("content_type")
    if actual_content_type and actual_content_type != expected_content_type:
        mismatches.append({
            "field": "content_type",
            "expected": expected_content_type,
            "actual": actual_content_type,
        })

    if mismatches:
        raise AgentError(
            "dataset_not_ready_for_training",
            "数据集不是可训练的已发布 ONLINE 数据集",
            "dataset.publish-wait_or_choose_ready_dataset",
            {
                "mismatches": mismatches,
                "dataset": {
                    "id": actual_id,
                    "name": row.get("name"),
                    "catalog": actual_catalog,
                    "status": actual_status,
                    "content_type": actual_content_type,
                },
            },
        )
    return row


def find_matching_dataset(
    rows: list[dict[str, Any]],
    *,
    dataset_id: str = "",
    name: str = "",
) -> dict[str, Any] | None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        if dataset_id and dataset_identifier(row) == dataset_id:
            return row
        if name and row.get("name") == name:
            return row
    return None
