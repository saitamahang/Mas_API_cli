import unittest

from pangu.agent.datasets import (
    extract_job_id,
    find_matching_dataset,
    validate_training_dataset_ready,
)
from pangu.agent.errors import AgentError
from pangu.agent.scenarios import get_scenario


class AgentDatasetTests(unittest.TestCase):
    def test_ready_training_dataset_passes(self):
        scenario = get_scenario("cv_image_classification")
        row = {
            "id": "ds-a",
            "name": "images-a",
            "catalog": "PUBLISH",
            "status": "ONLINE",
            "content_type": "IMAGE_CLASSIFICATION",
        }

        result = validate_training_dataset_ready(row, scenario)

        self.assertEqual(result["id"], "ds-a")

    def test_offline_training_dataset_fails(self):
        scenario = get_scenario("cv_image_classification")
        row = {
            "id": "ds-a",
            "name": "images-a",
            "catalog": "PUBLISH",
            "status": "OFFLINE",
            "content_type": "IMAGE_CLASSIFICATION",
        }

        with self.assertRaises(AgentError) as cm:
            validate_training_dataset_ready(row, scenario)

        self.assertEqual(cm.exception.code, "dataset_not_ready_for_training")
        self.assertEqual(cm.exception.details["mismatches"][0]["field"], "status")

    def test_wrong_content_type_fails(self):
        scenario = get_scenario("cv_object_detection")
        row = {
            "id": "ds-a",
            "name": "images-a",
            "catalog": "PUBLISH",
            "status": "ONLINE",
            "content_type": "IMAGE_CLASSIFICATION",
        }

        with self.assertRaises(AgentError) as cm:
            validate_training_dataset_ready(row, scenario)

        fields = {item["field"] for item in cm.exception.details["mismatches"]}
        self.assertIn("content_type", fields)

    def test_find_matching_dataset_by_id_or_name(self):
        rows = [
            {"id": "ds-a", "name": "images-a"},
            {"dataset_id": "ds-b", "name": "images-b"},
        ]

        self.assertEqual(find_matching_dataset(rows, dataset_id="ds-b")["name"], "images-b")
        self.assertEqual(find_matching_dataset(rows, name="images-a")["id"], "ds-a")
        self.assertIsNone(find_matching_dataset(rows, dataset_id="missing"))

    def test_extract_job_id_accepts_id_or_job_id(self):
        self.assertEqual(extract_job_id({"id": "job-a"}), "job-a")
        self.assertEqual(extract_job_id({"job_id": "job-b"}), "job-b")
        self.assertEqual(extract_job_id({}), "")


if __name__ == "__main__":
    unittest.main()
