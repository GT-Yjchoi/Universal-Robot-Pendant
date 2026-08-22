import unittest

from engine.control_backend import SignalGroup
from engine.plc_command_backend import FP0HCommandBackend, PlcCommand


class FakePLC:
    def __init__(self):
        self.is_connected = True
        self.writes = []
        self.ack = 0
        self._last_monitor_data = {"inputs": [0x0001, 0, 0x0002, 0], "outputs": [0, 0, 0x0004, 0]}

    def write_words(self, area, address, values):
        self.writes.append((area, address, list(values)))
        self.ack = values[FP0HCommandBackend.REQUEST_SEQ_OFFSET]
        return b"ok"

    def read_words(self, area, address, count):
        return [self.ack, FP0HCommandBackend.STATUS_DONE, 0, 0, 0]


class PlcCommandBackendTests(unittest.TestCase):
    def test_output_command_is_single_atomic_mailbox_write(self):
        plc = FakePLC()
        backend = FP0HCommandBackend(plc, timeout=0.1, poll_interval=0.001)
        backend.write_output(SignalGroup.VALVE_IO, 3, True)
        self.assertEqual(len(plc.writes), 1)
        _, address, words = plc.writes[0]
        self.assertEqual(address, 300)
        self.assertEqual(words[:4], [PlcCommand.OUTPUT_SET, SignalGroup.VALVE_IO, 3, 1])
        self.assertEqual(words[42], 1)

    def test_monitor_snapshot_and_group_offsets(self):
        backend = FP0HCommandBackend(FakePLC())
        self.assertTrue(backend.read_input(SignalGroup.SYSTEM_IO, 0))
        self.assertTrue(backend.read_input(SignalGroup.VALVE_IO, 1))
        self.assertTrue(backend.read_output(SignalGroup.VALVE_IO, 2))
        inputs, outputs = backend.snapshot()
        self.assertEqual(inputs & 1, 1)
        self.assertEqual((outputs >> 34) & 1, 1)

    def test_move_encodes_eight_signed_positions(self):
        plc = FakePLC()
        backend = FP0HCommandBackend(plc, timeout=0.1, poll_interval=0.001)
        backend.move({"coords": [-1.25, 2.5] + [0] * 6, "speeds": [50] * 8,
                      "axes": [True, True] + [False] * 6})
        words = plc.writes[0][2]
        self.assertEqual(words[0], PlcCommand.MOVE_ABSOLUTE)
        self.assertEqual(words[6], 0b11)
        self.assertEqual(words[8] | words[9] << 16, (-1250) & 0xFFFFFFFF)
        self.assertEqual(words[10] | words[11] << 16, 2500)


if __name__ == "__main__":
    unittest.main()
