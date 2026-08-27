import threading
import unittest

from utils.plc_client import PLCClient


class PLCAsyncQueueTests(unittest.TestCase):
    def test_final_pendant_memory_map(self):
        client = PLCClient()
        self.assertEqual(client.HEARTBEAT_ADDR, 200)
        self.assertEqual(client.ADDR_OPERATION_STATE, 201)
        self.assertEqual(client.ADDR_OUTPUT_BASE, 210)
        self.assertEqual(client.ADDR_JOG_CTRL, 220)
        self.assertEqual(client.ADDR_JOG_SPEED, 221)
        self.assertEqual(client.ADDR_SPEED_OVR, 222)
        self.assertEqual(client.ADDR_AXIS_STOP, 223)

        writes = []
        client.write_words = lambda area, address, values: (
            writes.append((area, address, list(values))) or b"ok"
        )
        client.send_operation_state(2)
        client.write_jog_bits(0x12345678)
        client.send_axis_stop(True)
        self.assertEqual(writes, [
            (0x09, 201, [2]),
            (0x09, 210, [0x5678, 0x1234, 0, 0]),
            (0x09, 223, [1]),
        ])

    def test_reserved_monitor_words_are_not_parsed_as_state(self):
        client = PLCClient()
        raw = [0] * 68
        raw[29] = 2
        raw[18:20] = [7, 8]
        raw[36:40] = [9, 10, 11, 12]
        raw[48:50] = [13, 14]
        raw[51:60] = list(range(9))
        data = client._parse_monitor_data(raw)
        self.assertNotIn("op_status", data)
        self.assertNotIn("user_alarm", data)
        self.assertNotIn("step_alarm_id", data)
        self.assertNotIn("pack_idx", data)
        self.assertFalse(data["home_done"])

    def test_axis_jog_bit_uses_one_word_write_without_read_modify_write(self):
        client = PLCClient()
        writes = []
        client.write_words = lambda area, address, values: (
            writes.append((area, address, list(values))) or b"ok"
        )
        client.write_axis_jog_bit(2, True)
        client.write_axis_jog_bit(3, True)
        client.write_axis_jog_bit(2, False)
        self.assertEqual(writes, [
            (0x09, 220, [0b0100]),
            (0x09, 220, [0b1000]),
            (0x09, 220, [0b1000]),
        ])

    def test_new_monitor_map_is_parsed(self):
        client = PLCClient()
        raw = [0] * 68
        raw[16] = 0x0101               # 1축 알람 + 비상정지
        raw[17] = 0x00FF               # 8축 원점완료
        raw[20:22] = [0x5678, 0x1234]  # 1축 에러코드
        raw[40:44] = [1, 2, 3, 4]
        raw[44:48] = [5, 6, 7, 8]
        raw[50] = 2
        raw[60:68] = [25, 0, 100, 0, 123, 0, 456, 0]

        data = client._parse_monitor_data(raw)
        self.assertEqual(client.MONITOR_COUNT, 68)
        self.assertEqual(data["axis_alarms"], [1, 9])
        self.assertEqual(data["axis_home_bits"], 0xFF)
        self.assertTrue(data["home_done"])
        self.assertEqual(data["axis_error_codes"][0], 0x12345678)
        self.assertEqual(data["inputs"], [1, 2, 3, 4])
        self.assertEqual(data["outputs"], [5, 6, 7, 8])
        self.assertEqual(data["operation_mode_status"], 2)
        self.assertEqual(data["production_count"], 25)
        self.assertEqual(data["target_count"], 100)
        self.assertEqual(data["takeout_cycle_time"], 12.3)
        self.assertEqual(data["molding_cycle_time"], 45.6)

    def test_submit_preserves_command_order(self):
        client = PLCClient()
        values = []
        done = threading.Event()

        def append(value):
            values.append(value)
            if len(values) == 4:
                done.set()

        for value in range(4):
            client.submit(append, value)
        self.assertTrue(done.wait(1.0))
        self.assertEqual(values, [0, 1, 2, 3])

    def test_urgent_command_overtakes_waiting_normal_command(self):
        client = PLCClient()
        values = []
        first_started = threading.Event()
        release_first = threading.Event()
        done = threading.Event()

        def blocked_first():
            first_started.set()
            release_first.wait(1.0)
            values.append("first")

        def append(value):
            values.append(value)
            if len(values) == 3:
                done.set()

        client.submit(blocked_first, priority=10)
        self.assertTrue(first_started.wait(1.0))
        client.submit(append, "normal", priority=10)
        client.submit(append, "urgent", priority=-10)
        release_first.set()

        self.assertTrue(done.wait(1.0))
        self.assertEqual(values, ["first", "urgent", "normal"])


if __name__ == "__main__":
    unittest.main()
