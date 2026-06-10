import unittest

from pangu.agent.approval import (
    DEPLOY_SUBMIT_ACTION,
    DEPLOY_SUBMIT_CONFIRM,
    TRAIN_SUBMIT_ACTION,
    TRAIN_SUBMIT_CONFIRM,
    build_deploy_submit_summary,
    build_training_submit_summary,
    record_approval,
    require_approval,
    require_confirmation,
)
from pangu.agent.errors import AgentError


class AgentApprovalTests(unittest.TestCase):
    def test_confirmation_phrase_is_required(self):
        require_confirmation(TRAIN_SUBMIT_CONFIRM, TRAIN_SUBMIT_CONFIRM)

        with self.assertRaises(AgentError) as cm:
            require_confirmation(None, TRAIN_SUBMIT_CONFIRM)

        self.assertEqual(cm.exception.code, "approval_confirmation_required")

    def test_training_approval_is_required_and_hash_bound(self):
        state = {
            "run_id": "training_20260610_120000",
            "artifact_hash": "hash-a",
            "artifacts": {"train_yaml": "/tmp/train.yaml"},
            "selection": {"task_name": "task-a", "cards": 2},
            "validation": {"batch_size": 1},
        }

        with self.assertRaises(AgentError) as cm:
            require_approval(state, TRAIN_SUBMIT_ACTION, "hash-a")
        self.assertEqual(cm.exception.code, "approval_required")

        summary = build_training_submit_summary(state)
        record_approval(state, TRAIN_SUBMIT_ACTION, summary, "hash-a")
        approval = require_approval(state, TRAIN_SUBMIT_ACTION, "hash-a")
        self.assertEqual(approval["action"], TRAIN_SUBMIT_ACTION)

        with self.assertRaises(AgentError) as cm:
            require_approval(state, TRAIN_SUBMIT_ACTION, "hash-b")
        self.assertEqual(cm.exception.code, "approval_stale")

    def test_deploy_summary_includes_inference_choices(self):
        state = {
            "run_id": "deployment_20260610_120000",
            "workspace_id": "ws-1",
            "asset_id": "asset-1",
            "artifact_hash": "hash-a",
            "artifacts": {"deploy_yaml": "/tmp/deploy.yaml"},
            "selection": {
                "service_name": "svc-a",
                "access_mode": "ELB",
                "instances": 1,
                "deploy_option": {"index": 1, "action_type": "EDGE-DEPLOY", "arch": "ARM"},
                "pool": {"index": 2, "pool_id": "pool-1", "chip_type": "D310P"},
            },
        }

        require_confirmation(DEPLOY_SUBMIT_CONFIRM, DEPLOY_SUBMIT_CONFIRM)
        summary = build_deploy_submit_summary(state)
        approval = record_approval(state, DEPLOY_SUBMIT_ACTION, summary, "hash-a")

        self.assertEqual(summary["service_name"], "svc-a")
        self.assertEqual(summary["deploy_option"]["action_type"], "EDGE-DEPLOY")
        self.assertEqual(summary["pool"]["pool_id"], "pool-1")
        self.assertEqual(approval["artifact_hash"], "hash-a")


if __name__ == "__main__":
    unittest.main()
