import unittest
import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory


config_stub = types.ModuleType("pangu.config")
config_stub.CONFIG_DIR = Path("/tmp/pangu-agent-monitor-tests")
sys.modules.setdefault("pangu.config", config_stub)

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda _text: {}
yaml_stub.safe_dump = lambda data, **_kwargs: str(data)
sys.modules.setdefault("yaml", yaml_stub)

from pangu.agent import state as state_mod
from pangu.agent_monitor import store as store_mod
from pangu.agent_monitor.adapters.base import AdapterDeliveryError, AgentAdapter
from pangu.agent_monitor.adapters import create_adapter
from pangu.agent_monitor.models import DELIVERY_DELIVERED, DELIVERY_FAILED, MonitorTask
from pangu.agent_monitor.runner import decode_process_output, run_monitor
from pangu.agent_monitor.status import classify_status, monitor_task_from_run
from pangu.agent_monitor.store import save_monitor


class FakeAdapter(AgentAdapter):
    name = "fake"

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def send_message(self, session, message, payload):
        self.calls.append((session, message, payload))
        if self.fail:
            raise AdapterDeliveryError("client unavailable")


class AgentMonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old_runs_dir = state_mod.RUNS_DIR
        self.old_monitors_dir = store_mod.MONITORS_DIR
        self.old_dead_letters_dir = store_mod.DEAD_LETTERS_DIR
        state_mod.RUNS_DIR = root / "runs"
        store_mod.MONITORS_DIR = root / "monitors"
        store_mod.DEAD_LETTERS_DIR = root / "dead_letters"

    def tearDown(self):
        state_mod.RUNS_DIR = self.old_runs_dir
        store_mod.MONITORS_DIR = self.old_monitors_dir
        store_mod.DEAD_LETTERS_DIR = self.old_dead_letters_dir
        self.tmp.cleanup()

    def test_monitor_task_from_training_run_uses_submit_result(self):
        state_mod.save_state(
            {
                "run_id": "training_20260617_120000",
                "kind": "training",
                "goal": "training_completed",
                "workspace_id": "ws-1",
                "submit_result": {"task_id": "task-1"},
            }
        )

        task = monitor_task_from_run(
            run_id="training_20260617_120000",
            adapter="fake",
            session={"session_id": "sess-1"},
        )

        self.assertEqual(task.kind, "training")
        self.assertEqual(task.target_id, "task-1")
        self.assertEqual(task.session["session_id"], "sess-1")
        self.assertEqual(
            task.status_command,
            [
                "pangu-agent",
                "train",
                "status",
                "--run-id",
                "training_20260617_120000",
                "--task-id",
                "task-1",
                "--json",
            ],
        )

    def test_codeagent_adapter_name_is_registered(self):
        adapter = create_adapter("codeagent")

        self.assertEqual(adapter.name, "codeagent")

    def test_decode_process_output_prefers_utf8(self):
        text = '{"ok": true, "message": "训练任务已完成"}'

        self.assertEqual(decode_process_output(text.encode("utf-8")), text)

    def test_decode_process_output_replaces_invalid_bytes(self):
        text = decode_process_output(b'{"ok": true, "message": "\xff"}')

        self.assertIn('"ok": true', text)

    def test_monitor_task_from_deployment_run_uses_submit_result(self):
        state_mod.save_state(
            {
                "run_id": "deployment_20260617_120000",
                "kind": "deployment",
                "goal": "service_running",
                "workspace_id": "ws-1",
                "submit_result": {"service_id": "service-1"},
            }
        )

        task = monitor_task_from_run(
            run_id="deployment_20260617_120000",
            adapter="fake",
            session={"session_id": "sess-1"},
        )

        self.assertEqual(task.kind, "deployment")
        self.assertEqual(task.target_id, "service-1")
        self.assertIn("deploy", task.status_command)
        self.assertIn("--service-id", task.status_command)

    def test_classify_status_terminal_values(self):
        self.assertEqual(classify_status("training", {"task_status": "completed"}), (True, True, "completed"))
        self.assertEqual(classify_status("training", {"task_status": "failed"}), (True, False, "failed"))
        self.assertEqual(classify_status("deployment", {"service_status": "running"}), (True, True, "running"))
        self.assertEqual(classify_status("deployment", {"service_status": "deploying"}), (False, False, "deploying"))

    def test_run_monitor_delivers_when_terminal_success(self):
        task = MonitorTask(
            monitor_id="monitor_training_20260617_120000",
            kind="training",
            run_id="training_20260617_120000",
            target_id="task-1",
            status_command=["status"],
            adapter="fake",
            session={"session_id": "sess-1"},
            success_message="训练任务已完成，请继续下一步。",
            failure_message="训练任务已结束但未成功，请检查失败原因。",
            interval_seconds=1,
        )
        save_monitor(task)
        adapter = FakeAdapter()
        payloads = iter([{"task_status": "running"}, {"task_status": "completed", "next_action": "next"}])

        result = run_monitor(
            task.monitor_id,
            status_runner=lambda _cmd: next(payloads),
            adapter_factory=lambda _name: adapter,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(result.delivery_status, DELIVERY_DELIVERED)
        self.assertEqual(result.terminal_status, "completed")
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(adapter.calls[0][0]["session_id"], "sess-1")
        self.assertIn("训练任务已完成", adapter.calls[0][1])

    def test_run_monitor_writes_dead_letter_when_delivery_fails(self):
        task = MonitorTask(
            monitor_id="monitor_training_20260617_130000",
            kind="training",
            run_id="training_20260617_130000",
            target_id="task-1",
            status_command=["status"],
            adapter="fake",
            session={"session_id": "sess-1"},
            success_message="训练任务已完成，请继续下一步。",
            failure_message="训练任务已结束但未成功，请检查失败原因。",
            max_delivery_attempts=2,
        )
        save_monitor(task)

        result = run_monitor(
            task.monitor_id,
            status_runner=lambda _cmd: {"task_status": "completed"},
            adapter_factory=lambda _name: FakeAdapter(fail=True),
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(result.delivery_status, DELIVERY_FAILED)
        self.assertTrue(result.dead_letter_path)
        self.assertTrue(Path(result.dead_letter_path).exists())


if __name__ == "__main__":
    unittest.main()
