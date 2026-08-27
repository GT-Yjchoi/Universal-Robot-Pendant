import unittest

from ui.pages.page_auto_qml import (
    PageAutoQml, default_auto_info_config, normalize_auto_info_config,
)
from utils.variable_store import VariableStore


class ImmediateOverlay:
    def request_text(self, _title, _value="", **kwargs):
        kwargs["callback"](True, "완료 수량")

    def request_confirm(self, _title, _message, **kwargs):
        kwargs["callback"](True)

    def show_message(self, *_args, **_kwargs):
        pass


class AutoInfoConfigTests(unittest.TestCase):
    def test_operation_info_uses_shared_named_data_and_custom_label(self):
        store = VariableStore()
        data_id = store.add_data("서브 완료 카운터", 12)
        config = default_auto_info_config()
        page = PageAutoQml(
            None, {"speed_level": 10}, None, ImmediateOverlay(),
            info_config=config, variable_store=store,
        )

        page._be.beginInfoEdit(0)
        page._be.selectInfoData(data_id)
        self.assertEqual(page._be.infoRows[0]["val"], "12")
        self.assertEqual(page._be.infoRows[0]["source"], "서브 완료 카운터")

        store.set_data(data_id, 37)
        self.assertEqual(page._be.infoRows[0]["val"], "37")

        page._be.renameInfo()
        self.assertEqual(page._be.infoRows[0]["name"], "완료 수량")
        self.assertEqual(config[0], {
            "name": "완료 수량", "data_id": data_id, "plc_source": 0,
        })

    def test_rows_can_be_added_and_deleted_up_to_six(self):
        config = default_auto_info_config()
        page = PageAutoQml(
            None, {"speed_level": 10}, None, ImmediateOverlay(),
            info_config=config, variable_store=VariableStore(),
        )
        self.assertTrue(page._be.addInfo())
        self.assertTrue(page._be.addInfo())
        self.assertFalse(page._be.addInfo())
        self.assertEqual(len(config), 6)
        self.assertEqual(config[-1]["plc_source"], -1)

        page._be.beginInfoEdit(0)
        page._be.deleteInfo()
        self.assertEqual(len(config), 5)
        self.assertEqual(config[0]["plc_source"], 1)

        self.assertEqual(normalize_auto_info_config([]), [])
        self.assertEqual(len(normalize_auto_info_config(None)), 4)


if __name__ == "__main__":
    unittest.main()
