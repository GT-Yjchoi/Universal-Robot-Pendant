import threading
import unittest

from utils.variable_store import VariableStore


class VariableStoreTests(unittest.TestCase):
    def test_named_values_round_trip_and_reset(self):
        store = VariableStore()
        bit_id = store.add_bit("서브 완료", True)
        data_id = store.add_data("생산 횟수", 7)
        store.set_publish("bit", bit_id, True)
        store.set_publish("data", data_id, True, address=620)
        saved = store.to_dict()

        restored = VariableStore()
        restored.load_from_dict(saved)
        self.assertEqual(restored.bit_name(bit_id), "서브 완료")
        self.assertTrue(restored.get_bit(bit_id))
        self.assertEqual(restored.data_name(data_id), "생산 횟수")
        self.assertEqual(restored.get_data(data_id), 7)

        restored.set_bit(bit_id, False)
        restored.set_data(data_id, 99)
        restored.reset_auto()
        self.assertTrue(restored.get_bit(bit_id))
        self.assertEqual(restored.get_data(data_id), 7)

    def test_parallel_increments_are_atomic(self):
        store = VariableStore()
        data_id = store.add_data("병렬 카운터")
        workers = [
            threading.Thread(
                target=lambda: [store.operate_data(data_id, 1, 1) for _ in range(500)]
            )
            for _ in range(4)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(store.get_data(data_id), 2000)

    def test_data_to_data_arithmetic_is_atomic_and_clamped(self):
        store = VariableStore()
        left = store.add_data("A", 17)
        right = store.add_data("B", 5)
        result = store.add_data("결과", 0)

        self.assertEqual(store.calculate_data(result, left, 0, right), 22)
        self.assertEqual(store.calculate_data(result, left, 1, right), 12)
        self.assertEqual(store.calculate_data(result, left, 2, right), 85)
        self.assertEqual(store.calculate_data(result, left, 3, right), 3)
        store.set_data(left, -17)
        self.assertEqual(store.calculate_data(result, left, 3, right), -3)
        store.set_data(left, 2 ** 31 - 1)
        self.assertEqual(store.calculate_data(result, left, 2, right), 2 ** 31 - 1)
        store.set_data(right, 0)
        with self.assertRaises(ZeroDivisionError):
            store.calculate_data(result, left, 3, right)

    def test_legacy_recipe_references_are_migrated(self):
        sequences = {"Main": [
            {"type": "OUT", "out_type": 2, "port": 3, "on": True},
            {"type": "DAT", "dat_dt_addr": 60007, "dat_op": 1, "dat_const": 1},
            {"type": "JMP", "condition": True, "cond_type": "BIT", "cond_value": 103},
            {"type": "JMP", "condition": True, "cond_type": "DTCMP", "cmp_dt_addr": 60007},
        ]}
        store = VariableStore()
        store.load_from_dict({}, sequences)
        self.assertIn(3, store.bit_ids())
        self.assertIn(7, store.data_ids())
        self.assertEqual(sequences["Main"][0]["bit_id"], 3)
        self.assertEqual(sequences["Main"][1]["data_id"], 7)
        self.assertEqual(sequences["Main"][2]["cond_bit_id"], 3)
        self.assertEqual(sequences["Main"][3]["cmp_data_id"], 7)

    def test_export_snapshot_only_exposes_published_values(self):
        store = VariableStore()
        public_bit = store.add_bit("공개 비트", True, item_id=17)
        store.add_bit("비공개 비트", True, item_id=18)
        public_data = store.add_data("공개 데이터", -3, item_id=4)
        store.add_data("비공개 데이터", 99, item_id=5)
        store.set_publish("bit", public_bit, True)
        store.set_publish("data", public_data, True, address=630)
        store.mark_all_dirty()
        _, words, values = store.export_snapshot()
        self.assertEqual(words[1], 0b10)
        self.assertEqual(values[630], -3)
        self.assertNotIn(5, values)

    def test_data_plc_address_is_manual_unique_and_clears_old_slot(self):
        store = VariableStore()
        first = store.add_data("업체 공개 1", 11)
        second = store.add_data("업체 공개 2", 22)

        with self.assertRaises(ValueError):
            store.set_publish("data", first, True)
        with self.assertRaises(ValueError):
            store.set_publish("data", first, True, address=513)
        store.set_publish("data", first, True, address=620)
        with self.assertRaises(ValueError):
            store.set_publish("data", second, True, address=620)

        store.export_snapshot()
        store.set_publish("data", first, True, address=622)
        _, _, values = store.export_snapshot()
        self.assertEqual(values[620], 0)
        self.assertEqual(values[622], 11)

        store.set_publish("data", first, False)
        _, _, values = store.export_snapshot()
        self.assertEqual(values, {622: 0})
        self.assertIsNone(store.data_plc_address(first))

    def test_version_two_published_data_keeps_legacy_address_once(self):
        store = VariableStore()
        store.load_from_dict({
            "version": 2,
            "data": [{
                "id": 4, "name": "구형 공개 데이터", "initial": 9,
                "reset_policy": "auto", "plc_publish": True,
            }],
        })
        self.assertEqual(store.data_plc_address(4), 520)

    def test_deleted_export_id_is_never_reused(self):
        store = VariableStore()
        old_bit = store.add_bit("이전 공개 비트")
        old_data = store.add_data("이전 공개 데이터")
        store.remove("bit", old_bit)
        store.remove("data", old_data)
        self.assertEqual(store.add_bit("새 비트"), old_bit + 1)
        self.assertEqual(store.add_data("새 데이터"), old_data + 1)

        saved = store.to_dict()
        restored = VariableStore()
        restored.load_from_dict(saved)
        latest_bit = max(restored.bit_ids())
        latest_data = max(restored.data_ids())
        restored.remove("bit", latest_bit)
        restored.remove("data", latest_data)
        self.assertEqual(restored.add_bit("재로드 후 비트"), latest_bit + 1)
        self.assertEqual(restored.add_data("재로드 후 데이터"), latest_data + 1)


if __name__ == "__main__":
    unittest.main()
