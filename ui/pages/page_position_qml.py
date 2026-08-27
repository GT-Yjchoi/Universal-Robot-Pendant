"""
위치설정 페이지 QML(GPU) — PagePosition drop-in.
화면, 미세조정, 선택, 재정렬 및 전체 화면 시퀀스 편집기는 QML로 렌더링한다.
티칭·실시간 추종·레시피 변경과 통신 로직은 Python 백엔드에 유지한다.

⚠ teach/값→PLC 포인트메모리 기록 경로는 실장비에서 정확도 검증 필수.
"""
import os

from PySide6.QtCore import (Qt, QObject, Signal, Slot, Property, QTimer,
                            QAbstractListModel, QModelIndex, QByteArray)

from ui.pages.page_manual_qml import ValveModel, ValveBackend

_QML_PATH = os.path.join(os.path.dirname(__file__), "PagePosition.qml")
_AXES = ["X", "Y", "Z", "Y2", "Z2", "θ", "R1", "R2"]


class AxisPosModel(QAbstractListModel):
    R_NM = Qt.UserRole + 1
    R_CUR = Qt.UserRole + 2
    R_SAV = Qt.UserRole + 3
    R_SPD = Qt.UserRole + 4
    R_VIS = Qt.UserRole + 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cur = ["0.000"] * 8
        self.sav = ["---"] * 8
        self.spd = ["-"] * 8
        self.vis = [True] * 8

    def rowCount(self, p=QModelIndex()):
        return 8

    def roleNames(self):
        return {self.R_NM: QByteArray(b"aname"),
                self.R_CUR: QByteArray(b"acur"),
                self.R_SAV: QByteArray(b"asaved"),
                self.R_SPD: QByteArray(b"aspeed"),
                self.R_VIS: QByteArray(b"avis")}

    def data(self, ix, role):
        i = ix.row()
        if not (0 <= i < 8):
            return None
        return {self.R_NM: _AXES[i], self.R_CUR: self.cur[i],
                self.R_SAV: self.sav[i], self.R_SPD: self.spd[i],
                self.R_VIS: self.vis[i]}.get(role)

    def _emit(self, roles):
        self.dataChanged.emit(self.index(0, 0), self.index(7, 0), roles)

    def set_cur(self, vals):
        for i, v in enumerate(vals):
            if i < 8:
                self.cur[i] = f"{v:.3f}"
        self._emit([self.R_CUR])

    def set_saved(self, coords, speeds):
        for i in range(8):
            self.sav[i] = f"{coords[i]:.3f}" if i < len(coords) else "---"
            self.spd[i] = f"{speeds[i]:.0f}" if i < len(speeds) else "-"
        self._emit([self.R_SAV, self.R_SPD])

    def clear_saved(self):
        self.sav = ["---"] * 8
        self.spd = ["-"] * 8
        self._emit([self.R_SAV, self.R_SPD])

    def set_vis(self, mask):
        for i in range(8):
            self.vis[i] = bool((mask >> i) & 1)
        self._emit([self.R_VIS])

    def set_one(self, row, sav=None, spd=None):
        if sav is not None:
            self.sav[row] = sav
        if spd is not None:
            self.spd[row] = spd
        self.dataChanged.emit(self.index(row, 0), self.index(row, 0),
                              [self.R_SAV, self.R_SPD])


class PreviewModel(QAbstractListModel):
    R_T = Qt.UserRole + 1
    R_HI = Qt.UserRole + 2
    R_C = Qt.UserRole + 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []     # [(text, is_comment)]
        self._hi = -1

    def rowCount(self, p=QModelIndex()):
        return len(self._rows)

    def roleNames(self):
        return {self.R_T: QByteArray(b"ptext"),
                self.R_HI: QByteArray(b"phi"),
                self.R_C: QByteArray(b"pcomment")}

    def data(self, ix, role):
        i = ix.row()
        if not (0 <= i < len(self._rows)):
            return None
        if role == self.R_T:
            return self._rows[i][0]
        if role == self.R_C:
            return self._rows[i][1]
        if role == self.R_HI:
            return i == self._hi
        return None

    def reset_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self._hi = -1
        self.endResetModel()

    def set_hi(self, row):
        if row == self._hi:
            return
        old = self._hi
        self._hi = row
        for r in (old, row):
            if 0 <= r < len(self._rows):
                self.dataChanged.emit(self.index(r, 0), self.index(r, 0),
                                      [self.R_HI])


class PosBackend(QObject):
    changed = Signal()      # 포인트/네비/시퀀스 표시 갱신
    monitorChanged = Signal()

    def __init__(self, page):
        super().__init__(page)
        self._p = page

    def _pn(self):
        return self._p._point_name()

    def _cp(self):
        return self._p._pt_index > 0

    def _cn(self):
        return self._p._pt_index < len(self._p._visible_points) - 1

    def _keys(self):
        return self._p._seq_keys()

    def _si(self):
        return self._p._seq_index()

    def _hi(self):
        return self._p._hi_row

    def _te(self):
        return not (self._p._current_op_status in (1, 2))

    pointName = Property(str, _pn, notify=changed)
    canPrev = Property(bool, _cp, notify=changed)
    canNext = Property(bool, _cn, notify=changed)
    seqKeys = Property(list, _keys, notify=changed)
    seqIndex = Property(int, _si, notify=changed)
    hiRow = Property(int, _hi, notify=changed)
    teachEnabled = Property(bool, _te, notify=changed)
    monitorRows = Property(
        list, lambda self: self._p._sequence_monitor_rows(), notify=changed,
    )
    monitorPrograms = Property(
        list, lambda self: self._p._sequence_monitor_programs(), notify=changed,
    )
    monitorRevision = Property(
        int, lambda self: self._p._sequence_monitor_revision,
        notify=monitorChanged,
    )

    @Slot()
    def prevPoint(self):
        self._p._nav_point(-1)

    @Slot()
    def nextPoint(self):
        self._p._nav_point(1)

    @Slot()
    def showNameCard(self):
        self._p._show_name_card_overlay()

    @Slot()
    def reorder(self):
        self._p._on_reorder_clicked()

    @Slot(int, str)
    def valueClicked(self, row, col):
        self._p._on_value_clicked(row, col)

    @Slot()
    def teachClicked(self):
        self._p._on_teach_clicked()

    @Slot(int)
    def seqChanged(self, idx):
        self._p._on_seq_selector_changed(idx)

    @Slot()
    def openSeqEditor(self):
        self._p._open_sequence_editor()

    @Slot(bool)
    def setSequenceMonitorVisible(self, visible):
        self._p._sequence_monitor_visible = bool(visible)
        if visible:
            self._p._sequence_monitor_revision += 1
            self.monitorChanged.emit()

    @Slot(str, int, result=bool)
    def isSequenceStepActive(self, program, step_index):
        instances = self._p._runtime_instances_by_sequence.get(str(program), {})
        return int(step_index) in instances.values()

    @Slot(str, result=bool)
    def isSequenceRunning(self, program):
        return bool(self._p._runtime_instances_by_sequence.get(str(program)))


class PagePositionQml(QObject):
    sig_sequence_changed = Signal()

    def __init__(self, sequence_data=None, position_points=None,
                 view_order_data=None, mode_data=None, timer_library=None,
                 plc_client=None, local_runtime=None, overlay=None,
                 sequence_editor=None):
        super().__init__()
        self.plc_client = plc_client
        self.local_runtime = local_runtime
        self.qml_overlay = overlay
        self.sequence_editor = sequence_editor
        self._active = False
        self.raw_sequence_ref = sequence_data if sequence_data is not None else []
        self.position_points = position_points if position_points is not None else {}
        self.view_order_data = view_order_data if view_order_data is not None else []
        self.mode_data = mode_data if mode_data is not None else []
        self.timer_library = timer_library if timer_library is not None else {}

        self.sequences = {}
        if isinstance(self.raw_sequence_ref, list):
            self.sequences["Main"] = self.raw_sequence_ref
        elif isinstance(self.raw_sequence_ref, dict):
            self.sequences = self.raw_sequence_ref
        else:
            self.sequences["Main"] = []
        if "Main" not in self.sequences:
            self.sequences["Main"] = []
        self.current_seq_key = "Main"

        self._visible_points = []
        self._pt_index = 0
        self._current_op_status = 0
        self._hi_row = -1
        self._last_hi = None
        # Keep execution highlights per program without taking ownership of
        # the operator's program selector during parallel execution.
        self._runtime_steps_by_sequence = {}
        # One program may have several simultaneous parallel CALL instances.
        # Keep their positions separately so the monitor does not rapidly
        # overwrite one Sub program highlight with another instance's step.
        self._runtime_instances_by_sequence = {}
        self._sequence_monitor_visible = False
        self._sequence_monitor_revision = 0

        self._init_points_from_sequence()

        self._axis = AxisPosModel(self)
        self._prev = PreviewModel(self)
        self._valve_m = ValveModel(self)
        self._valve_be = ValveBackend(plc_client, self._valve_m, self)
        self._valve_be.load_configs()
        self._be = PosBackend(self)

        if self.plc_client:
            self.plc_client.sig_monitor_data.connect(self._update_realtime_values)
        if self.local_runtime:
            self.local_runtime.sig_monitor_data.connect(self._update_realtime_values)
        self._refresh_ui()

    # ---- PagePosition 와 동일 ----
    def _init_points_from_sequence(self):
        for seq_list in self.sequences.values():
            for step in seq_list:
                if step.get("type") == "POS":
                    p_name = step.get("point_name", step.get("name", "Point"))
                    if not p_name:
                        p_name = "Point_1"
                    if p_name not in self.position_points:
                        self.position_points[p_name] = {
                            "coords": list(step.get("coords", [0.0] * 8)),
                            "speeds": list(step.get("speeds", [100.0] * 8))}

    def _is_point_visible(self, name):
        vm = self.position_points.get(name, {}).get("visible_mode", -1)
        if isinstance(vm, int):
            if vm < 0:
                return True
            return bool(self.mode_data[vm]) if self.mode_data and vm < len(self.mode_data) else False
        if not vm:
            return True
        return any(bool(self.mode_data[i]) for i in vm
                   if self.mode_data and i < len(self.mode_data))

    def _recompute_visible_points(self, keep_name=None):
        all_points = sorted(list(self.position_points.keys()))
        valid_custom = [n for n in self.view_order_data if n in all_points]
        new_names = [n for n in all_points if n not in valid_custom]
        self.view_order_data.clear()
        self.view_order_data.extend(valid_custom + new_names)
        self._visible_points = [n for n in self.view_order_data
                                if self._is_point_visible(n)]
        if keep_name and keep_name in self._visible_points:
            self._pt_index = self._visible_points.index(keep_name)
        else:
            self._pt_index = min(self._pt_index,
                                 max(0, len(self._visible_points) - 1))

    def _point_name(self):
        if not self._visible_points:
            return "위치 없음"
        if 0 <= self._pt_index < len(self._visible_points):
            return self._visible_points[self._pt_index]
        return "위치 없음"

    def _seq_keys(self):
        keys = sorted([
            k for k in self.sequences.keys() if k not in {"Main", "Monitor"}
        ])
        return ["Main"] + keys

    def _seq_index(self):
        ks = self._seq_keys()
        return ks.index(self.current_seq_key) if self.current_seq_key in ks else 0

    def _refresh_ui(self):
        prev_name = self._point_name()
        self._recompute_visible_points(
            keep_name=prev_name if prev_name != "위치 없음" else None)
        self._update_preview_list()
        self._load_selected_point()
        self._be.changed.emit()

    def _load_selected_point(self):
        name = self._point_name()
        if name == "위치 없음" or name not in self.position_points:
            self._axis.clear_saved()
            return
        d = self.position_points[name]
        self._axis.set_saved(d.get("coords", [0.0] * 8),
                             d.get("speeds", [100.0] * 8))

    def _nav_point(self, delta):
        n = len(self._visible_points)
        if n == 0:
            return
        self._pt_index = max(0, min(n - 1, self._pt_index + delta))
        self._load_selected_point()
        self._be.changed.emit()

    def _on_seq_selector_changed(self, idx):
        ks = self._seq_keys()
        if 0 <= idx < len(ks) and ks[idx] in self.sequences:
            self.current_seq_key = ks[idx]
            self._update_preview_list()
            if self._current_op_status in (1, 2):
                self._highlight_step(
                    self._runtime_steps_by_sequence.get(self.current_seq_key, -1)
                )
            self._be.changed.emit()

    # ---- preview 빌드 (PagePosition 와 동일 데코레이션) ----
    def _out_port_name(self, out_type, bit_index):
        if out_type == 2:
            try:
                from utils.internal_bit_names import get_name
                nm = get_name(f"M{bit_index:02d}")
                return f"M{bit_index:02d} [{nm}]" if nm else f"M{bit_index:02d}"
            except Exception:
                return f"M{bit_index:02d}"
        try:
            from utils.io_manager import IOManager
            mgr = IOManager.instance()
            slot = mgr.group_slot(out_type)
            return mgr.display_label(False, slot * 16 + bit_index)
        except Exception:
            pass
        return f"Y{bit_index:02X}"

    def _in_port_name(self, in_type, port_index):
        if in_type == 2 or 100 <= port_index <= 131:
            bit_idx = port_index - 100 if port_index >= 100 else port_index
            try:
                from utils.internal_bit_names import get_name
                nm = get_name(f"M{bit_idx:02d}")
                if nm:
                    return f"M{bit_idx:02d}: {nm}"
            except Exception:
                pass
            return f"M{bit_idx:02d}"
        try:
            from utils.io_manager import IOManager
            mgr = IOManager.instance()
            logical = port_index - 32 if in_type == 1 and port_index >= 32 else port_index
            slot = mgr.group_slot(in_type)
            return mgr.display_label(True, slot * 16 + logical)
        except Exception:
            pass
        return f"X{port_index:02X}" if port_index < 100 else f"포트{port_index}"

    def _jmp_target_name(self, current_steps, target_idx):
        n = 0
        for step in current_steps:
            if step.get("type") == "COMMENT":
                continue
            if n == target_idx:
                return step.get("name", f"스텝{target_idx}")
            n += 1
        return f"스텝{target_idx}"

    def _preview_entries(self, sequence_name):
        rows = []
        current_steps = self.sequences.get(sequence_name, [])
        step_num = 0
        executable_index = 0
        for step in current_steps:
            stype = step.get("type", "")
            if stype == "COMMENT":
                rows.append({
                    "text": f"// {step.get('text', '')}",
                    "comment": True,
                    "stepIndex": -1,
                })
                continue
            step_num += 1
            name = step.get("name", "Unknown")
            if stype in ("POS", "WPOS"):
                p_name = step.get("point_name", "")
                if p_name and p_name != name:
                    name = f"{name}  ({p_name})"
            elif stype == "CALL":
                tgt = step.get("target_seq", "")
                if tgt:
                    name = f"{name}  ({tgt})"
            elif stype == "OUT":
                ot = int(step.get("out_type", 0))
                port = int(step.get("port", 0))
                on_val = step.get("on", step.get("on_off", False))
                name = f"{name}  ({self._out_port_name(ot, port)} {'ON' if on_val else 'OFF'})"
            elif stype == "IN":
                in_type = int(step.get("in_type", 0))
                port = int(step.get("port", step.get("io_index", 0)))
                on_val = step.get("on", step.get("on_off", True))
                name = f"{name}  ({self._in_port_name(in_type, port)} {'ON' if on_val else 'OFF'})"
            elif stype == "JMP":
                ti = int(step.get("target_idx", 0))
                tn = self._jmp_target_name(current_steps, ti)
                if tn:
                    name = f"{name}  ({tn})"
            elif stype == "TMR":
                ref = step.get("timer_ref", "")
                if ref:
                    name = f"{name}  ({ref})"
            rows.append({
                "text": f"[{step_num:02d}] {name}",
                "comment": False,
                "stepIndex": executable_index,
            })
            executable_index += 1
        return rows

    def _update_preview_list(self):
        self._last_hi = None
        rows = self._preview_entries(self.current_seq_key)
        self._prev.reset_rows([
            (entry["text"], entry["comment"]) for entry in rows
        ])
        self._hi_row = -1

    def _sequence_monitor_rows(self):
        rows = []
        for sequence_name in self._seq_keys():
            active_step = self._runtime_steps_by_sequence.get(sequence_name, -1)
            kind = "MAIN" if sequence_name == "Main" else (
                "MONITOR" if sequence_name == "Monitor" else "SUB"
            )
            rows.append({
                "header": True,
                "program": sequence_name,
                "kind": kind,
                "text": sequence_name,
                "comment": False,
                "active": active_step >= 0,
                "stepIndex": -1,
            })
            for entry in self._preview_entries(sequence_name):
                rows.append({
                    "header": False,
                    "program": sequence_name,
                    "kind": kind,
                    "text": entry["text"],
                    "comment": entry["comment"],
                    "stepIndex": entry["stepIndex"],
                    "active": (
                        entry["stepIndex"] >= 0
                        and entry["stepIndex"] == active_step
                    ),
                })
        return rows

    def _sequence_monitor_programs(self):
        programs = []
        for sequence_name in self._seq_keys():
            kind = "MAIN" if sequence_name == "Main" else "SUB"
            programs.append({
                "program": sequence_name,
                "kind": kind,
                "steps": [
                    {
                        "text": entry["text"],
                        "comment": entry["comment"],
                        "stepIndex": entry["stepIndex"],
                    }
                    for entry in self._preview_entries(sequence_name)
                ],
            })
        return programs

    # ---- 실시간 (PagePosition._update_realtime_values 와 동일) ----
    def _update_realtime_values(self, data):
        is_monitor = isinstance(data, dict)
        has_runtime_state = is_monitor and 'op_status' in data

        # PLC monitor packets and pendant-runtime packets arrive independently.
        # The PLC-only packet intentionally has no op_status/current_step, so it
        # must not be treated as an idle packet or it will clear the execution
        # highlight and unlock the controls between every runtime update.
        if has_runtime_state:
            self._current_op_status = data['op_status']
            self._valve_be.set_locked(self._current_op_status in (1, 2))

            current_step = data.get('current_step', -1)
            op_status = self._current_op_status
            background_sequence = bool(data.get('background_sequence', False))
            target_name = data.get('local_sequence') or "Main"

            if background_sequence:
                if (target_name and target_name != "Monitor"
                        and target_name in self.sequences):
                    self._track_runtime_step(target_name, current_step, data)
            elif op_status in (1, 2):
                if data.get('pendant_sequence') or data.get('local_dio'):
                    target_name = data.get('local_sequence') or "Main"
                else:
                    current_slot = data.get('sub_seq_idx', 0)
                    target_name = self._get_seq_name_by_slot(current_slot)
                if target_name and target_name in self.sequences:
                    self._track_runtime_step(target_name, current_step, data)
            else:
                # Main stopping must not erase a Sub independently running
                # under the always-on Monitor executor.
                self._clear_runtime_source("main")

            if self._active:
                self._be.changed.emit()
                self._highlight_step(
                    self._runtime_steps_by_sequence.get(
                        self.current_seq_key, -1
                    )
                )
            if self._sequence_monitor_visible:
                self._sequence_monitor_revision += 1
                self._be.monitorChanged.emit()

        if not self._active:
            return
        axis_data = data.get('axis_pos', []) if is_monitor else data
        self._axis.set_cur(axis_data)

        if is_monitor and 'outputs' in data:
            outs = data['outputs']
            if outs and len(outs) >= 2:
                self._valve_be.sync_from_outputs(outs)

    def _track_runtime_step(self, target_name, current_step, data):
        execution_id = int(data.get('local_execution_id', 0) or 0)
        source = str(data.get('local_execution_source', 'main') or 'main')
        instance_key = (source, execution_id)
        instances = self._runtime_instances_by_sequence.setdefault(
            target_name, {}
        )
        if current_step >= 0:
            instances[instance_key] = current_step
            self._runtime_steps_by_sequence[target_name] = current_step
            return
        instances.pop(instance_key, None)
        if instances:
            self._runtime_steps_by_sequence[target_name] = next(
                reversed(instances.values())
            )
        else:
            self._runtime_instances_by_sequence.pop(target_name, None)
            self._runtime_steps_by_sequence.pop(target_name, None)

    def _clear_runtime_source(self, source):
        source = str(source)
        for target_name in list(self._runtime_instances_by_sequence):
            instances = self._runtime_instances_by_sequence[target_name]
            for key in list(instances):
                if key[0] == source:
                    instances.pop(key, None)
            if instances:
                self._runtime_steps_by_sequence[target_name] = next(
                    reversed(instances.values())
                )
            else:
                self._runtime_instances_by_sequence.pop(target_name, None)
                self._runtime_steps_by_sequence.pop(target_name, None)

    def _get_seq_name_by_slot(self, slot_id):
        MONITOR_KEY = "Monitor"
        if slot_id == 0:
            return "Main"
        if slot_id == 39:
            return MONITOR_KEY if MONITOR_KEY in self.sequences else None
        reserved = {"Main", MONITOR_KEY}
        subs = sorted([k for k in self.sequences.keys() if k not in reserved])
        idx = slot_id - 1
        return subs[idx] if 0 <= idx < len(subs) else None

    def _highlight_step(self, step_idx):
        list_row = -1
        if step_idx >= 0:
            n = 0
            for i, s in enumerate(self.sequences.get(self.current_seq_key, [])):
                if s.get("type") == "COMMENT":
                    continue
                if n == step_idx:
                    list_row = i
                    break
                n += 1
        if self._last_hi == list_row:
            return
        self._last_hi = list_row
        self._hi_row = list_row
        self._prev.set_hi(list_row)
        self._be.changed.emit()

    # ---- 값 편집 (PagePosition._on_value_clicked 와 동일) ----
    def _on_value_clicked(self, row_idx, col_type):
        if not self._visible_points:
            return
        selected_point = self._point_name()
        if selected_point not in self.position_points:
            return
        if col_type == "coords" and self._current_op_status in (1, 2):
            self._open_fine_adjust_overlay(selected_point, row_idx)
            return
        if col_type == "coords":
            current_val_str = self._axis.sav[row_idx]
        else:
            current_val_str = self._axis.spd[row_idx]
        def finished(accepted, value):
            if accepted: self._apply_edited_value(selected_point, row_idx, col_type, value)
        if col_type == "coords":
            from utils.axis_limits import get_axis_strokes
            maximum = get_axis_strokes()[row_idx] if 0 <= row_idx < 8 else 1000.0
        else:
            maximum = 100
        self.qml_overlay.request_number(
            f"{selected_point} {_AXES[row_idx]} {col_type}", float(current_val_str),
            decimal=col_type == "coords", minimum=0 if col_type == "coords" else 1,
            maximum=maximum, callback=finished,
        )

    def _apply_edited_value(self, selected_point, row_idx, col_type, new_val):
        new_val = float(new_val)
        if col_type == "speed":
            try:
                old_speed = int(float(self._axis.spd[row_idx]))
            except Exception:
                old_speed = 0
            new_val = max(1, min(100, int(new_val)))
        elif col_type == "coords":
            from utils.axis_limits import get_axis_strokes
            stroke = get_axis_strokes()[row_idx] if 0 <= row_idx < 8 else 1000.0
            if new_val < 0.0 or new_val > stroke:
                self.qml_overlay.show_message(
                    "입력 범위 초과",
                    f"스트로크 한계를 벗어났습니다.\n허용 범위: 0 ~ {stroke:.3f} mm\n입력값: {new_val:.3f} mm",
                    error=True,
                )
                return
        if col_type == "coords":
            self.position_points[selected_point]["coords"][row_idx] = new_val
            for seq in self.sequences.values():
                for step in seq:
                    if step.get("type") == "POS":
                        p_name = step.get("point_name", step.get("name"))
                        if p_name == selected_point and "coords" in step:
                            step["coords"][row_idx] = new_val
        elif col_type == "speed":
            if "speeds" not in self.position_points[selected_point]:
                self.position_points[selected_point]["speeds"] = [100] * 8
            self.position_points[selected_point]["speeds"][row_idx] = new_val
        self._load_selected_point()
        self.sig_sequence_changed.emit()
        try:
            from utils.op_history import record as op_record
            axis = _AXES[row_idx] if 0 <= row_idx < 8 else f"축{row_idx+1}"
            if col_type == "coords":
                op_record("POS", f"{selected_point} {axis}축 기억위치 변경 → {new_val:.3f} mm")
            elif col_type == "speed":
                op_record("SPEED", f"{selected_point} {axis}축 속도 {old_speed} → {new_val} %")
        except Exception:
            pass

    def _open_fine_adjust_overlay(self, selected_point, row_idx):
        coords = self.position_points[selected_point].setdefault("coords", [0.0] * 8)
        cur = coords[row_idx] if row_idx < len(coords) else 0.0
        axis_name = _AXES[row_idx] if 0 <= row_idx < 8 else f"{row_idx+1}"
        from utils.axis_limits import get_axis_strokes
        stroke = get_axis_strokes()[row_idx] if 0 <= row_idx < 8 else 1000.0
        self.qml_overlay.request_fine_adjust(
            f"{axis_name}축 미세조정", cur, 0, stroke,
            callback=lambda delta: self._apply_fine_adjust(selected_point, row_idx, delta),
        )

    def _apply_fine_adjust(self, selected_point, row_idx, delta):
        if selected_point not in self.position_points:
            return
        coords = self.position_points[selected_point].setdefault("coords", [0.0] * 8)
        cur = coords[row_idx] if row_idx < len(coords) else 0.0
        new_val = round(cur + delta, 3)
        from utils.axis_limits import get_axis_strokes
        stroke = get_axis_strokes()[row_idx] if 0 <= row_idx < 8 else 1000.0
        if new_val < 0.0 or new_val > stroke:
            self.qml_overlay.show_message(
                "입력 범위 초과",
                f"스트로크 한계를 벗어났습니다.\n허용 범위: 0 ~ {stroke:.3f} mm\n입력값: {new_val:.3f} mm", error=True,
            )
            return None
        coords[row_idx] = new_val
        for seq in self.sequences.values():
            for step in seq:
                if step.get("type") == "POS":
                    p_name = step.get("point_name", step.get("name"))
                    if p_name == selected_point and "coords" in step:
                        step["coords"][row_idx] = new_val
        self._axis.set_one(row_idx, sav=f"{new_val:.3f}")
        self.sig_sequence_changed.emit()
        try:
            from utils.op_history import record as op_record
            axis = _AXES[row_idx] if 0 <= row_idx < 8 else f"축{row_idx+1}"
            op_record("POS", f"(자동중) {selected_point} {axis}축 미세조정 {delta:+g} → {new_val:.3f} mm")
        except Exception:
            pass
        return new_val

    # ---- teach (PagePosition._on_teach_clicked 와 동일) ----
    def _on_teach_clicked(self):
        if self._current_op_status in (1, 2):
            return
        if not self._visible_points:
            return
        target_point_name = self._point_name()
        if target_point_name not in self.position_points:
            return
        new_coords = []
        for s in self._axis.cur:
            try:
                new_coords.append(float(s))
            except ValueError:
                new_coords.append(0.0)
        self.position_points[target_point_name]["coords"] = list(new_coords)
        for seq in self.sequences.values():
            for step in seq:
                if step.get("type") == "POS":
                    p_name = step.get("point_name", step.get("name"))
                    if p_name == target_point_name:
                        step["coords"] = list(new_coords)
        self._load_selected_point()
        self.sig_sequence_changed.emit()
        if self._pt_index + 1 < len(self._visible_points):
            self._pt_index += 1
            self._load_selected_point()
            self._be.changed.emit()

    # ---- 오버레이/다이얼로그 (재사용) ----
    def _show_name_card_overlay(self):
        if not self._visible_points:
            return
        ordered = list(self._visible_points)
        current = self._point_name()
        current_index = ordered.index(current) if current in ordered else -1
        self.qml_overlay.request_selection(
            "포인트 선택", ordered, current_index,
            callback=lambda accepted, index, name: self._on_point_selected_from_card(name) if accepted else None,
        )

    def _on_point_selected_from_card(self, name):
        if name in self._visible_points:
            self._pt_index = self._visible_points.index(name)
            self._load_selected_point()
            self._be.changed.emit()

    def _on_reorder_clicked(self):
        def finished(accepted, new_order):
            if not accepted: return
            self.view_order_data.clear()
            self.view_order_data.extend(new_order)
            self._refresh_ui()
            self.sig_sequence_changed.emit()
        self.qml_overlay.request_reorder(
            "포인트 순서 변경", list(self.view_order_data), callback=finished,
        )

    def _open_sequence_editor(self):
        if self.sequence_editor is None:
            return
        def finished(accepted, editor):
            if not accepted:
                return
            new_seqs = editor.get_sequence_data()
            new_points = editor.get_position_points()
            self.sequences.clear()
            self.sequences.update(new_seqs)
            if isinstance(self.raw_sequence_ref, list):
                self.raw_sequence_ref.clear()
                if "Main" in self.sequences:
                    self.raw_sequence_ref.extend(self.sequences["Main"])
            self.position_points.clear()
            self.position_points.update(new_points)
            refresh_monitor = getattr(
                self.local_runtime, "refresh_monitor_sequence", None
            )
            if callable(refresh_monitor):
                refresh_monitor()
            self._refresh_ui()
            self.sig_sequence_changed.emit()
        self.sequence_editor.open(
            sequence_data=self.sequences,
            position_points=self.position_points,
            timer_library=self.timer_library,
            mode_data=self.mode_data,
            callback=finished,
        )

    # ---- 호환 (main_window 가 _refresh_ui() 호출) ----
    def activate(self):
        self._active = True
        self._refresh_ui()
        if self._visible_points:
            self._pt_index = 0
            self._load_selected_point()
        QTimer.singleShot(0, self._check_axis_visibility)

    def deactivate(self):
        self._active = False

    def _check_axis_visibility(self):
        try:
            from utils.json_utils import load_json
            from utils.paths import get_settings_path
            uses = (load_json(get_settings_path()) or {}).get("axis_uses", [True] * 8)
            mask = sum((1 << i) for i, enabled in enumerate(uses[:8]) if enabled)
            self._axis.set_vis(mask)
        except Exception as e:
            print(f"[Position] 축 표시 갱신 실패: {e}")
