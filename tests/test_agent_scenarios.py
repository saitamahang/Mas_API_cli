import unittest

from pangu.agent.errors import AgentError
from pangu.agent.scenarios import get_scenario, list_scenarios, validate_scenario


class AgentScenarioTests(unittest.TestCase):
    def test_builtin_scenarios_are_valid(self):
        scenarios = list_scenarios()

        self.assertGreaterEqual(len(scenarios), 3)
        self.assertIn("cv_image_classification", {row["scenario"] for row in scenarios})

    def test_invalid_scenario_profile_reports_missing_paths(self):
        scenario = get_scenario("cv_image_classification")
        del scenario["training"]["batch_size_param_names"]

        with self.assertRaises(AgentError) as cm:
            validate_scenario("broken", scenario)

        self.assertEqual(cm.exception.code, "invalid_scenario_profile")
        self.assertEqual(cm.exception.next_action, "fix_scenario_profile")


if __name__ == "__main__":
    unittest.main()
