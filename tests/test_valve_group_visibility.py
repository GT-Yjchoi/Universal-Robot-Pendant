import json
import unittest
from unittest.mock import mock_open, patch

from ui.pages.page_manual_qml import ValveBackend, ValveModel
from utils.io_manager import IOManager


class ValveGroupVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.manager = IOManager.instance()
        self.saved_io = self.manager.to_dict()
        self.configs = [
            {"index": i, "name": f"Valve {i}", "mode": "toggle",
             "enabled": True, "order": i}
            for i in range(64)
        ]

    def tearDown(self):
        self.manager.load_from_dict(self.saved_io)

    def _visible_count(self):
        model = ValveModel()
        backend = ValveBackend(None, model)
        contents = json.dumps({"valve_config": self.configs})
        with patch("ui.pages.page_manual_qml.get_settings_path",
                   return_value="settings.json"), \
             patch("ui.pages.page_manual_qml.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=contents)):
            backend.load_configs()
        return model.rowCount()

    def test_only_configured_output_groups_are_available_as_valves(self):
        self.manager.set_groups(False, [0x00])
        self.assertEqual(self._visible_count(), 16)

        self.manager.set_groups(False, [0x00, 0x20])
        self.assertEqual(self._visible_count(), 32)


if __name__ == "__main__":
    unittest.main()
