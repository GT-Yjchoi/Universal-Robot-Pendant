import threading
import time
import unittest
from unittest.mock import patch

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

    def test_call_emits_subsequence_completion_marker(self):
        io = FakeDIO()
        events = []
        engine = SequenceExecutor(
            io, poll_interval=0.001, safe_off_on_stop=False,
            status_callback=events.append,
        )
        engine.start({
            "Main": [{"type": "CALL", "target_seq": "Sub"}, {"type": "END"}],
            "Sub": [{"type": "TMR", "time": 0.001}, {"type": "END"}],
        })
        self.wait_done(engine)
        self.assertTrue(any(
            event.sequence == "Sub"
            and event.step_index == -1
            and event.message == "sequence_completed"
            for event in events
        ))
        sub_steps = [
            event for event in events
            if event.sequence == "Sub" and event.step_index >= 0
        ]
        sub_completions = [
            event for event in events
            if event.sequence == "Sub"
            and event.message == "sequence_completed"
        ]
        self.assertTrue(sub_steps)
        self.assertEqual(
            {event.execution_id for event in sub_steps},
            {event.execution_id for event in sub_completions},
        )
        self.assertNotEqual(sub_steps[0].execution_id, 0)

    def test_unsupported_pos_fails_and_safe_off(self):
        io = FakeDIO(); io.outputs = 0xFF
        engine = SequenceExecutor(io, poll_interval=0.001)
        engine.start({"Main": [{"type": "POS", "coords": [0] * 8,
                                "active_axes": [True] * 8}]})
        self.wait_done(engine)
        self.assertEqual(engine.state, ExecutorState.ERROR)
        self.assertIn("POS", engine.last_error)
        self.assertEqual(io.outputs, 0)

    def test_configured_output_stop_callback_replaces_global_output_off(self):
        io = FakeDIO(); io.outputs = 0b11
        called = []

        def apply_policy():
            called.append(True)
            io.outputs &= ~0b01

        engine = SequenceExecutor(
            io, poll_interval=0.001, output_stop_callback=apply_policy,
        )
        engine.start({"Main": [{"type": "END"}]})
        self.wait_done(engine)
        self.assertTrue(called)
        self.assertEqual(io.outputs, 0b10)

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
        self.assertEqual(engine.variable_store.get_data(0), 12)

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
        self.assertEqual(engine.variable_store.get_data(0), 4)

    def test_data_step_calculates_two_data_values_into_a_result(self):
        io = FakeMachine()
        engine = SequenceExecutor(io, poll_interval=0.001, safe_off_on_stop=False)
        left = engine.variable_store.add_data("A", 18, item_id=0)
        right = engine.variable_store.add_data("B", 4, item_id=1)
        result = engine.variable_store.add_data("결과", 0, item_id=2)
        engine.start({"Main": [
            {"type": "DAT", "dat_mode": "data", "data_id": result,
             "dat_left_data_id": left, "dat_math_op": 2,
             "dat_right_data_id": right},
            {"type": "END"},
        ]})
        self.wait_done(engine)
        self.assertEqual(engine.variable_store.get_data(result), 72)

    def test_data_step_zero_division_stops_with_clear_error(self):
        io = FakeMachine()
        engine = SequenceExecutor(io, poll_interval=0.001, safe_off_on_stop=False)
        left = engine.variable_store.add_data("A", 18, item_id=0)
        right = engine.variable_store.add_data("B", 0, item_id=1)
        result = engine.variable_store.add_data("결과", 7, item_id=2)
        engine.start({"Main": [
            {"type": "DAT", "dat_mode": "data", "data_id": result,
             "dat_left_data_id": left, "dat_math_op": 3,
             "dat_right_data_id": right},
        ]})
        self.wait_done(engine)
        self.assertEqual(engine.state, ExecutorState.ERROR)
        self.assertIn("제수가 0", engine.last_error)
        self.assertEqual(engine.variable_store.get_data(result), 7)

    def test_saved_jump_signal_groups(self):
        io = FakeMachine()
        engine = SequenceExecutor(io, poll_interval=0.001, safe_off_on_stop=False)
        self.assertTrue(engine._jump_condition(
            {"condition": True, "cond_type": "INPUT", "cond_value": 3, "cond_on": True}))
        self.assertTrue(engine._jump_condition(
            {"condition": True, "cond_type": "VALVE", "cond_value": 34, "cond_on": True}))

    def test_jump_alarm_state_uses_alarm_provider(self):
        alarm = [False]
        engine = SequenceExecutor(
            FakeMachine(), poll_interval=0.001, safe_off_on_stop=False,
            state_provider=lambda: 1,
            alarm_provider=lambda: alarm[0],
        )
        step = {
            "condition": True, "cond_type": "STATE",
            "cond_value": 3, "cond_on": True,
        }
        self.assertFalse(engine._jump_condition(step))
        alarm[0] = True
        self.assertTrue(engine._jump_condition(step))
        # Alarm is an additional condition and does not replace AUTO state.
        step["cond_value"] = 1
        self.assertTrue(engine._jump_condition(step))

    def test_jump_position_compares_selected_axes_with_tolerance(self):
        io = FakeMachine()
        actual = [10.04, 999.0, 30.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        engine = SequenceExecutor(
            io, poll_interval=0.001, safe_off_on_stop=False,
            position_points={"검사 위치": {
                "coords": [10.0, 20.0, 30.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            }},
            position_provider=lambda: actual,
        )
        step = {
            "condition": True, "cond_type": "POSITION",
            "cond_point_name": "검사 위치",
            "cond_position_axes": [True, False, True] + [False] * 5,
            "cond_position_tolerance": 0.05, "cond_on": True,
        }
        self.assertTrue(engine._jump_condition(step))
        actual[0] = 10.06
        self.assertFalse(engine._jump_condition(step))
        step["cond_on"] = False
        self.assertTrue(engine._jump_condition(step))

    def test_jump_position_fails_safe_without_actual_position(self):
        engine = SequenceExecutor(
            FakeMachine(), safe_off_on_stop=False,
            position_points={"P1": {"coords": [0.0] * 8}},
        )
        with self.assertRaises(UnsupportedStepError):
            engine._jump_condition({
                "condition": True, "cond_type": "POSITION",
                "cond_point_name": "P1",
                "cond_position_axes": [True] + [False] * 7,
            })

    def test_wpos_waits_until_selected_axes_reach_point(self):
        io = FakeDIO()
        actual = [0.0] * 8
        engine = SequenceExecutor(
            io, poll_interval=0.001, safe_off_on_stop=False,
            position_points={"도착 위치": {"coords": [10.0, 20.0] + [0.0] * 6}},
            position_provider=lambda: list(actual),
        )
        engine.start({"Main": [
            {"type": "WPOS", "point_name": "도착 위치",
             "active_axes": [True, False] + [False] * 6,
             "position_tolerance": 0.1, "timeout": 0.3},
            {"type": "OUT", "dio_channel": 0, "on": True},
            {"type": "END"},
        ]})
        time.sleep(0.03)
        self.assertTrue(engine.is_running)
        self.assertEqual(io.outputs, 0)
        actual[0] = 10.05
        self.wait_done(engine)
        self.assertEqual(io.outputs, 1)

    def test_wpos_timeout_stops_sequence_with_clear_error(self):
        engine = SequenceExecutor(
            FakeMachine(), poll_interval=0.001, safe_off_on_stop=False,
            position_points={"미도착 위치": {"coords": [10.0] + [0.0] * 7}},
            position_provider=lambda: [0.0] * 8,
        )
        engine.start({"Main": [{
            "type": "WPOS", "point_name": "미도착 위치",
            "active_axes": [True] + [False] * 7,
            "position_tolerance": 0.1, "timeout": 0.01,
        }]})
        self.wait_done(engine)
        self.assertEqual(engine.state, ExecutorState.ERROR)
        self.assertIn("WPOS 위치 도달 타임아웃", engine.last_error)

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

    def test_input_timeout_selection_reset_restarts_wait_without_advancing(self):
        io = FakeDIO()
        events = []
        engine = SequenceExecutor(
            io, poll_interval=0.001, safe_off_on_stop=False,
            event_callback=lambda name, _step: events.append(name) or "reset",
        )
        engine.start({"Main": [
            {"type": "IN", "dio_channel": 0, "on": True,
             "timeout_enabled": True, "timeout": 0.01,
             "timeout_action": "continue"},
            {"type": "OUT", "dio_channel": 1, "on": True},
            {"type": "END"},
        ]})
        threading.Timer(0.025, lambda: setattr(io, "inputs", 0b1)).start()
        self.wait_done(engine)
        self.assertGreaterEqual(len(events), 1)
        self.assertTrue(all(event == "input_timeout:continue" for event in events))
        self.assertEqual(io.outputs & 0b10, 0b10)

    def test_missing_saved_timeout_uses_same_five_seconds_shown_by_editor(self):
        io = FakeDIO()
        events = []
        engine = SequenceExecutor(
            io, poll_interval=0.001, safe_off_on_stop=False,
            event_callback=lambda name, _step: events.append(name) or "proceed",
        )
        class FakeClock:
            def __init__(self):
                self.ticks = [0.0, 0.0, 4.9, 5.0]

            def monotonic(self):
                return self.ticks.pop(0) if self.ticks else 5.0

        with patch("engine.step_executor.time", FakeClock()):
            self.assertTrue(engine._wait_input({
                "type": "IN", "dio_channel": 0, "on": True,
                "timeout_enabled": True, "timeout_action": "continue",
            }))
        self.assertEqual(events, ["input_timeout:continue"])

    def test_timeout_selection_holds_only_its_flow_until_operator_stops(self):
        io = FakeDIO()
        release = threading.Event()

        def select_after_other_programs(_name, _step):
            release.wait(0.5)
            return "stop"

        engine = SequenceExecutor(
            io, poll_interval=0.001, safe_off_on_stop=False,
            event_callback=select_after_other_programs,
        )
        engine.start({
            "Main": [
                {"type": "CALL", "target_seq": "AlarmSub", "parallel": True},
                {"type": "CALL", "target_seq": "FinishSub", "parallel": True},
                {"type": "END"},
            ],
            "AlarmSub": [
                {"type": "IN", "dio_channel": 0, "on": True,
                 "timeout_enabled": True, "timeout": 0.01,
                 "timeout_action": "continue"},
                {"type": "END"},
            ],
            "FinishSub": [
                {"type": "TMR", "time": 0.03},
                {"type": "OUT", "dio_channel": 1, "on": True},
                {"type": "END"},
            ],
        })
        time.sleep(0.08)
        self.assertTrue(engine.is_running)
        self.assertEqual(io.outputs & 0b10, 0b10)
        release.set()
        self.wait_done(engine)
        self.assertEqual(engine.state, ExecutorState.IDLE)

    def test_input_timeup_requires_one_continuous_signal_period(self):
        io = FakeDIO()
        engine = SequenceExecutor(io, poll_interval=0.001, safe_off_on_stop=False)
        engine.start({"Main": [
            {"type": "IN", "dio_channel": 0, "on": True,
             "timeup_enabled": True, "timeup_time": 0.2},
            {"type": "OUT", "dio_channel": 1, "on": True},
            {"type": "END"},
        ]})

        # The first pulse is shorter than 200 ms, so it must not complete the step.
        threading.Timer(0.01, lambda: setattr(io, "inputs", 0b1)).start()
        threading.Timer(0.03, lambda: setattr(io, "inputs", 0)).start()
        threading.Timer(0.05, lambda: setattr(io, "inputs", 0b1)).start()
        time.sleep(0.1)
        self.assertTrue(engine.is_running)
        self.assertEqual(io.outputs & 0b10, 0)

        self.wait_done(engine)
        self.assertEqual(io.outputs & 0b10, 0b10)

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
