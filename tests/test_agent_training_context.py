import unittest

from pangu.agent.errors import AgentError
from pangu.agent.training_context import expected_training_context, validate_training_context


def training_state():
    return {
        "run_id": "training_20260610_120000",
        "selection": {
            "model": {
                "asset_id": "asset-a",
                "model_id": "model-a",
                "asset_name": "detector-a",
            },
            "dataset": {
                "dataset_id": "dataset-a",
                "name": "images-a",
            },
            "pool": {
                "pool_id": "pool-a",
                "pool_name": "pool A",
            },
            "cards": 2,
        },
    }


def training_body():
    return {
        "asset_id": "asset-a",
        "model_name": "detector-a",
        "dataset_id": "dataset-a",
        "dataset_name": "images-a",
        "resource_config": {
            "pool_id": "pool-a",
            "flavor_id": "modelarts.pool.visual.2xlarge",
        },
        "task_parameter": {
            "parameters": [
                {
                    "name": "train_flavor",
                    "value": {
                        "pool_id": "pool-a",
                        "flavor_id": "modelarts.pool.visual.2xlarge",
                    },
                }
            ]
        },
    }


class AgentTrainingContextTests(unittest.TestCase):
    def test_expected_context_derives_flavor_from_cards(self):
        context = expected_training_context(training_state())

        self.assertEqual(context["resources"]["cards"], 2)
        self.assertEqual(context["resources"]["flavor_id"], "modelarts.pool.visual.2xlarge")

    def test_matching_context_passes(self):
        actual = validate_training_context(training_state(), training_body())

        self.assertEqual(actual["model"]["asset_id"], "asset-a")
        self.assertEqual(actual["pool"]["pool_id"], "pool-a")

    def test_model_mismatch_fails(self):
        body = training_body()
        body["asset_id"] = "asset-b"

        with self.assertRaises(AgentError) as cm:
            validate_training_context(training_state(), body)

        self.assertEqual(cm.exception.code, "training_context_mismatch")
        self.assertEqual(cm.exception.details["mismatches"][0]["field"], "model.asset_id")
        self.assertEqual(cm.exception.next_action, "rerun_train_scaffold")

    def test_resource_flavor_mismatch_fails(self):
        body = training_body()
        body["resource_config"]["flavor_id"] = "modelarts.pool.visual.8xlarge"

        with self.assertRaises(AgentError) as cm:
            validate_training_context(training_state(), body)

        self.assertEqual(cm.exception.code, "training_context_mismatch")
        fields = {item["field"] for item in cm.exception.details["mismatches"]}
        self.assertIn("resources.flavor_id", fields)

    def test_missing_scaffold_selection_fails(self):
        with self.assertRaises(AgentError) as cm:
            validate_training_context({}, training_body())

        self.assertEqual(cm.exception.code, "training_context_missing")


if __name__ == "__main__":
    unittest.main()
