import struct
import unittest
from unittest.mock import Mock

from drivers.fastech_ezi_io import EziIOClient, EziIOWriteLocked


class EziIOClientTests(unittest.TestCase):
    def test_frame_layout(self):
        self.assertEqual(
            EziIOClient._frame(0x12, EziIOClient.GET_INPUT),
            bytes.fromhex("AA 03 12 00 C0"),
        )

    def test_get_input_decodes_network_byte_order_words(self):
        client = EziIOClient("192.0.2.1")
        client._request = Mock(return_value=struct.pack("<II", 0x1234, 0xABCD))
        state = client.get_input()
        self.assertEqual(state.inputs, 0x1234)
        self.assertEqual(state.latch, 0xABCD)

    def test_writes_are_locked_by_default(self):
        client = EziIOClient("192.0.2.1")
        with self.assertRaises(EziIOWriteLocked):
            client.set_channel(0, True)

    def test_set_channel_uses_separate_set_and_reset_masks(self):
        client = EziIOClient("192.0.2.1", allow_writes=True)
        client._request = Mock(return_value=b"")
        client.set_channel(3, True)
        client._request.assert_called_once_with(
            EziIOClient.SET_OUTPUT, struct.pack("<II", 1 << 3, 0)
        )

    def test_i8o8_channel_zero_maps_to_bit_eight(self):
        client = EziIOClient(
            "192.0.2.1", allow_writes=True, output_offset=8, output_count=8
        )
        client._request = Mock(return_value=b"")
        client.set_channel(0, True)
        client._request.assert_called_once_with(
            EziIOClient.SET_OUTPUT, struct.pack("<II", 1 << 8, 0)
        )

    def test_trigger_frame_is_thirteen_bytes(self):
        client = EziIOClient("192.0.2.1", allow_writes=True)
        client._request = Mock(return_value=b"")
        client.configure_trigger(2, period_ms=20, on_ms=10, count=3)
        payload = client._request.call_args.args[1]
        self.assertEqual(len(payload), 13)
        self.assertEqual(payload, struct.pack("<BHHHHI", 2, 20, 0, 10, 0, 3))


if __name__ == "__main__":
    unittest.main()
