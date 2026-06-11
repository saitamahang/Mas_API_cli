import unittest

from pangu.agent.errors import AgentError
from pangu.agent.scenarios import get_scenario
from pangu.agent.training_params import (
    list_training_parameters_from_body,
    resolve_training_override_from_body,
    resolve_training_param_overrides_from_body,
)


class AgentTrainingParamTests(unittest.TestCase):
    def test_resolves_batch_size_by_name(self):
        scenario = get_scenario("cv_image_classification")
        body = {"task_parameter": {"parameters": [{"name": "batch_size", "value": 2}]}}

        name, override = resolve_training_override_from_body(body, scenario, "batch_size", 4)

        self.assertEqual(name, "batch_size")
        self.assertEqual(override, "batch_size=4")

    def test_resolves_batch_size_by_format_alias(self):
        scenario = get_scenario("cv_image_classification")
        body = {"task_parameter": {"parameters": [{"format": "batchSize", "value": 2}]}}

        name, override = resolve_training_override_from_body(body, scenario, "batch_size", 1)

        self.assertEqual(name, "batchSize")
        self.assertEqual(override, "batchSize=1")

    def test_missing_batch_size_fails_before_submit(self):
        scenario = get_scenario("cv_image_classification")
        body = {"task_parameter": {"parameters": [{"name": "learning_rate", "value": 0.1}]}}

        with self.assertRaises(AgentError) as cm:
            resolve_training_override_from_body(body, scenario, "batch_size", 1)

        self.assertEqual(cm.exception.code, "training_param_not_found")
        self.assertEqual(cm.exception.next_action, "adjust_scenario_param_names_or_regenerate_yaml")

    def test_lists_training_parameters_with_indexes(self):
        body = {
            "task_parameter": {
                "parameters": [
                    {"name": "learning_rate", "value": 0.1, "default": 0.01, "type": "number"},
                    {"name": "train_flavor", "value": {"pool_id": "pool-a"}},
                ]
            }
        }

        params = list_training_parameters_from_body(body)

        self.assertEqual(params[0]["index"], 1)
        self.assertEqual(params[0]["key"], "learning_rate")
        self.assertTrue(params[0]["editable"])
        self.assertFalse(params[1]["editable"])

    def test_resolves_param_override_by_index_and_type(self):
        body = {
            "task_parameter": {
                "parameters": [
                    {"name": "learning_rate", "value": 0.1},
                    {"format": "use_aug", "value": False},
                ]
            }
        }

        overrides = resolve_training_param_overrides_from_body(body, ["1=0.001", "use_aug=true"])

        self.assertEqual(overrides[0]["param"], "learning_rate")
        self.assertEqual(overrides[0]["value"], 0.001)
        self.assertEqual(overrides[0]["override"], "learning_rate=0.001")
        self.assertEqual(overrides[1]["param"], "use_aug")
        self.assertIs(overrides[1]["value"], True)
        self.assertEqual(overrides[1]["override"], "use_aug=true")

    def test_unknown_param_override_fails(self):
        body = {"task_parameter": {"parameters": [{"name": "learning_rate", "value": 0.1}]}}

        with self.assertRaises(AgentError) as cm:
            resolve_training_param_overrides_from_body(body, ["epochs=20"])

        self.assertEqual(cm.exception.code, "training_param_not_found")

    def test_protected_param_override_fails(self):
        body = {"task_parameter": {"parameters": [{"name": "train_flavor", "value": {"pool_id": "pool-a"}}]}}

        with self.assertRaises(AgentError) as cm:
            resolve_training_param_overrides_from_body(body, ["1={\"pool_id\":\"pool-b\"}"])

        self.assertEqual(cm.exception.code, "protected_training_param")

    def test_duplicate_param_override_fails(self):
        body = {"task_parameter": {"parameters": [{"name": "learning_rate", "value": 0.1}]}}

        with self.assertRaises(AgentError) as cm:
            resolve_training_param_overrides_from_body(body, ["learning_rate=0.1", "1=0.2"])

        self.assertEqual(cm.exception.code, "duplicate_training_param_override")


if __name__ == "__main__":
    unittest.main()
