import unittest

from ui.pages.page_auto_qml import _axis_config_masks


class AxisEncoderConfigTests(unittest.TestCase):
    def test_existing_config_defaults_used_axes_to_incremental(self):
        use_mask, home_mask = _axis_config_masks({
            "axis_uses": [True, True, True, True, False, False, False, False],
        })
        self.assertEqual(use_mask, 0x0F)
        self.assertEqual(home_mask, 0x0F)

    def test_all_used_axes_absolute_removes_homing_requirement(self):
        use_mask, home_mask = _axis_config_masks({
            "axis_uses": [True, True, True, False, False, False, False, False],
            "axis_encoder_types": [
                "absolute", "absolute", "absolute", "incremental",
                "incremental", "incremental", "incremental", "incremental",
            ],
        })
        self.assertEqual(use_mask, 0x07)
        self.assertEqual(home_mask, 0)

    def test_only_used_incremental_axes_require_homing(self):
        use_mask, home_mask = _axis_config_masks({
            "axis_uses": [True, True, False, True, False, False, False, False],
            "axis_encoder_types": [
                "absolute", "incremental", "incremental", "absolute",
                "incremental", "incremental", "incremental", "incremental",
            ],
        })
        self.assertEqual(use_mask, 0x0B)
        self.assertEqual(home_mask, 0x02)


if __name__ == "__main__":
    unittest.main()
