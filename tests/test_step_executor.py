import threading
import time
import unittest

from engine.step_executor import ExecutorState, SequenceExecutor, UnsupportedStepError
from engine.control_backend import SignalGroup


class FakeDIO:
    input_count = output_count = 8

    def __init__(self):
        self.inputs = 0
        self.outputs = 0
        self.closed = False

    def read_inputs(self): return self.inputs
    def read_outputs(self): return self.outputs
    def write_output(self, channel, enabled):
        if enabled: self.outputs |= 1 << channel
        else: self.outputs &= ~(1 << channel)
    def all_outputs_off(self): self.outputs = 0
    def close(self): self.closed = True


class FakeMachine(FakeDIO):
    def __init__(self):
        super().__init__()
        self.moves = []
        self.typed_inputs = {(SignalGroup.SYSTEM_IO, 3): True,
                             (SignalGroup.VALVE_IO, 2): True}

    def move(self, step): self.moves.append(dict(step))
    def read_input(self, group, index): return self.typed_inputs.get((group, index), False)
    def write_output(self, group, index, enabled, pulse_ms=0): pass
    def snapshot(self): return self.inputs, self.outputs


class SequenceExecutorTests(unittest.TestCase):
    def wait_done(self, engine, timeout=1):
        deadline = time.monotonic() + timeout
        while engine.is_running and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(engine.is_running)

    def test_out_timer_and_end(self):
        io = FakeDIO()
        engine = SequenceExecutor(io, poll_interval=0.001, safe_off_on_stop=False)
        engine.start({"Main": [
            {"type": "OUT", "dio_channel": 2, "on": True},
            {"type": "TMR", "time": 0.01},
            {"type": "OUT", "dio_channel": 2, "on": False},
            {"type": "END"},
        ]})
        self.wait_done(engine)
        self.assertEqual(io.outputs, 0)
        self.assertEqual(engine.state, ExecutorState.IDLE)

    def test_wait_input(self):
        io = FakeDIO()
        engine = SequenceExecutor(io, poll_interval=0.001, safe_off_on_stop=False)
        engine.start({"Main": [{"type": "IN", "dio_channel": 7, "on": True}, {"type": "END"}]})
        threading.Timer(0.02, lambda: setattr(io, "inputs", 1 << 7)).start()
        self.wait_done(engine)
        self.assertEqual(engine.state, ExecutorState.IDLE)

    def test_call(self):
        io = FakeDIO()
        engine = SequenceExecutor(io, poll_interval=0.001, safe_off_on_stop=False)
        engine.start({
            "Main": [{"type": "CALL", "target_seq": "Sub"}, {"type": "END"}],
            "Sub": [{"type": "OUT", "dio_channel": 1, "on": True}, {"type": "END"}],
        })
        self.wait_done(engine)
        self.assertEqual(io.outputs, 2)

    def test_unsupported_pos_fails_and_safe_off(self):
        io = FakeDIO(); io.outputs = 0xFF
        engine = SequenceExecutor(io, poll_interval=0.001)
        engine.start({"Main": [{"type": "POS", "coords": [0] * 8,
                                "active_axes": [True] * 8}]})
        self.wait_done(engine)
        self.assertEqual(engine.state, ExecutorState.ERROR)
        self.assertIn("POS", engine.last_error)
        self.assertEqual(io.outputs, 0)

    def test_internal_bits_and_dat_are_executed_on_pendant(self):
        io = FakeDIO()
        engine = SequenceExecutor(io, poll_interval=0.001, safe_off_on_stop=False)
        engine.start({"Main": [
            {"type": "OUT", "out_type": 2, "port": 4, "on": True},
            {"type": "IN", "in_type": 2, "port": 104, "on": True},
            {"type": "DAT", "dt_addr": 60000, "operation": 0, "value": 7},
            {"type": "DAT", "dt_addr": 60000, "operation": 1, "value": 5},
            {"type": "END"},
        ]})
        self.wait_done(engine)
        self.assertEqual(engine._data_words[60000], 12)

    def test_parallel_call_runs_without_blocking_caller(self):
        io = FakeDIO()
        engine = SequenceExecutor(io, poll_interval=0.001, safe_off_on_stop=False)
        engine.start({
            "Main": [{"type": "CALL", "target_seq": "Sub", "parallel": True},
                     {"type": "OUT", "dio_channel": 0, "on": True}, {"type": "END"}],
            "Sub": [{"type": "TMR", "time": 0.01},
                    {"type": "OUT", "dio_channel": 1, "on": True}, {"type": "END"}],
        })
        self.wait_done(engine)
        self.assertEqual(io.outputs, 0b11)

    def test_recipe_position_is_resolved_from_point_library(self):
        io = FakeMachine()
        engine = SequenceExecutor(
            io, poll_interval=0.001, safe_off_on_stop=False,
            position_points={"Pick": {"coords": [1, 2, 3, 4, 5, 6, 7, 8],
                                      "speeds": [10] * 8}},
        )
        engine.start({"Main": [
            {"type": "POS", "point_name": "Pick",
             "active_axes": [True, False, False, False, False, False, False, False]},
            {"type": "END"},
        ]})
        self.wait_done(engine)
        self.assertEqual(io.moves[0]["coords"], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(io.moves[0]["active_axes"], [True, False, False, False, False, False, False, False])

    def test_position_transform_runs_after_point_resolution(self):
        io = FakeMachine()
        def offset(step):
            result = dict(step); result["coords"] = list(result["coords"])
            result["coords"][0] += 20
            return result
        engine = SequenceExecutor(
            io, poll_interval=0.001, safe_off_on_stop=False,
            position_points={"Base": {"coords": [1] * 8, "speeds": [10] * 8}},
            position_transform=offset,
        )
        engine.start({"Main": [{"type": "POS", "point_name": "Base",
                                "active_axes": [True] * 8}, {"type": "END"}]})
        self.wait_done(engine)
        self.assertEqual(io.moves[0]["coords"][0], 21)

    def test_saved_dat_and_jump_schema(self):
        io = FakeMachine()
        engine = SequenceExecutor(io, poll_interval=0.001, safe_off_on_stop=False)
        engine.start({"Main": [
            {"type": "DAT", "dat_dt_addr": 60000, "dat_op": 0, "dat_const": 4},
            {"type": "JMP", "condition": True, "cond_type": "DTCMP",
             "cmp_dt_addr": 60000, "cmp_op": 0, "cmp_const": 4, "target_idx": 3},
            {"type": "DAT", "dat_dt_addr": 60000, "dat_op": 0, "dat_const": 99},
            {"type": "END"},
        ]})
        self.wait_done(engine)
        self.assertEqual(engine._data_words[60000], 4)

    def test_saved_jump_signal_groups(self):
        io = FakeMachine()
        engine = SequenceExecutor(io, poll_interval=0.001, safe_off_on_stop=False)
        self.assertTrue(engine._jump_condition(
            {"condition": True, "cond_type": "INPUT", "cond_value": 3, "cond_on": True}))
        self.assertTrue(engine._jump_condition(
            {"condition": True, "cond_type": "VALVE", "cond_value": 34, "cond_on": True}))

    def test_input_timeout_alarm_go_advances(self):
        io = FakeMachine()
        events = []
        engine = SequenceExecutor(
            io, poll_interval=0.001, safe_off_on_stop=False,
            event_callback=lambda name, step: events.append((name, step.get("timeout_alarm_no"))),
        )
        engine.start({"Main": [
            {"type": "IN", "in_type": 0, "port": 0, "on": True,
             "timeout_enabled": True, "timeout": 0.005,
             "timeout_action": "alarm_go", "timeout_alarm_no": 7},
            {"type": "END"},
        ]})
        self.wait_done(engine)
        self.assertEqual(engine.state, ExecutorState.IDLE)
        self.assertEqual(events, [("input_timeout:alarm_go", 7)])

    def test_pause_freezes_timer(self):
        io = FakeDIO()
        engine = SequenceExecutor(io, poll_interval=0.001, safe_off_on_stop=False)
        engine.start({"Main": [
            {"type": "TMR", "time": 0.04},
            {"type": "OUT", "dio_channel": 0, "on": True},
            {"type": "END"},
        ]})
        time.sleep(0.01)
        engine.pause()
        time.sleep(0.06)
        self.assertTrue(engine.is_running)
        self.assertEqual(io.outputs, 0)
        engine.resume()
        self.wait_done(engine)
        self.assertEqual(io.outputs, 1)


if __name__ == "__main__":
    unittest.main()
