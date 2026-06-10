import unittest

from pangu.agent.errors import AgentError
from pangu.agent.scenarios import get_scenario
from pangu.agent.training_params import resolve_training_override_from_body


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


if __name__ == "__main__":
    unittest.main()
