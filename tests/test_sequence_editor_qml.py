import unittest

from ui.dialogs.sequence_editor_qml import SequenceEditorBackend, StepListModel
from ui.sequence_schema import normalize_step
from utils.io_manager import IOManager


class ImmediateOverlay:
    def __init__(self):
        self.text_result = (True, "새 지연")
        self.number_result = (True, 1.25)
        self.confirm_result = True
        self.messages = []

    def request_text(self, _title, _value="", **kwargs):
        kwargs["callback"](*self.text_result)

    def request_number(self, _title, _value=0, **kwargs):
        kwargs["callback"](*self.number_result)

    def request_confirm(self, _title, _message, **kwargs):
        kwargs["callback"](self.confirm_result)

    def show_message(self, title, message, **_kwargs):
        self.messages.append((title, message))


class SequenceEditorBackendTests(unittest.TestCase):
    def setUp(self):
        self.steps = [
            {
                "type": "IN", "name": "입력 대기", "in_type": 0, "port": 7,
                "on": True, "timeout_enabled": True, "timeout": 5.0,
                "timeout_action": "ask", "timeout_alarm_no": 18,
                "timeup_enabled": True, "timeup_time": 0.4,
            },
            {
                "type": "OUT", "name": "지연 출력", "out_type": 0, "port": 0,
                "on": True, "delay_enable": True, "delay_time": 0.5,
            },
            {"type": "TMR", "name": "대기", "tmr_mode": "simple", "time": 1.0},
        ]
        self.sub_steps = [
            {"type": "TMR", "name": "짧은 대기", "time": 0.25,
             "timer_ref": "짧은 대기"},
            {"type": "OUT", "name": "서브 지연", "delay_enable": True,
             "delay_time": 0.25, "delay_timer_ref": "짧은 대기"},
            {"type": "IN", "name": "서브 타임아웃", "timeout_enabled": True,
             "timeout": 0.25, "timeout_timer_ref": "짧은 대기"},
        ]
        self.model = StepListModel()
        self.overlay = ImmediateOverlay()
        self.backend = SequenceEditorBackend(
            {"Main": self.steps, "Sub": self.sub_steps},
            {"짧은 대기": 0.25}, {}, self.model,
            overlay=self.overlay,
        )

    def test_input_timeout_action_and_alarm_are_editable(self):
        self.assertTrue(self.backend.selectedTimeoutEnabled)
        self.assertEqual(self.backend.selectedTimeoutAction, 1)
        self.assertEqual(self.backend.selectedTimeoutAlarmNo, 18)

        self.backend.selectLibraryTimer("짧은 대기")
        self.assertEqual(self.steps[0]["timeout_timer_ref"], "짧은 대기")
        self.assertEqual(self.steps[0]["timeout"], 0.25)

        self.backend.setTimeoutSeconds(9.0)
        self.backend.setTimeoutAction(2)
        self.backend.setTimeoutAlarmNo(23)

        self.assertEqual(self.steps[0]["timeout"], 9.0)
        self.assertEqual(self.steps[0]["timeout_action"], "alarm_go")
        self.assertEqual(self.steps[0]["timeout_alarm_no"], 23)
        self.assertNotIn("timeout_timer_ref", self.steps[0])

        self.backend.setTimeoutAction(0)
        self.assertEqual(self.steps[0]["timeout_action"], "continue")
        self.assertIn("알람 후 진행여부 선택", self.model.data(
            self.model.index(0, 0), StepListModel.DetailRole,
        ))

    def test_enabling_timeout_persists_the_displayed_five_second_default(self):
        step = {
            "type": "IN", "name": "기본 타임아웃", "in_type": 0,
            "port": 0, "on": True, "timeout_enabled": False,
        }
        model = StepListModel()
        backend = SequenceEditorBackend(
            {"Main": [step]}, {}, {}, model, overlay=self.overlay,
        )
        backend.setTimeoutEnabled(True)
        self.assertEqual(step["timeout"], 5.0)
        self.assertEqual(backend.selectedTimeoutSeconds, 5.0)

    def test_input_timeup_uses_direct_or_shared_timer_without_changing_timeout(self):
        self.assertTrue(self.backend.selectedTimeupEnabled)
        self.assertAlmostEqual(self.backend.selectedTimeupSeconds, 0.4)

        self.backend.selectTimeupTimer("짧은 대기")
        self.assertEqual(self.steps[0]["timeup_timer_ref"], "짧은 대기")
        self.assertEqual(self.steps[0]["timeup_time"], 0.25)
        self.assertEqual(self.steps[0]["timeout"], 5.0)

        self.backend.setTimeupSeconds(0.8)
        self.assertNotIn("timeup_timer_ref", self.steps[0])
        self.assertAlmostEqual(self.steps[0]["timeup_time"], 0.8)

        self.overlay.number_result = (True, 1.2)
        self.backend.editTimeupSeconds()
        self.assertAlmostEqual(self.steps[0]["timeup_time"], 1.2)
        self.assertEqual(self.steps[0]["timeout"], 5.0)

    def test_all_io_address_selectors_use_settings_names(self):
        manager = IOManager.instance()
        old_inputs, old_outputs = list(manager.inputs), list(manager.outputs)
        try:
            inputs, outputs = list(old_inputs), list(old_outputs)
            inputs[0] = "제품 감지"
            inputs[18] = "금형 개방 확인"
            outputs[0] = "클램프 출력"
            manager.update_names(inputs, outputs)

            self.backend.selectStep(1)
            self.assertEqual(self.backend.addressKeys[0], "Y00 [클램프 출력]")
            self.assertIn("Y00 [클램프 출력]", self.model.data(
                self.model.index(1, 0), StepListModel.DetailRole,
            ))

            self.backend.selectStep(0)
            self.assertEqual(self.backend.addressKeys[0], "X00 [제품 감지]")
            self.backend.setAddressIndex(18)
            self.assertEqual(self.steps[0]["port"], 34)
            self.assertEqual(self.backend.addressKeys[18], "X22 [금형 개방 확인]")

            jump = {
                "type": "JMP", "name": "조건 분기", "condition": True,
                "target_idx": 0, "cond_type": "VALVE", "cond_value": 34,
                "cond_on": True,
            }
            jump_model = StepListModel()
            jump_backend = SequenceEditorBackend(
                {"Main": [jump]}, {}, {}, jump_model, overlay=self.overlay,
            )
            self.assertEqual(jump_backend.condAddressKeys[18], "X22 [금형 개방 확인]")
            self.assertEqual(jump_backend.selectedCondAddressIndex, 18)
            from utils.variable_store import VariableStore
            bit_id = VariableStore.instance().add_bit("조건 허용")
            jump_backend.setCondType(1)
            jump_backend.selectCondBit(bit_id)
            self.assertEqual(jump["cond_bit_id"], bit_id)
            self.assertEqual(jump["cond_value"], 100 + bit_id)
        finally:
            manager.update_names(old_inputs, old_outputs)

    def test_third_configured_group_is_saved_with_compatible_type_code(self):
        manager = IOManager.instance()
        saved = manager.to_dict()
        try:
            manager.set_group_configuration(True, [0x00, 0x20, 0x40], [""] * 64)
            self.backend.selectStep(0)
            self.backend.setAddressIndex(35)
            self.assertEqual(self.steps[0]["in_type"], 4)
            self.assertEqual(self.steps[0]["port"], 3)
            self.assertEqual(self.backend.addressKeys[35], "X43")
        finally:
            manager.load_from_dict(saved)

    def test_output_delay_can_reference_library_or_use_direct_time(self):
        self.backend.selectStep(1)
        self.backend.setDelayTimerIndex(1)
        self.assertEqual(self.steps[1]["delay_timer_ref"], "짧은 대기")
        self.assertEqual(self.steps[1]["delay_time"], 0.25)

        self.backend.setDelaySeconds(0.7)
        self.assertNotIn("delay_timer_ref", self.steps[1])
        self.assertAlmostEqual(self.steps[1]["delay_time"], 0.7)

    def test_output_delay_time_uses_touch_input_and_manages_timer_library(self):
        self.backend.selectStep(1)
        self.backend.setDelayTimerIndex(1)

        self.overlay.number_result = (True, 0.75)
        self.backend.editDelaySeconds()
        self.assertEqual(self.backend.timer_library["짧은 대기"], 0.75)
        self.assertEqual(self.steps[1]["delay_timer_ref"], "짧은 대기")
        self.assertEqual(self.steps[1]["delay_time"], 0.75)

        self.overlay.number_result = (True, 1.25)
        self.backend.addDelayTimer()
        self.assertEqual(self.backend.timer_library["새 지연"], 1.25)
        self.assertEqual(self.steps[1]["delay_timer_ref"], "새 지연")
        self.sub_steps[0]["timer_ref"] = "새 지연"
        self.sub_steps[1]["delay_timer_ref"] = "새 지연"
        self.sub_steps[2]["timeout_timer_ref"] = "새 지연"
        self.steps[0]["timeup_timer_ref"] = "새 지연"
        self.steps[0]["timeup_time"] = 1.25

        self.overlay.text_result = (True, "변경된 지연")
        self.backend.renameDelayTimer("새 지연")
        self.assertNotIn("새 지연", self.backend.timer_library)
        self.assertEqual(self.backend.timer_library["변경된 지연"], 1.25)
        self.assertEqual(self.steps[1]["delay_timer_ref"], "변경된 지연")
        self.assertEqual(self.sub_steps[0]["timer_ref"], "변경된 지연")
        self.assertEqual(self.sub_steps[1]["delay_timer_ref"], "변경된 지연")
        self.assertEqual(self.sub_steps[2]["timeout_timer_ref"], "변경된 지연")
        self.assertEqual(self.steps[0]["timeup_timer_ref"], "변경된 지연")

        self.backend.deleteDelayTimer()
        self.assertNotIn("변경된 지연", self.backend.timer_library)
        self.assertNotIn("delay_timer_ref", self.steps[1])
        self.assertEqual(self.steps[1]["delay_time"], 1.25)
        self.assertNotIn("timer_ref", self.sub_steps[0])
        self.assertNotIn("delay_timer_ref", self.sub_steps[1])
        self.assertNotIn("timeout_timer_ref", self.sub_steps[2])
        self.assertNotIn("timeup_timer_ref", self.steps[0])

    def test_timer_supports_library_and_direct_time(self):
        self.backend.selectStep(2)
        self.backend.selectLibraryTimer("짧은 대기")
        self.assertEqual(self.steps[2]["timer_ref"], "짧은 대기")
        self.assertEqual(self.steps[2]["time"], 0.25)

        self.backend.setSeconds(1.3)
        self.assertAlmostEqual(self.steps[2]["time"], 1.3)
        self.assertNotIn("timer_ref", self.steps[2])

    def test_legacy_held_timer_is_migrated_to_input_timeup(self):
        step = {
            "type": "TMR", "name": "구형 유지 대기", "tmr_mode": "hold",
            "in_type": 0, "port": 3, "on": True, "time": 0.5,
            "timer_ref": "짧은 대기",
        }
        normalize_step(step, {"짧은 대기": 0.25})
        self.assertEqual(step["type"], "IN")
        self.assertTrue(step["timeup_enabled"])
        self.assertEqual(step["timeup_timer_ref"], "짧은 대기")
        self.assertEqual(step["timeup_time"], 0.25)
        self.assertNotIn("tmr_mode", step)

    def test_in_out_and_tmr_share_one_timer_library(self):
        bindings = (
            (0, "timeout_timer_ref", "timeout"),
            (1, "delay_timer_ref", "delay_time"),
            (2, "timer_ref", "time"),
        )
        for row, ref_field, value_field in bindings:
            self.backend.selectStep(row)
            self.backend.selectLibraryTimer("짧은 대기")
            self.assertEqual(self.steps[row][ref_field], "짧은 대기")
            self.assertEqual(self.steps[row][value_field], 0.25)

        self.backend.selectStep(2)
        self.overlay.number_result = (True, 0.6)
        self.backend.editLibraryTimerSeconds()
        self.assertEqual(self.backend.timer_library["짧은 대기"], 0.6)
        self.assertEqual(self.steps[0]["timeout"], 0.6)
        self.assertEqual(self.steps[1]["delay_time"], 0.6)
        self.assertEqual(self.steps[2]["time"], 0.6)
        self.assertEqual(self.sub_steps[0]["time"], 0.6)
        self.assertEqual(self.sub_steps[1]["delay_time"], 0.6)
        self.assertEqual(self.sub_steps[2]["timeout"], 0.6)

    def test_comments_are_unnumbered_and_use_touch_keyboard(self):
        steps = [
            {"type": "OUT", "name": "출력", "out_type": 0, "port": 0},
            {"type": "COMMENT", "text": "기존 메모"},
            {"type": "TMR", "name": "대기", "time": 1.0},
            {"type": "JMP", "name": "반복", "target_idx": 1},
        ]
        model = StepListModel()
        backend = SequenceEditorBackend(
            {"Main": steps}, {}, {}, model, overlay=self.overlay,
        )
        numbers = [
            model.data(model.index(row, 0), StepListModel.NumberRole)
            for row in range(model.rowCount())
        ]
        self.assertEqual(numbers, ["1", "", "2", "3"])

        backend.selectStep(3)
        self.assertEqual(len(backend.stepTargets), 3)
        self.assertEqual(backend.selectedTargetIndex, 1)
        backend.setTargetIndex(0)
        self.assertEqual(steps[3]["target_idx"], 0)

        backend.selectStep(1)
        self.overlay.text_result = (True, "터치로 변경한 메모")
        backend.editComment()
        self.assertEqual(steps[1]["text"], "터치로 변경한 메모")

    def test_position_step_exposes_and_edits_all_point_details(self):
        step = {
            "type": "POS", "name": "취출 위치", "point_name": "P1",
            "active_axes": [True, False, True, True, False, True, True, True],
            "wait_completion": True,
        }
        points = {
            "P1": {
                "coords": [10.1234, 20, 30, 40, 50, 60, 70, 80],
                "speeds": [90, 80, 70, 60, 50, 40, 30, 20],
            }
        }
        model = StepListModel()
        backend = SequenceEditorBackend(
            {"Main": [step]}, {}, points, model, overlay=self.overlay,
        )

        rows = backend.positionAxisRows
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "X")
        self.assertEqual(rows[0]["position"], "10.123")
        self.assertEqual(rows[0]["speed"], "90")
        self.assertTrue(rows[0]["active"])

        backend.setPointCoordinate(0, 123.4567)
        backend.setPointSpeed(0, 77)
        backend.setAxisActive(0, False)
        self.assertEqual(points["P1"]["coords"][0], 123.457)
        self.assertEqual(points["P1"]["speeds"][0], 77)
        self.assertFalse(step["active_axes"][0])

        self.overlay.number_result = (True, 12.5)
        backend.editPointCoordinate(1)
        self.assertEqual(points["P1"]["coords"][1], 12.5)
        self.overlay.number_result = (True, 65)
        backend.editPointSpeed(1)
        self.assertEqual(points["P1"]["speeds"][1], 65)

    def test_position_point_add_rename_delete_updates_every_reference(self):
        main = [{"type": "POS", "name": "P1", "point_name": "P1"}]
        sub = [
            {"type": "POS", "name": "서브 이동", "point_name": "P1"},
            {"type": "WPOS", "name": "도착 대기", "point_name": "P1"},
            {"type": "JMP", "name": "위치 분기", "condition": True,
             "cond_type": "POSITION", "cond_point_name": "P1", "target_idx": 0},
        ]
        points = {"P1": {"coords": [0.0] * 8, "speeds": [100] * 8}}
        model = StepListModel()
        backend = SequenceEditorBackend(
            {"Main": main, "Sub": sub}, {}, points, model, overlay=self.overlay,
        )

        self.overlay.text_result = (True, "새 위치")
        backend.addPositionPoint()
        self.assertIn("새 위치", points)
        self.assertEqual(main[0]["point_name"], "새 위치")
        sub[1]["point_name"] = "새 위치"
        sub[2]["cond_point_name"] = "새 위치"

        self.overlay.text_result = (True, "변경 위치")
        backend.renameSelectedPoint()
        self.assertNotIn("새 위치", points)
        self.assertIn("변경 위치", points)
        self.assertEqual(main[0]["point_name"], "변경 위치")
        self.assertEqual(sub[1]["point_name"], "변경 위치")
        self.assertEqual(sub[2]["cond_point_name"], "변경 위치")

        sub[0]["point_name"] = "변경 위치"
        backend.deleteSelectedPoint()
        self.assertNotIn("변경 위치", points)
        self.assertEqual(main[0]["point_name"], "P1")
        self.assertEqual(sub[0]["point_name"], "P1")
        self.assertEqual(sub[1]["point_name"], "P1")
        self.assertEqual(sub[2]["cond_point_name"], "P1")

    def test_wpos_editor_selects_point_axes_tolerance_and_timeout(self):
        points = {"완료 위치": {"coords": [10, 20, 30, 40, 50, 60, 70, 80]}}
        step = {
            "type": "WPOS", "name": "위치 도달 대기", "point_name": "완료 위치",
            "active_axes": [True] * 8, "position_tolerance": 0.1, "timeout": 5.0,
        }
        model = StepListModel()
        backend = SequenceEditorBackend(
            {"Main": [step]}, {}, points, model, overlay=self.overlay,
        )

        backend.setAxisActive(1, False)
        self.overlay.number_result = (True, 0.25)
        backend.editWaitPositionTolerance()
        self.overlay.number_result = (True, 7.5)
        backend.editWaitPositionTimeout()

        self.assertFalse(step["active_axes"][1])
        self.assertEqual(step["position_tolerance"], 0.25)
        self.assertEqual(step["timeout"], 7.5)
        self.assertIn("완료 위치 도달 대기", model.data(
            model.index(0, 0), StepListModel.DetailRole,
        ))

    def test_jump_mode_cards_and_run_state_dropdown_values(self):
        from utils.mode_manager import ModeManager

        manager = ModeManager.instance()
        old_names = manager.to_dict()
        try:
            manager.set_name(3, "금형 대기 모드")
            step = {
                "type": "JMP", "name": "조건 점프", "condition": True,
                "cond_type": "MODE", "cond_value": 3, "cond_on": True,
                "target_idx": 0,
            }
            model = StepListModel()
            modes = [False] * 44
            modes[3] = True
            backend = SequenceEditorBackend(
                {"Main": [step]}, {}, {}, model, overlay=self.overlay,
                mode_data=modes,
            )

            self.assertEqual(backend.selectedModeIndex, 3)
            self.assertEqual(backend.selectedModeName, "금형 대기 모드")
            self.assertTrue(backend.modeCards[3]["state"])
            backend.selectModeCondition(7)
            self.assertEqual(step["cond_type"], "MODE")
            self.assertEqual(step["cond_value"], 7)

            backend.setCondType(3)
            backend.setRunStateIndex(2)
            self.assertEqual(step["cond_type"], "STATE")
            self.assertEqual(step["cond_value"], 2)
            self.assertTrue(step["cond_on"])
            self.assertEqual(backend.selectedRunStateIndex, 2)
            backend.setRunStateIndex(3)
            self.assertEqual(step["cond_value"], 3)
            self.assertEqual(backend.selectedRunStateIndex, 3)
            self.assertIn("알람발생", model.data(
                model.index(0, 0), StepListModel.DetailRole,
            ))
        finally:
            manager.load_from_dict(old_names)

    def test_jump_data_comparison_editor_uses_named_pendant_data(self):
        from utils.variable_store import VariableStore

        store = VariableStore.instance()
        data_id = store.add_data("비교용 카운터", initial=20)
        step = {
            "type": "JMP", "name": "데이터 조건", "condition": True,
            "cond_type": "DTCMP", "target_idx": 0,
        }
        model = StepListModel()
        backend = SequenceEditorBackend(
            {"Main": [step]}, {}, {}, model, overlay=self.overlay,
        )
        backend.selectCmpData(data_id)
        backend.setCmpOp(3)
        backend.setCmpConst(20)

        self.assertEqual(step["cmp_data_id"], data_id)
        self.assertEqual(step["cmp_dt_addr"], 60000 + data_id)
        self.assertEqual(step["cmp_op"], 3)
        self.assertEqual(step["cmp_const"], 20)
        self.assertEqual(backend.selectedCmpDataName, "비교용 카운터")

    def test_jump_position_condition_selects_point_axes_and_tolerance(self):
        step = {
            "type": "JMP", "name": "위치 검사", "condition": True,
            "cond_type": "INPUT", "target_idx": 0,
        }
        points = {
            "대기 위치": {"coords": [1, 2, 3, 4, 5, 6, 7, 8]},
            "취출 위치": {"coords": [11, 12, 13, 14, 15, 16, 17, 18]},
        }
        model = StepListModel()
        backend = SequenceEditorBackend(
            {"Main": [step]}, {}, points, model, overlay=self.overlay,
        )

        backend.setCondType(5)
        self.assertEqual(step["cond_type"], "POSITION")
        backend.setCondPointIndex(1)
        self.assertEqual(step["cond_point_name"], sorted(points)[1])
        backend.setPositionCondAxisActive(1, False)
        self.assertFalse(step["cond_position_axes"][1])
        self.overlay.number_result = (True, 0.25)
        backend.editPositionCondTolerance()
        self.assertEqual(step["cond_position_tolerance"], 0.25)
        self.assertIn("±0.250", model.data(
            model.index(0, 0), StepListModel.DetailRole,
        ))

    def test_monitor_program_cannot_add_or_save_position_steps(self):
        sequences = {"Main": [], "Monitor": []}
        model = StepListModel()
        backend = SequenceEditorBackend(
            sequences, {}, {}, model, overlay=self.overlay,
        )
        backend.selectSequence(backend.sequenceKeys.index("Monitor"))
        self.assertTrue(backend.isMonitorSequence)

        backend.addStep("POS")
        self.assertEqual(sequences["Monitor"], [])
        self.assertIn("위치이동(POS)", self.overlay.messages[-1][1])

        backend.addStep("OUT")
        self.assertEqual(sequences["Monitor"][0]["type"], "OUT")
        sequences["Monitor"].append({"type": "POS", "point_name": "P1"})
        accepted = []
        backend.acceptRequested.connect(lambda: accepted.append(True))
        backend.save()
        self.assertEqual(accepted, [])
        self.assertEqual(backend.selectedType, "POS")
        self.assertIn("저장", self.overlay.messages[-1][0])

    def test_add_step_inserts_below_selection_and_preserves_jump_target(self):
        self.steps[:] = [
            {"type": "OUT", "name": "첫 스텝", "out_type": 0, "port": 0},
            {"type": "TMR", "name": "대기", "time": 1.0},
            {"type": "JMP", "name": "반복", "target_idx": 1},
        ]
        self.model.reset_steps(self.steps)
        self.backend.selectStep(0)

        self.backend.addStep("IN")

        self.assertEqual([step["type"] for step in self.steps], ["OUT", "IN", "TMR", "JMP"])
        self.assertEqual(self.backend.selectedRow, 1)
        self.assertEqual(self.steps[3]["target_idx"], 2)

    def test_move_step_uses_incremental_model_move_and_reports_direction(self):
        self.steps[:] = [
            {"type": "OUT", "name": "A"},
            {"type": "OUT", "name": "B"},
            {"type": "OUT", "name": "C"},
        ]
        self.model.reset_steps(self.steps)
        moved = []
        invalidated_roles = []
        self.backend.stepMoved.connect(lambda row, direction: moved.append((row, direction)))
        self.model.dataChanged.connect(
            lambda _first, _last, roles: invalidated_roles.append(list(roles))
        )
        self.backend.selectStep(1)

        self.backend.moveSelected(-1)
        self.assertEqual([step["name"] for step in self.steps], ["B", "A", "C"])
        self.assertEqual(moved[-1], (0, -1))
        self.assertIn(StepListModel.NumberRole, invalidated_roles[-1])

        self.backend.moveSelected(1)
        self.assertEqual([step["name"] for step in self.steps], ["A", "B", "C"])
        self.assertEqual(moved[-1], (1, 1))

    def test_sequence_cards_describe_main_sub_and_monitor_programs(self):
        sequences = {
            "Main": [{"type": "OUT"}, {"type": "COMMENT", "text": "메모"}],
            "Sub1": [{"type": "TMR"}],
            "Monitor": [{"type": "IN"}],
        }
        backend = SequenceEditorBackend(
            sequences, {}, {}, StepListModel(), overlay=self.overlay,
        )
        cards = backend.sequenceCards
        self.assertEqual([card["name"] for card in cards], ["Main", "Sub1", "Monitor"])
        self.assertEqual([card["kind"] for card in cards], ["MAIN", "SUB", "MONITOR"])
        self.assertEqual(cards[0]["stepCount"], 1)

    def test_new_sequence_requests_name_before_creation(self):
        self.overlay.text_result = (True, "검사 공정")
        self.backend.addSequence()

        self.assertIn("검사 공정", self.backend.sequences)
        self.assertEqual(self.backend.current_sequence, "검사 공정")
        self.assertEqual(self.backend.model.rowCount(), 0)

    def test_sequence_rename_updates_every_call_reference(self):
        sequences = {
            "Main": [{"type": "CALL", "target_seq": "Sub1"}],
            "Sub1": [{"type": "END"}],
            "Sub2": [{"type": "CALL", "target_seq": "Sub1"}],
            "Monitor": [{"type": "CALL", "target_seq": "Sub1"}],
        }
        backend = SequenceEditorBackend(
            sequences, {}, {}, StepListModel(), overlay=self.overlay,
        )
        self.overlay.text_result = (True, "제품 배출")
        backend.renameSequence(backend.sequenceKeys.index("Sub1"))

        self.assertNotIn("Sub1", sequences)
        self.assertIn("제품 배출", sequences)
        self.assertEqual(sequences["Main"][0]["target_seq"], "제품 배출")
        self.assertEqual(sequences["Sub2"][0]["target_seq"], "제품 배출")
        self.assertEqual(sequences["Monitor"][0]["target_seq"], "제품 배출")

    def test_data_step_can_build_data_to_data_arithmetic_expression(self):
        from utils.variable_store import VariableStore

        store = VariableStore.instance()
        left = store.add_data("원본 수량 A", 12)
        right = store.add_data("원본 수량 B", 3)
        result = store.add_data("계산 결과", 0)
        step = {
            "type": "DAT", "name": "수량 계산", "data_id": result,
            "dat_dt_addr": 60000 + result, "dat_mode": "constant",
            "dat_op": 0, "dat_const": 0,
        }
        model = StepListModel()
        backend = SequenceEditorBackend(
            {"Main": [step]}, {}, {}, model, overlay=self.overlay,
        )

        backend.setDatMode(1)
        backend.selectDatLeftData(left)
        backend.selectDatRightData(right)
        backend.setDatMathOp(3)

        self.assertEqual(backend.selectedDatMode, 1)
        self.assertEqual(backend.selectedDatLeftDataId, left)
        self.assertEqual(backend.selectedDatRightDataId, right)
        self.assertEqual(backend.selectedDatMathOp, 3)
        self.assertEqual(backend.selectedDatLeftDataName, "원본 수량 A")
        self.assertEqual(backend.selectedDatRightDataName, "원본 수량 B")
        self.assertIn("계산 결과 = 원본 수량 A ÷ 원본 수량 B", model.data(
            model.index(0, 0), StepListModel.DetailRole,
        ))
        self.assertEqual(backend._variable_reference_count("data", left), 1)

    def test_data_plc_publish_address_is_chosen_by_operator(self):
        from utils.variable_store import VariableStore

        store = VariableStore.instance()
        data_id = store.add_data("외부 공개 검사", 42)
        self.overlay.number_result = (True, 700)
        self.backend.configureDataPublish(data_id)

        self.assertEqual(store.data_plc_address(data_id), 700)
        card = next(card for card in self.backend.dataCards if card["id"] == data_id)
        self.assertEqual(card["plc"], "DT700~DT701")

        self.backend.unpublishData(data_id)
        self.assertIsNone(store.data_plc_address(data_id))


if __name__ == "__main__":
    unittest.main()
