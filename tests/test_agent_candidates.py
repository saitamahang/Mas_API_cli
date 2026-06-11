import unittest

from pangu.agent.candidates import MAX_PAGE_SIZE, candidate_page, normalize_page_size, page_metadata
from pangu.agent.errors import AgentError


class AgentCandidateTests(unittest.TestCase):
    def test_candidate_page_returns_compact_rows_with_stable_indexes(self):
        rows = [
            {
                "index": 1,
                "name": "dataset-a",
                "dataset_id": "ds-a",
                "catalog": "PUBLISH",
                "content_type": "IMAGE_CLASSIFICATION",
                "sample_path": "obs://very/long/path/that/should/not/be/returned",
            },
            {"index": 2, "name": "dataset-b", "dataset_id": "ds-b", "catalog": "PUBLISH"},
            {"index": 3, "name": "dataset-c", "dataset_id": "ds-c", "catalog": "PUBLISH"},
        ]

        page = candidate_page("datasets", rows, page=1, page_size=2)

        self.assertEqual(page["total"], 3)
        self.assertEqual(page["total_pages"], 2)
        self.assertTrue(page["has_more"])
        self.assertEqual([row["index"] for row in page["datasets"]], [1, 2])
        self.assertNotIn("sample_path", page["datasets"][0])

    def test_page_metadata_excludes_items(self):
        rows = [{"index": 1, "pool_id": "pool-a"}]

        meta = page_metadata("pools", rows, page=1, page_size=20)

        self.assertEqual(meta["kind"], "pools")
        self.assertEqual(meta["total"], 1)
        self.assertNotIn("pools", meta)

    def test_model_page_includes_asset_description(self):
        rows = [
            {
                "index": 1,
                "asset_name": "model-a",
                "asset_id": "asset-a",
                "asset_desc": "image classification model",
            }
        ]

        page = candidate_page("models", rows, page=1, page_size=20)

        self.assertEqual(page["models"][0]["asset_desc"], "image classification model")

    def test_invalid_page_fails(self):
        with self.assertRaises(AgentError) as cm:
            candidate_page("datasets", [{"index": 1}], page=2, page_size=20)

        self.assertEqual(cm.exception.code, "invalid_page")

    def test_page_size_is_capped(self):
        self.assertEqual(normalize_page_size(500), MAX_PAGE_SIZE)


if __name__ == "__main__":
    unittest.main()
