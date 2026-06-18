import unittest

from pangu.agent.monitor_contract import (
    MONITOR_ADD_ACTION,
    apply_submit_monitor_contract,
    monitor_submit_fields,
)


class AgentMonitorContractTests(unittest.TestCase):
    def test_submit_monitor_contract_keeps_stop_when_goal_reached(self):
        result = {
            "run_id": "deployment_20260618_120000",
            "terminal": True,
            "next_action": "stop",
            **monitor_submit_fields("deployment_20260618_120000", "service-1"),
        }

        updated = apply_submit_monitor_contract(result)

        self.assertEqual(updated["next_action"], "stop")
        self.assertFalse(updated["monitor_required"])
        self.assertFalse(updated["monitor"]["required"])

    def test_submit_monitor_contract_forces_monitor_add_when_goal_not_reached(self):
        result = {
            "run_id": "training_20260618_120000",
            "terminal": False,
            "next_action": "train.status",
            **monitor_submit_fields("training_20260618_120000", "task-1"),
        }

        updated = apply_submit_monitor_contract(result)

        self.assertEqual(updated["next_action"], MONITOR_ADD_ACTION)
        self.assertTrue(updated["monitor_required"])
        self.assertTrue(updated["monitor"]["required"])
        self.assertIn("--detach --json", updated["monitor_add_template"])


if __name__ == "__main__":
    unittest.main()
