import threading
import time
import unittest

from engine.step_executor import ExecutorState, SequenceExecutor, UnsupportedStepError


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
        engine.start({"Main": [{"type": "POS"}]})
        self.wait_done(engine)
        self.assertEqual(engine.state, ExecutorState.ERROR)
        self.assertIn("POS", engine.last_error)
        self.assertEqual(io.outputs, 0)


if __name__ == "__main__":
    unittest.main()
