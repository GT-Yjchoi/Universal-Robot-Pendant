import unittest

from utils.io_manager import IOManager, MAX_GROUPS, OUTPUT_LATCH, OUTPUT_RESET


class IOGroupConfigTests(unittest.TestCase):
    def setUp(self):
        self.manager = IOManager.instance()
        self.saved = self.manager.to_dict()

    def tearDown(self):
        self.manager.load_from_dict(self.saved)

    def test_configured_starts_control_visible_addresses(self):
        self.manager.set_group_configuration(True, [0x00, 0x10, 0x40], [""] * 64)
        self.assertEqual(self.manager.address(True, 0), "X00")
        self.assertEqual(self.manager.address(True, 16), "X10")
        self.assertEqual(self.manager.address(True, 47), "X4F")
        self.assertEqual(self.manager.point_count(True), 48)

    def test_group_configuration_is_serialized(self):
        self.manager.set_group_configuration(False, [0x00, 0x30], ["출력0"] + [""] * 63)
        saved = self.manager.to_dict()
        self.manager.set_group_configuration(False, [0x00], [""] * 64)
        self.manager.load_from_dict(saved)
        self.assertEqual(self.manager.groups(False), [0x00, 0x30])
        self.assertEqual(self.manager.display_label(False, 0), "Y00 [출력0]")

    def test_group_count_is_limited_and_duplicate_starts_are_removed(self):
        self.manager.set_groups(True, [0x00, 0x10, 0x10, 0x20, 0x30, 0x40])
        self.assertEqual(self.manager.groups(True), [0x00, 0x10, 0x20, 0x30])
        self.assertEqual(self.manager.group_count(True), MAX_GROUPS)

    def test_output_stop_modes_default_to_reset_and_are_serialized(self):
        self.manager.load_from_dict({"output_groups": [0x00]})
        self.assertEqual(self.manager.get_output_stop_mode(0), OUTPUT_RESET)
        modes = [OUTPUT_RESET] * 64
        modes[1] = OUTPUT_LATCH
        self.manager.update_names(self.manager.inputs, self.manager.outputs, modes)
        saved = self.manager.to_dict()
        self.manager.load_from_dict(saved)
        self.assertEqual(self.manager.get_output_stop_mode(1), OUTPUT_LATCH)
        self.assertNotIn(1, self.manager.reset_output_indices())
        self.assertIn(0, self.manager.reset_output_indices())


if __name__ == "__main__":
    unittest.main()
