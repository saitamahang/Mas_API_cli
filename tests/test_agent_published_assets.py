import unittest

from pangu.agent.published_assets import (
    PUBLISHED_ASSET_SOURCE,
    flatten_asset_ext,
    published_asset_query,
    select_published_asset,
)


class PublishedAssetTests(unittest.TestCase):
    def test_flatten_asset_ext_keeps_asset_and_model_ids(self):
        row = flatten_asset_ext({
            "modelAsset": {"asset_id": "asset-a", "asset_name": "model-a"},
            "model_id": "train-model-a",
            "can_deploy": True,
        })

        self.assertEqual(row["asset_id"], "asset-a")
        self.assertEqual(row["model_id"], "train-model-a")
        self.assertTrue(row["can_deploy"])

    def test_select_published_asset_prefers_model_id_and_name_match(self):
        assets = [
            {"asset_id": "asset-a", "asset_name": "same-name", "model_id": "model-old"},
            {"asset_id": "asset-b", "asset_name": "same-name", "model_id": "model-new"},
        ]

        selected = select_published_asset(assets, model_id="model-new", asset_name="same-name")

        self.assertEqual(selected["asset_id"], "asset-b")

    def test_select_published_asset_does_not_guess_ambiguous_name(self):
        assets = [
            {"asset_id": "asset-a", "asset_name": "same-name"},
            {"asset_id": "asset-b", "asset_name": "same-name"},
        ]

        self.assertIsNone(select_published_asset(assets, asset_name="same-name"))

    def test_published_asset_query_uses_asset_source_not_model_id(self):
        query = published_asset_query("model-a")

        self.assertEqual(query["asset_source"], PUBLISHED_ASSET_SOURCE)
        self.assertEqual(query["asset_name"], "model-a")
        self.assertEqual(query["workspace_source"], "current")
        self.assertNotIn("model_id", query)


if __name__ == "__main__":
    unittest.main()
