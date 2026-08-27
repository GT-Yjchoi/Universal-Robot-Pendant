import unittest
import time
import threading

from PySide6.QtCore import QCoreApplication, QObject, Signal

from engine.qt_runtime import PLCSequenceRuntime
from engine.step_executor import ExecutionStatus, ExecutorState
from utils.variable_store import VariableStore


class FakePLC(QObject):
    sig_connected = Signal(bool)
    sig_monitor_data = Signal(dict)

    def __init__(self):
        super().__init__()
        self.is_connected = True
        self.submitted = []
        self._last_monitor_data = {"inputs": [0] * 4, "outputs": [0] * 4}

    def submit(self, function, *args, **kwargs):
        self.submitted.append((function, args, kwargs))

    def write_words(self, *_args):
        return True

    def send_axis_stop(self, *_args):
        return True

    def send_operation_state(self, *_args):
        return True


class VariablePublisherTests(unittest.TestCase):
    def test_check_mode_waits_for_start_and_reports_pause_state(self):
        app = QCoreApplication.instance() or QCoreApplication([])
        runtime = PLCSequenceRuntime({
            "Main": [
                {"type": "TMR", "time": 1.0},
                {"type": "END"},
            ],
            "Monitor": [],
        }, FakePLC())
        runtime._publish_timer.stop()
        runtime._monitor_restart_timer.stop()
        reports = []
        runtime.sig_monitor_data.connect(reports.append)

        runtime.start_mode(2)
        self.assertEqual(runtime.current_mode, 2)
        self.assertFalse(runtime.executor.is_running)
        self.assertEqual(reports[-1]["check_run_status"], 0)

        runtime.start_check()
        self.assertTrue(runtime.executor.is_running)
        self.assertEqual(reports[-1]["check_run_status"], 1)

        runtime.pause()
        app.processEvents()
        self.assertEqual(runtime.executor.state, ExecutorState.PAUSED)
        self.assertEqual(reports[-1]["check_run_status"], 2)

        runtime.start_check()
        app.processEvents()
        self.assertEqual(runtime.executor.state, ExecutorState.RUNNING)
        self.assertEqual(reports[-1]["check_run_status"], 1)
        runtime.close()

    def test_full_snapshot_is_payload_then_commit(self):
        plc = FakePLC()
        store = VariableStore()
        bit_id = store.add_bit("완료", True, item_id=1)
        data_id = store.add_data("횟수", -7, item_id=2)
        store.set_publish("bit", bit_id, True)
        store.set_publish("data", data_id, True, address=620)
        runtime = PLCSequenceRuntime({"Main": []}, plc, variable_store=store)
        runtime._publish_timer.stop()
        runtime._publish_variables()

        writes = [(args[1], list(args[2])) for _, args, _ in plc.submitted]
        self.assertEqual(writes[0], (504, [0b10] + [0] * 7))
        self.assertEqual(writes[1][0], 512)
        self.assertEqual(len(writes[1][1]), 200)
        self.assertEqual(writes[1][1][108:110], [0xFFF9, 0xFFFF])
        self.assertEqual(writes[-1][0], 500)
        self.assertEqual(writes[-1][1][:3], [2, 1, 0x0001])
        runtime.close()

    def test_monitor_sequence_cycles_while_main_mode_is_stopped(self):
        app = QCoreApplication.instance() or QCoreApplication([])
        plc = FakePLC()
        store = VariableStore()
        data_id = store.add_data("상시 감시 횟수", 0, item_id=0)
        runtime = PLCSequenceRuntime({
            "Main": [],
            "Monitor": [
                {"type": "DAT", "data_id": data_id, "dat_op": 1,
                 "dat_const": 1},
                {"type": "END"},
            ],
        }, plc, variable_store=store)
        runtime._publish_timer.stop()

        deadline = time.monotonic() + 0.38
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)

        self.assertEqual(runtime.current_mode, 0)
        self.assertGreaterEqual(store.get_data(data_id), 3)
        self.assertFalse(runtime.executor.is_running)
        runtime.close()

    def test_monitor_runtime_rejects_position_motion(self):
        plc = FakePLC()
        runtime = PLCSequenceRuntime({
            "Main": [],
            "Monitor": [
                {"type": "CALL", "target_seq": "MotionSub"},
            ],
            "MotionSub": [
                {"type": "POS", "point_name": "P1",
                 "active_axes": [True] * 8},
            ],
        }, plc, position_points={
            "P1": {"coords": [0.0] * 8, "speeds": [100] * 8},
        })
        runtime._publish_timer.stop()
        runtime._monitor_restart_timer.stop()
        errors = []
        runtime.sig_error.connect(errors.append)
        runtime._run_monitor_sequence()

        self.assertFalse(runtime.monitor_executor.is_running)
        self.assertIn("위치이동(POS)", errors[-1])
        self.assertIn("Monitor → MotionSub", errors[-1])
        runtime.close()

    def test_pending_timeout_decision_is_an_active_alarm_condition(self):
        app = QCoreApplication.instance() or QCoreApplication([])
        runtime = PLCSequenceRuntime({"Main": [], "Monitor": []}, FakePLC())
        runtime._publish_timer.stop()
        runtime._monitor_restart_timer.stop()
        requests = []
        runtime.sig_timeout_request.connect(requests.append)

        result = []
        worker = threading.Thread(
            target=lambda: result.append(runtime._executor_event(
                "input_timeout:continue",
                {"name": "IN_1", "timeout_alarm_no": 1},
            )),
            daemon=True,
        )
        worker.start()
        deadline = time.monotonic() + 1.0
        while not requests and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)

        self.assertTrue(requests)
        self.assertTrue(runtime._alarm_active())
        requests[0].resolve(True)
        worker.join(timeout=1.0)
        self.assertEqual(result, ["reset"])
        self.assertFalse(runtime._alarm_active())
        runtime.close()

    def test_monitor_called_sub_status_is_published_but_monitor_is_hidden(self):
        runtime = PLCSequenceRuntime({"Main": [], "Monitor": []}, FakePLC())
        runtime._publish_timer.stop()
        runtime._monitor_restart_timer.stop()
        published = []
        runtime.sig_monitor_data.connect(published.append)

        runtime._on_monitor_executor_status(ExecutionStatus(
            ExecutorState.RUNNING, "알람", 2, "JMP", execution_id=7,
        ))
        self.assertEqual(published[-1]["local_sequence"], "알람")
        self.assertEqual(published[-1]["local_execution_source"], "monitor")
        self.assertTrue(published[-1]["background_sequence"])

        count = len(published)
        runtime._on_monitor_executor_status(ExecutionStatus(
            ExecutorState.RUNNING, "Monitor", 0, "CALL", execution_id=1,
        ))
        self.assertEqual(len(published), count)
        runtime.close()


if __name__ == "__main__":
    unittest.main()
