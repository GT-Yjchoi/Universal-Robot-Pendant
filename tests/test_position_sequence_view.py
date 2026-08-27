import unittest

from ui.pages.page_position_qml import PagePositionQml


class PositionSequenceViewTests(unittest.TestCase):
    def setUp(self):
        self.sequences = {
            "Main": [
                {"type": "OUT", "name": "메인1"},
                {"type": "TMR", "name": "메인2", "time": 1.0},
            ],
            "Sub1": [
                {"type": "OUT", "name": "서브1"},
                {"type": "TMR", "name": "서브2", "time": 1.0},
            ],
            "Monitor": [
                {"type": "IN", "name": "상시 감시"},
            ],
        }
        self.page = PagePositionQml(
            sequence_data=self.sequences,
            position_points={},
        )
        self.page._active = True

    def test_runtime_keeps_operator_program_selection(self):
        sub_index = self.page._seq_keys().index("Sub1")
        self.page._on_seq_selector_changed(sub_index)

        self.page._update_realtime_values({
            "op_status": 1,
            "pendant_sequence": True,
            "local_sequence": "Main",
            "current_step": 0,
        })

        self.assertEqual(self.page.current_seq_key, "Sub1")
        self.assertEqual(self.page._hi_row, -1)

    def test_each_program_keeps_its_own_last_highlight(self):
        sub_index = self.page._seq_keys().index("Sub1")
        self.page._on_seq_selector_changed(sub_index)
        self.page._update_realtime_values({
            "op_status": 1,
            "pendant_sequence": True,
            "local_sequence": "Sub1",
            "current_step": 1,
        })
        self.assertEqual(self.page._hi_row, 1)

        # A parallel Main update must not disturb the Sub1 view.
        self.page._update_realtime_values({
            "op_status": 1,
            "pendant_sequence": True,
            "local_sequence": "Main",
            "current_step": 0,
        })
        self.assertEqual(self.page.current_seq_key, "Sub1")
        self.assertEqual(self.page._hi_row, 1)

        # When the operator selects Main, its independently remembered step is shown.
        self.page._on_seq_selector_changed(self.page._seq_keys().index("Main"))
        self.assertEqual(self.page._hi_row, 0)

    def test_large_monitor_rows_show_parallel_highlights_and_clear_completion(self):
        self.page._update_realtime_values({
            "op_status": 1, "pendant_sequence": True,
            "local_sequence": "Main", "current_step": 0,
        })
        self.page._update_realtime_values({
            "op_status": 1, "pendant_sequence": True,
            "local_sequence": "Sub1", "current_step": 1,
        })
        active = [
            (row["program"], row["text"][:4])
            for row in self.page._sequence_monitor_rows()
            if not row["header"] and row["active"]
        ]
        self.assertEqual(active, [
            ("Main", "[01]"),
            ("Sub1", "[02]"),
        ])

        self.page._update_realtime_values({
            "op_status": 1, "pendant_sequence": True,
            "local_sequence": "Sub1", "current_step": -1,
        })
        active_programs = {
            row["program"] for row in self.page._sequence_monitor_rows()
            if not row["header"] and row["active"]
        }
        self.assertEqual(active_programs, {"Main"})

    def test_monitor_program_is_hidden_from_position_lists(self):
        self.assertEqual(self.page._seq_keys(), ["Main", "Sub1"])
        programs = {
            row["program"] for row in self.page._sequence_monitor_rows()
        }
        self.assertNotIn("Monitor", programs)

    def test_monitor_program_cards_group_steps_for_three_column_view(self):
        programs = self.page._sequence_monitor_programs()
        self.assertEqual([row["program"] for row in programs], ["Main", "Sub1"])
        self.assertEqual(programs[0]["kind"], "MAIN")
        self.assertEqual(programs[1]["kind"], "SUB")
        self.assertEqual(len(programs[0]["steps"]), 2)
        self.assertEqual(programs[1]["steps"][1]["stepIndex"], 1)

    def test_parallel_instances_keep_all_real_sub_steps_highlighted(self):
        for execution_id, step_index in ((11, 0), (12, 1)):
            self.page._update_realtime_values({
                "op_status": 1,
                "pendant_sequence": True,
                "local_sequence": "Sub1",
                "local_execution_id": execution_id,
                "current_step": step_index,
            })

        self.assertTrue(self.page._be.isSequenceStepActive("Sub1", 0))
        self.assertTrue(self.page._be.isSequenceStepActive("Sub1", 1))

        self.page._update_realtime_values({
            "op_status": 1,
            "pendant_sequence": True,
            "local_sequence": "Sub1",
            "local_execution_id": 11,
            "local_event_message": "sequence_completed",
            "current_step": -1,
        })
        self.assertFalse(self.page._be.isSequenceStepActive("Sub1", 0))
        self.assertTrue(self.page._be.isSequenceStepActive("Sub1", 1))

    def test_hidden_page_keeps_main_step_for_later_display(self):
        self.page._active = False
        self.page._update_realtime_values({
            "op_status": 1,
            "pendant_sequence": True,
            "local_sequence": "Main",
            "local_execution_id": 1,
            "local_execution_source": "main",
            "current_step": 1,
        })
        self.page._active = True
        self.page._on_seq_selector_changed(0)
        self.assertEqual(self.page._hi_row, 1)
        self.assertTrue(self.page._be.isSequenceStepActive("Main", 1))

    def test_monitor_called_sub_is_tracked_without_showing_monitor(self):
        self.page._update_realtime_values({
            "op_status": 0,
            "pendant_sequence": True,
            "background_sequence": True,
            "local_sequence": "Sub1",
            "local_execution_id": 1,
            "local_execution_source": "monitor",
            "current_step": 0,
        })
        self.assertTrue(self.page._be.isSequenceStepActive("Sub1", 0))

        # An idle Main packet must not erase the independently running Sub1.
        self.page._update_realtime_values({
            "op_status": 0,
            "pendant_sequence": True,
            "local_sequence": "",
            "local_execution_source": "main",
            "current_step": -1,
        })
        self.assertTrue(self.page._be.isSequenceStepActive("Sub1", 0))


if __name__ == "__main__":
    unittest.main()
