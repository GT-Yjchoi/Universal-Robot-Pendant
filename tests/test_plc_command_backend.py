import unittest

from engine.control_backend import SignalGroup
from engine.plc_command_backend import FP0HCommandBackend, PlcCommand


class FakePLC:
    def __init__(self):
        self.is_connected = True
        self.writes = []
        self.bit_writes = []
        self.reads = []
        self.ack = 0
        self._last_monitor_data = {"inputs": [0x0001, 0x0002, 0, 0], "outputs": [0, 0x0004, 0, 0]}

    def write_words(self, area, address, values):
        self.writes.append((area, address, list(values)))
        if address == FP0HCommandBackend.REQUEST_ADDR:
            self.ack = values[FP0HCommandBackend.REQUEST_SEQ_OFFSET]
        return b"ok"

    def read_words(self, area, address, count):
        self.reads.append((area, address, count))
        return [self.ack, FP0HCommandBackend.STATUS_DONE, 0, 0, 0]

    def write_bit(self, area, address, bit, enabled):
        self.bit_writes.append((area, address, bit, bool(enabled)))
        return True


class PlcCommandBackendTests(unittest.TestCase):
    def test_output_set_uses_direct_request_word_without_mailbox_ack(self):
        plc = FakePLC()
        backend = FP0HCommandBackend(plc, timeout=0.1, poll_interval=0.001)
        backend.write_output(SignalGroup.VALVE_IO, 3, True)
        self.assertEqual(plc.bit_writes, [(0x09, 211, 3, True)])
        self.assertEqual(plc.writes, [])
        self.assertEqual(plc.reads, [])

    def test_precise_output_pulse_uses_mailbox_ack(self):
        plc = FakePLC()
        backend = FP0HCommandBackend(plc, timeout=0.1, poll_interval=0.001)
        backend.write_output(SignalGroup.VALVE_IO, 3, True, pulse_ms=20)
        _, address, words = plc.writes[0]
        self.assertEqual(address, 300)
        self.assertEqual(words[:4], [PlcCommand.OUTPUT_PULSE, 1, 3, 1])
        self.assertEqual(words[4:6], [20, 0])
        self.assertEqual(words[42], 1)
        self.assertEqual(plc.reads, [(0x09, 400, 5), (0x09, 400, 5)])

    def test_first_request_continues_after_plc_last_ack(self):
        plc = FakePLC()
        plc.ack = 77
        backend = FP0HCommandBackend(plc, timeout=0.1, poll_interval=0.001)
        backend.write_output(SignalGroup.SYSTEM_IO, 0, True, pulse_ms=10)
        self.assertEqual(plc.writes[0][2][42], 78)

    def test_all_outputs_off_writes_four_request_words_without_ack(self):
        plc = FakePLC()
        backend = FP0HCommandBackend(plc)
        backend.all_outputs_off()
        self.assertEqual(plc.writes, [(0x09, 210, [0, 0, 0, 0])])
        self.assertEqual(plc.reads, [])

    def test_selective_reset_preserves_latched_output_feedback(self):
        plc = FakePLC()
        plc._last_monitor_data["outputs"] = [0b1111, 0b1010, 0, 0]
        backend = FP0HCommandBackend(plc)
        backend.reset_outputs([0, 2, 17])
        self.assertEqual(plc.writes, [(0x09, 210, [0b1010, 0b1000, 0, 0])])

    def test_monitor_snapshot_and_group_offsets(self):
        backend = FP0HCommandBackend(FakePLC())
        self.assertTrue(backend.read_input(SignalGroup.SYSTEM_IO, 0))
        self.assertTrue(backend.read_input(SignalGroup.VALVE_IO, 1))
        self.assertTrue(backend.read_output(SignalGroup.VALVE_IO, 2))
        inputs, outputs = backend.snapshot()
        self.assertEqual(inputs & 1, 1)
        self.assertEqual((outputs >> 18) & 1, 1)

    def test_third_and_fourth_groups_use_remaining_words(self):
        plc = FakePLC()
        backend = FP0HCommandBackend(plc)
        backend.write_output(SignalGroup.IO_GROUP_3, 4, True)
        backend.write_output(SignalGroup.IO_GROUP_4, 5, True)
        self.assertEqual(plc.bit_writes, [
            (0x09, 212, 4, True),
            (0x09, 213, 5, True),
        ])

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
