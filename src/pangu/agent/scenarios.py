"""Scenario registry for agent-safe Pangu workflows."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pangu.agent.errors import AgentError


SCENARIOS: dict[str, dict[str, Any]] = {
    "cv_image_classification": {
        "label": "图像分类",
        "capabilities": {
            "dataset_import": True,
            "dataset_publish": True,
            "training": True,
            "edge_deploy": True,
        },
        "model_query": {
            "type": "CV",
            "sub_type": "IC",
            "source": "Preset",
            "asset_action": "SFT",
        },
        "dataset": {
            "modal": "IMAGE",
            "import": {
                "content_type": "IMAGE_CLASSIFICATION",
                "file_format": "IMAGE_TXT",
                "file_source": "OBS",
            },
            "publish": {
                "file_content_type": "IMAGE_CLASSIFICATION",
                "publish_format": "PANGU",
                "require_train_proportion": True,
                "default_train_proportion": 0.8,
            },
            "training_catalog": "PUBLISH",
        },
        "training": {
            "model_type": "CV",
            "train_type": "SFT",
            "model_source_detail": "SYSTEM",
            "create_model_source": "pangu",
            "default_batch_size": 1,
        },
    },
    "cv_object_detection": {
        "label": "物体检测",
        "capabilities": {
            "dataset_import": True,
            "dataset_publish": True,
            "training": True,
            "edge_deploy": True,
        },
        "model_query": {
            "type": "CV",
            "sub_type": "ObjectDetection",
            "source": "Preset",
            "asset_action": "SFT",
        },
        "dataset": {
            "modal": "IMAGE",
            "import": {
                "content_type": "IMAGE_OBJECT_DETECTION",
                "file_format": "PASCAL",
                "file_source": "OBS",
            },
            "publish": {
                "file_content_type": "IMAGE_OBJECT_DETECTION",
                "publish_format": "PANGU",
                "require_train_proportion": True,
                "default_train_proportion": 0.8,
            },
            "training_catalog": "PUBLISH",
        },
        "training": {
            "model_type": "CV",
            "train_type": "SFT",
            "model_source_detail": "SYSTEM",
            "create_model_source": "pangu",
            "default_batch_size": 1,
        },
    },
    "cv_semantic_segmentation": {
        "label": "语义分割",
        "capabilities": {
            "dataset_import": True,
            "dataset_publish": True,
            "training": True,
            "edge_deploy": True,
        },
        "model_query": {
            "type": "CV",
            "sub_type": "SS",
            "source": "Preset",
            "asset_action": "SFT",
        },
        "dataset": {
            "modal": "IMAGE",
            "import": {
                "content_type": "IMAGE_SEMANTIC_SEGMENTATION",
                "file_format": "IMAGE_PNG",
                "file_source": "OBS",
            },
            "publish": {
                "file_content_type": "IMAGE_SEMANTIC_SEGMENTATION",
                "publish_format": "PANGU",
                "require_train_proportion": True,
                "default_train_proportion": 0.8,
            },
            "training_catalog": "PUBLISH",
        },
        "training": {
            "model_type": "CV",
            "train_type": "SFT",
            "model_source_detail": "SYSTEM",
            "create_model_source": "pangu",
            "default_batch_size": 1,
        },
    },
}


def list_scenarios() -> list[dict[str, Any]]:
    """Return a compact scenario listing."""
    rows = []
    for key, value in SCENARIOS.items():
        rows.append({
            "scenario": key,
            "label": value["label"],
            "capabilities": value.get("capabilities", {}),
        })
    return rows


def get_scenario(name: str) -> dict[str, Any]:
    """Return a deep copy so callers can safely mutate local values."""
    if name not in SCENARIOS:
        raise AgentError(
            "unsupported_scenario",
            f"不支持的场景: {name}",
            "run_scenarios_or_add_profile",
        )
    return deepcopy(SCENARIOS[name])

