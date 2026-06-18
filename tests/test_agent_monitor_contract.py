import unittest

from pangu.agent.monitor_contract import (
    MONITOR_ADD_ACTION,
    apply_status_monitor_contract,
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

    def test_status_monitor_contract_forces_monitor_add_for_long_goal(self):
        result = {
            "run_id": "deployment_20260618_120000",
            "goal": "service_running",
            "terminal": False,
            "next_action": "poll_deploy_status",
        }

        updated = apply_status_monitor_contract(
            result,
            run_id="deployment_20260618_120000",
            target_id="service-1",
            submitted_milestone="deployment_submitted",
        )

        self.assertEqual(updated["next_action"], MONITOR_ADD_ACTION)
        self.assertTrue(updated["monitor_required"])
        self.assertTrue(updated["monitor"]["required"])

    def test_status_monitor_contract_keeps_poll_for_submitted_goal(self):
        result = {
            "run_id": "deployment_20260618_120000",
            "goal": "deployment_submitted",
            "terminal": False,
            "next_action": "poll_deploy_status",
        }

        updated = apply_status_monitor_contract(
            result,
            run_id="deployment_20260618_120000",
            target_id="service-1",
            submitted_milestone="deployment_submitted",
        )

        self.assertEqual(updated["next_action"], "poll_deploy_status")
        self.assertFalse(updated["monitor_required"])


if __name__ == "__main__":
    unittest.main()
