import importlib
import os
import stat
import sys
import time
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pangu.agent.errors import AgentError


def load_state_module(config_dir: Path):
    sys.modules.pop("pangu.agent.state", None)

    config = types.ModuleType("pangu.config")
    config.CONFIG_DIR = config_dir
    sys.modules["pangu.config"] = config

    yaml = types.ModuleType("yaml")
    yaml.safe_load = lambda _text: {}
    sys.modules.setdefault("yaml", yaml)

    return importlib.import_module("pangu.agent.state")


class AgentStateTests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("pangu.agent.state", None)
        sys.modules.pop("pangu.config", None)

    def test_run_path_rejects_path_like_ids(self):
        with TemporaryDirectory() as tmp:
            state = load_state_module(Path(tmp))

            for run_id in ("../x", "train/x", "train\\x", "x.y", ""):
                with self.subTest(run_id=run_id):
                    with self.assertRaises(AgentError):
                        state.run_path(run_id)

            self.assertEqual(
                state.run_path("training_20260610_120000").name,
                "training_20260610_120000.json",
            )

    def test_save_state_uses_private_permissions_and_gc_deletes_old_expired_runs(self):
        with TemporaryDirectory() as tmp:
            state = load_state_module(Path(tmp))
            run_id = "training_20260610_120000"
            expired_at = (state.now_utc() - state.timedelta(hours=48)).isoformat()

            state.save_state({"run_id": run_id, "expires_at": expired_at})
            path = state.run_path(run_id)
            old = time.time() - 25 * 3600
            os.utime(path, (old, old))

            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

            result = state.gc_runs(max_age_hours=24)

            self.assertIn(path.name, result["deleted"])
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
