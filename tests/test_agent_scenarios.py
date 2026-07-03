import unittest

from pangu.agent.errors import AgentError
from pangu.agent.scenarios import get_scenario, list_scenarios, validate_scenario


class AgentScenarioTests(unittest.TestCase):
    def test_builtin_scenarios_are_valid(self):
        scenarios = list_scenarios()

        expected = {
            "cv_image_classification",
            "cv_object_detection",
            "cv_semantic_segmentation",
            "cv_anomaly_detection",
            "cv_rotated_object_detection",
            "cv_object_tracking",
        }
        self.assertEqual(expected, {row["scenario"] for row in scenarios})
        self.assertTrue(all(row["capabilities"]["training"] for row in scenarios))

    def test_object_detection_uses_od_sub_type(self):
        scenario = get_scenario("cv_object_detection")

        self.assertEqual(scenario["model_query"]["sub_type"], "OD")

    def test_new_cv_scenario_profiles_use_expected_model_and_dataset_types(self):
        cases = {
            "cv_anomaly_detection": ("AD", "IMAGE_ANOMALY_DETECTION", "IMAGE_TXT"),
            "cv_rotated_object_detection": ("RD", "IMAGE_OBJECT_DETECTION", "PASCAL"),
            "cv_object_tracking": ("OD", "IMAGE_OBJECT_DETECTION", "PASCAL"),
        }

        for name, (sub_type, content_type, file_format) in cases.items():
            with self.subTest(name=name):
                scenario = get_scenario(name)
                self.assertEqual(scenario["model_query"]["sub_type"], sub_type)
                self.assertEqual(scenario["dataset"]["import"]["content_type"], content_type)
                self.assertEqual(scenario["dataset"]["import"]["file_format"], file_format)

    def test_invalid_scenario_profile_reports_missing_paths(self):
        scenario = get_scenario("cv_image_classification")
        del scenario["training"]["batch_size_param_names"]

        with self.assertRaises(AgentError) as cm:
            validate_scenario("broken", scenario)

        self.assertEqual(cm.exception.code, "invalid_scenario_profile")
        self.assertEqual(cm.exception.next_action, "fix_scenario_profile")


if __name__ == "__main__":
    unittest.main()
