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
            "batch_size_param_names": ["batch_size", "batchSize"],
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
            "sub_type": "OD",
            "source": "Preset",
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
            "batch_size_param_names": ["batch_size", "batchSize"],
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
            "batch_size_param_names": ["batch_size", "batchSize"],
        },
    },
    "cv_anomaly_detection": {
        "label": "异常检测",
        "capabilities": {
            "dataset_import": True,
            "dataset_publish": True,
            "training": True,
            "edge_deploy": True,
        },
        "model_query": {
            "type": "CV",
            "sub_type": "AD",
            "source": "Preset",
        },
        "dataset": {
            "modal": "IMAGE",
            "import": {
                "content_type": "IMAGE_ANOMALY_DETECTION",
                "file_format": "IMAGE_TXT",
                "file_source": "OBS",
            },
            "publish": {
                "file_content_type": "IMAGE_ANOMALY_DETECTION",
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
            "batch_size_param_names": ["batch_size", "batchSize"],
        },
    },
    "cv_rotated_object_detection": {
        "label": "旋转框目标检测",
        "capabilities": {
            "dataset_import": True,
            "dataset_publish": True,
            "training": True,
            "edge_deploy": True,
        },
        "model_query": {
            "type": "CV",
            "sub_type": "RD",
            "source": "Preset",
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
            "batch_size_param_names": ["batch_size", "batchSize"],
        },
    },
    "cv_object_tracking": {
        "label": "目标跟踪",
        "capabilities": {
            "dataset_import": True,
            "dataset_publish": True,
            "training": True,
            "edge_deploy": True,
        },
        # The platform exposes tracking as an object-detection workflow; there
        # is no separate tracking asset subtype or dataset content type.
        "model_query": {
            "type": "CV",
            "sub_type": "OD",
            "source": "Preset",
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
            "batch_size_param_names": ["batch_size", "batchSize"],
        },
    },
}


REQUIRED_PATHS: tuple[tuple[str, ...], ...] = (
    ("label",),
    ("capabilities",),
    ("model_query", "type"),
    ("model_query", "sub_type"),
    ("model_query", "source"),
    ("dataset", "modal"),
    ("dataset", "import", "content_type"),
    ("dataset", "import", "file_format"),
    ("dataset", "publish", "file_content_type"),
    ("dataset", "publish", "publish_format"),
    ("dataset", "training_catalog"),
    ("training", "model_type"),
    ("training", "train_type"),
    ("training", "model_source_detail"),
    ("training", "create_model_source"),
    ("training", "default_batch_size"),
    ("training", "batch_size_param_names"),
)


def validate_scenario(name: str, scenario: dict[str, Any]) -> None:
    """Validate one scenario profile before agent workflows depend on it."""
    missing = []
    for path in REQUIRED_PATHS:
        current: Any = scenario
        for key in path:
            if not isinstance(current, dict) or key not in current or current[key] in (None, ""):
                missing.append(".".join(path))
                break
            current = current[key]
    names = scenario.get("training", {}).get("batch_size_param_names")
    if not isinstance(names, list) or not all(isinstance(item, str) and item for item in names):
        missing.append("training.batch_size_param_names")
    if missing:
        raise AgentError(
            "invalid_scenario_profile",
            f"场景 {name} 配置不完整: {', '.join(sorted(set(missing)))}",
            "fix_scenario_profile",
        )


def list_scenarios() -> list[dict[str, Any]]:
    """Return a compact scenario listing."""
    rows = []
    for key, value in SCENARIOS.items():
        validate_scenario(key, value)
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
    scenario = deepcopy(SCENARIOS[name])
    validate_scenario(name, scenario)
    return scenario
