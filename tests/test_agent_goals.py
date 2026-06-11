import unittest

from pangu.agent.errors import AgentError
from pangu.agent.goals import (
    DATASET_READY,
    MODEL_PUBLISHED,
    SERVICE_RUNNING,
    TRAINING_COMPLETED,
    TRAINING_SUBMITTED,
    default_goal_for_kind,
    normalize_goal,
    with_goal_next_action,
)


class AgentGoalTests(unittest.TestCase):
    def test_default_goal_by_workflow_kind(self):
        self.assertEqual(default_goal_for_kind("dataset_publish"), DATASET_READY)
        self.assertEqual(default_goal_for_kind("training"), TRAINING_SUBMITTED)

    def test_invalid_goal_is_rejected(self):
        with self.assertRaises(AgentError) as cm:
            normalize_goal("auto_deploy_everything", TRAINING_SUBMITTED)

        self.assertEqual(cm.exception.code, "invalid_goal")
        self.assertIn(TRAINING_SUBMITTED, cm.exception.details["supported_goals"])

    def test_reached_goal_stops_next_action(self):
        result = with_goal_next_action(
            {"kind": "training", "goal": TRAINING_SUBMITTED},
            {"run_id": "training_20260610_120000"},
            milestone=TRAINING_SUBMITTED,
            continue_action="train.status",
        )

        self.assertTrue(result["goal_reached"])
        self.assertTrue(result["terminal"])
        self.assertEqual(result["next_action"], "stop")

    def test_farther_goal_allows_continue_action(self):
        result = with_goal_next_action(
            {"kind": "training", "goal": MODEL_PUBLISHED},
            {"run_id": "training_20260610_120000"},
            milestone=TRAINING_COMPLETED,
            continue_action="train.publish_if_user_wants",
        )

        self.assertFalse(result["goal_reached"])
        self.assertFalse(result["terminal"])
        self.assertEqual(result["next_action"], "train.publish_if_user_wants")

    def test_service_running_reaches_all_prior_goals(self):
        result = with_goal_next_action(
            {"kind": "deployment", "goal": MODEL_PUBLISHED},
            {"service": {"status": "running"}},
            milestone=SERVICE_RUNNING,
            continue_action="poll_deploy_status",
        )

        self.assertTrue(result["goal_reached"])
        self.assertEqual(result["next_action"], "stop")


if __name__ == "__main__":
    unittest.main()
