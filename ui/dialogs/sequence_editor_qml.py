"""QML sequence editor with a Python data model and legacy recipe compatibility."""

from __future__ import annotations

import copy

from PySide6.QtCore import (
    QByteArray,
    Property,
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    Signal,
    Slot,
)

from ui.sequence_schema import MONITOR_SEQ_KEY, normalize_all_sequences
from ui.alarm_catalog import USER_ALARMS

try:
    from utils.io_manager import IOManager
except Exception:
    IOManager = None

from utils.variable_store import (
    VariableStore, RESET_LABELS, MAX_BITS, MAX_DATA,
    PLC_DATA_START, PLC_DATA_LAST_START,
)

try:
    from utils.mode_manager import ModeManager, TOTAL_MODE_COUNT
except Exception:
    ModeManager = None
    TOTAL_MODE_COUNT = 44


_COLORS = {
    "POS": "#468CFF", "WPOS": "#36B7C9", "OUT": "#FFA500", "IN": "#FF69B4",
    "TMR": "#F1C40F", "JMP": "#00E5FF", "CALL": "#FF00FF",
    "DAT": "#00FF9C", "END": "#FF4646", "COMMENT": "#FFD700",
}

_AXIS_NAMES = ("X", "Y", "Z", "Y2", "Z2", "θ", "R1", "R2")
_MAX_POSITION_POINTS = 60


def _physical_io_label(prefix: str, list_index: int) -> str:
    try:
        manager = IOManager.instance() if IOManager else None
        if manager is not None:
            return manager.display_label(prefix == "X", list_index)
    except Exception:
        pass
    address = list_index if list_index < 16 else 0x20 + (list_index - 16)
    return f"{prefix}{address:02X}"


def _physical_io_labels(prefix: str) -> list[str]:
    try:
        manager = IOManager.instance() if IOManager else None
        count = manager.point_count(prefix == "X") if manager else 32
    except Exception:
        count = 32
    return [_physical_io_label(prefix, index) for index in range(count)]


def _internal_bit_labels() -> list[str]:
    store = VariableStore.instance()
    return [store.bit_name(item_id) for item_id in store.bit_ids()]


def _internal_bit_ids() -> list[int]:
    return VariableStore.instance().bit_ids()


def _data_labels() -> list[str]:
    store = VariableStore.instance()
    return [store.data_name(item_id) for item_id in store.data_ids()]


def _data_ids() -> list[int]:
    return VariableStore.instance().data_ids()


def _bit_label(item_id: int) -> str:
    return VariableStore.instance().bit_name(item_id)


def _data_label(item_id: int) -> str:
    return VariableStore.instance().data_name(item_id)


def _step_io_label(kind: str, group: int, logical: int) -> str:
    if group == 2:
        return _bit_label(logical)
    try:
        slot = IOManager.group_slot(group) if IOManager else (1 if group == 1 else 0)
    except Exception:
        slot = 0
    list_index = slot * 16 + logical
    return _physical_io_label("Y" if kind == "OUT" else "X", list_index)


def _executable_rows(steps) -> list[int]:
    return [
        index for index, step in enumerate(steps)
        if str(step.get("type", "")).upper() != "COMMENT"
    ]


def _display_number_for_raw_row(steps, raw_row: int) -> int:
    rows = _executable_rows(steps)
    if not rows:
        return 0
    target = next((row for row in rows if row >= raw_row), rows[-1])
    return rows.index(target) + 1


def _summary(step: dict, row: int, steps=None) -> str:
    name, detail = _name_and_detail(step, row, steps)
    return f"{name}  ·  {detail}" if detail else name


def _name_and_detail(step: dict, row: int, steps=None) -> tuple[str, str]:
    kind = str(step.get("type", "")).upper()
    if kind == "COMMENT":
        return str(step.get("text", "메모")), "코멘트"
    name = step.get("name") or f"{kind} {row + 1}"
    if kind in ("OUT", "IN"):
        channel = int(step.get("port", step.get("dio_channel", 0)))
        state = "ON" if step.get("on", True) else "OFF"
        group = int(step.get("out_type" if kind == "OUT" else "in_type", 0))
        logical = channel
        if kind == "IN" and group == 1 and logical >= 32:
            logical -= 32
        elif kind == "IN" and group == 2 and logical >= 100:
            logical -= 100
        if group == 2:
            bit_id = int(step.get("bit_id", logical))
            address = _bit_label(bit_id) if bit_id >= 0 else "내부비트 미선택"
        else:
            address = _step_io_label(kind, group, logical)
        detail = f"{address}  ·  {state}"
        if kind == "OUT" and step.get("delay_enable", False):
            detail += f"  ·  {float(step.get('delay_time', 0)):.2f}초 지연"
        elif kind == "IN":
            if step.get("timeup_enabled", False):
                detail += f"  ·  {float(step.get('timeup_time', 0)):.2f}초 유지"
            if not step.get("timeout_enabled", False):
                return str(name), detail
            action = {
                "continue": "알람 후 진행여부 선택",
                "ask": "알람 후 정지",
                "alarm_go": "알람 후 진행",
            }.get(
                str(step.get("timeout_action", "continue")),
                "알람 후 진행여부 선택",
            )
            alarm = f" A-{int(step.get('timeout_alarm_no', 1)):03d}"
            detail += f"  ·  최대 {float(step.get('timeout', 5)):.1f}초 후{alarm} {action}"
        return str(name), detail
    if kind == "TMR":
        if step.get("tmr_mode", "simple") == "hold":
            channel = int(step.get("port", 0))
            group = int(step.get("in_type", 0))
            if group == 1 and channel >= 32:
                channel -= 32
            elif group == 2 and channel >= 100:
                channel -= 100
            address = _step_io_label("IN", group, channel)
            state = "ON" if step.get("on", True) else "OFF"
            return str(name), f"{address} {state} 유지  ·  {float(step.get('time', 0)):.3f}초"
        ref = str(step.get("timer_ref", ""))
        prefix = f"{ref}  ·  " if ref else ""
        return str(name), f"{prefix}{float(step.get('time', 0)):.3f}초"
    if kind == "JMP":
        suffix = " · 조건부" if step.get("condition", False) else ""
        if step.get("condition", False):
            cond_type = str(step.get("cond_type", "INPUT")).upper()
            cond_value = int(step.get("cond_value", 0))
            expected = "ON" if step.get("cond_on", True) else "OFF"
            if cond_type == "INPUT":
                cond_group = int(step.get("cond_io_type", 0))
                try:
                    slot = IOManager.group_slot(cond_group) if IOManager else 0
                except Exception:
                    slot = 0
                suffix += f" · {_physical_io_label('X', slot * 16 + max(0, min(15, cond_value)))} {expected}"
            elif cond_type == "VALVE":
                logical = cond_value - 32 if cond_value >= 32 else cond_value
                suffix += f" · {_physical_io_label('X', 16 + max(0, min(15, logical)))} {expected}"
            elif cond_type == "BIT":
                logical = cond_value - 100 if cond_value >= 100 else cond_value
                bit_id = int(step.get("cond_bit_id", logical))
                suffix += f" · {_bit_label(bit_id)} {expected}"
            elif cond_type == "STATE":
                state_labels = ("정지", "자동", "확인운전", "알람발생")
                suffix += f" · {state_labels[max(0, min(3, cond_value))]}"
            elif cond_type in ("DTCMP", "DT", "DATA"):
                data_id = int(step.get(
                    "cmp_data_id", int(step.get("cmp_dt_addr", 60000)) - 60000,
                ))
                operators = ("=", "!=", ">", ">=", "<", "<=")
                operator = operators[max(0, min(5, int(step.get("cmp_op", 0))))]
                data_name = _data_label(data_id) if data_id >= 0 else "데이터 미선택"
                suffix += f" · {data_name} {operator} {int(step.get('cmp_const', 0))}"
            elif cond_type in ("POSITION", "POINT", "AXISPOS"):
                point_name = str(step.get("cond_point_name", "위치 미지정"))
                axes = list(step.get("cond_position_axes", [True] * 8))
                axes = (axes + [False] * 8)[:8]
                axis_names = ", ".join(
                    _AXIS_NAMES[index] for index in range(8) if axes[index]
                ) or "축 미선택"
                tolerance = float(step.get("cond_position_tolerance", 0.1))
                state = "일치" if step.get("cond_on", True) else "불일치"
                suffix += (
                    f" · {point_name} {state} · {axis_names} · ±{tolerance:.3f}"
                )
        target = int(step.get("target_idx", 0))
        display = _display_number_for_raw_row(steps, target) if steps is not None else target + 1
        return str(name), f"{display}번으로 이동{suffix}"
    if kind == "CALL":
        suffix = " · 동시 실행" if step.get("parallel", False) else ""
        return str(name), f"{step.get('target_seq', '미지정')}{suffix}"
    if kind == "POS":
        suffix = " · 동시 이행" if not step.get("wait_completion", True) else ""
        return str(name), f"{step.get('point_name', '위치 미지정')}{suffix}"
    if kind == "WPOS":
        point_name = str(step.get("point_name", "위치 미지정"))
        axes = (list(step.get("active_axes", [True] * 8)) + [False] * 8)[:8]
        axis_names = ", ".join(
            _AXIS_NAMES[index] for index in range(8) if axes[index]
        ) or "축 미선택"
        tolerance = float(step.get("position_tolerance", 0.1))
        timeout = float(step.get("timeout", 5.0))
        return str(name), (
            f"{point_name} 도달 대기 · {axis_names} · ±{tolerance:.3f} · 최대 {timeout:.3f}초"
        )
    if kind == "DAT":
        data_id = int(step.get("data_id", int(step.get("dat_dt_addr", 60000)) - 60000))
        data_name = _data_label(data_id) if data_id >= 0 else "데이터 미선택"
        if str(step.get("dat_mode", "constant")) == "data":
            left_id = int(step.get("dat_left_data_id", -1))
            right_id = int(step.get("dat_right_data_id", -1))
            left_name = _data_label(left_id) if left_id >= 0 else "데이터 A 미선택"
            right_name = _data_label(right_id) if right_id >= 0 else "데이터 B 미선택"
            math_ops = ("+", "−", "×", "÷")
            math_op = max(0, min(3, int(step.get("dat_math_op", 0))))
            return str(name), f"{data_name} = {left_name} {math_ops[math_op]} {right_name}"
        ops = ("=", "+=", "-=")
        op = max(0, min(2, int(step.get("dat_op", 0))))
        return str(name), f"{data_name} {ops[op]} {int(step.get('dat_const', 0))}"
    if kind == "END":
        return str(name), "시퀀스 종료"
    return str(name), ""


class StepListModel(QAbstractListModel):
    TypeRole = Qt.UserRole + 1
    SummaryRole = Qt.UserRole + 2
    ColorRole = Qt.UserRole + 3
    NameRole = Qt.UserRole + 4
    DetailRole = Qt.UserRole + 5
    NumberRole = Qt.UserRole + 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps: list[dict] = []

    def roleNames(self):
        return {
            self.TypeRole: QByteArray(b"stepType"),
            self.SummaryRole: QByteArray(b"summary"),
            self.ColorRole: QByteArray(b"stepColor"),
            self.NameRole: QByteArray(b"stepName"),
            self.DetailRole: QByteArray(b"stepDetail"),
            self.NumberRole: QByteArray(b"displayNumber"),
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self.steps)

    def data(self, index, role):
        row = index.row()
        if not 0 <= row < len(self.steps):
            return None
        step = self.steps[row]
        kind = str(step.get("type", "")).upper()
        name, detail = _name_and_detail(step, row, self.steps)
        display_number = "" if kind == "COMMENT" else str(
            _display_number_for_raw_row(self.steps, row)
        )
        return {
            self.TypeRole: kind,
            self.SummaryRole: _summary(step, row, self.steps),
            self.ColorRole: _COLORS.get(kind, "#95A5A6"),
            self.NameRole: name,
            self.DetailRole: detail,
            self.NumberRole: display_number,
        }.get(role)

    def reset_steps(self, steps):
        self.beginResetModel()
        self.steps = steps
        self.endResetModel()

    def refresh(self, row):
        if 0 <= row < len(self.steps):
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, [
                self.TypeRole, self.SummaryRole, self.ColorRole,
                self.NameRole, self.DetailRole, self.NumberRole,
            ])


class SequenceEditorBackend(QObject):
    changed = Signal()
    selectionChanged = Signal()
    stepMoved = Signal(int, int)  # selected raw row, direction (-1=up, +1=down)
    timerLibraryChanged = Signal()
    variableLibraryChanged = Signal()
    acceptRequested = Signal()
    rejectRequested = Signal()

    def __init__(self, sequences, timer_library, position_points, model, parent=None,
                 overlay=None, mode_data=None):
        super().__init__(parent)
        self.sequences = sequences
        self.timer_library = timer_library
        self.position_points = position_points
        VariableStore.instance().ensure_legacy_references(sequences)
        self.model = model
        self.overlay = overlay
        self.mode_data = mode_data if mode_data is not None else []
        self.enabled_axes = self._load_enabled_axes()
        self.current_sequence = "Main" if "Main" in sequences else next(iter(sequences))
        self.model.reset_steps(self.sequences[self.current_sequence])
        self.selected_row = 0 if self.model.steps else -1

    def _keys(self):
        reserved = {"Main", MONITOR_SEQ_KEY}
        keys = ["Main"] if "Main" in self.sequences else []
        keys.extend(sorted(k for k in self.sequences if k not in reserved))
        if MONITOR_SEQ_KEY in self.sequences:
            keys.append(MONITOR_SEQ_KEY)
        return keys

    def _monitor_position_path(self):
        def walk(sequence_name, path):
            if sequence_name in path:
                return None
            next_path = path + [sequence_name]
            steps = self.sequences.get(sequence_name, [])
            if not isinstance(steps, list):
                return None
            for step in steps:
                kind = str(step.get("type", "")).upper()
                if kind == "POS":
                    return next_path
                if kind == "CALL":
                    found = walk(str(step.get("target_seq", "")), next_path)
                    if found:
                        return found
            return None
        return walk(MONITOR_SEQ_KEY, [])

    def _seq_index(self):
        keys = self._keys()
        return keys.index(self.current_sequence) if self.current_sequence in keys else 0

    def _selected(self):
        steps = self.sequences.get(self.current_sequence, [])
        return steps[self.selected_row] if 0 <= self.selected_row < len(steps) else {}

    def _kind(self): return str(self._selected().get("type", ""))
    def _name(self):
        step = self._selected()
        return str(step.get("text", "") if step.get("type") == "COMMENT" else step.get("name", ""))
    def _channel(self):
        step = self._selected()
        if not step: return 0
        value = int(step.get("port", step.get("dio_channel", 0)))
        kind = int(step.get("out_type" if step.get("type") == "OUT" else "in_type", 0))
        if kind == 2 and "bit_id" in step:
            return int(step["bit_id"])
        if step.get("type") in ("IN", "TMR"):
            if kind == 1 and value >= 32: value -= 32
            if kind == 2 and value >= 100: value -= 100
        return max(0, min(31 if kind == 2 else 15, value))
    def _io_type(self):
        step = self._selected(); key = "out_type" if step.get("type") == "OUT" else "in_type"
        value = int(step.get(key, 0)) if step else 0
        return value if value in (0, 1, 2, 4, 5) else 0
    def _address_class(self):
        return 1 if self._io_type() == 2 else 0
    def _address_keys(self):
        if self._address_class() == 1:
            return _internal_bit_labels()
        return _physical_io_labels("Y" if self._kind() == "OUT" else "X")
    def _address_index(self):
        group = self._io_type()
        logical = self._channel()
        if group == 2:
            ids = _internal_bit_ids()
            return ids.index(logical) if logical in ids else 0
        slot = IOManager.group_slot(group) if IOManager else (1 if group == 1 else 0)
        return slot * 16 + logical
    def _on(self): return bool(self._selected().get("on", True))
    def _seconds(self): return float(self._selected().get("time", 1.0)) if self._selected() else 1.0
    def _target_index(self):
        if not self._selected():
            return 0
        rows = _executable_rows(self.model.steps)
        raw_target = int(self._selected().get("target_idx", 0))
        if raw_target in rows:
            return rows.index(raw_target)
        return next((i for i, row in enumerate(rows) if row >= raw_target), 0)
    def _target_sequence(self): return str(self._selected().get("target_seq", ""))
    def _point_keys(self): return sorted(self.position_points.keys())
    def _point_index(self):
        keys = self._point_keys(); value = str(self._selected().get("point_name", ""))
        return keys.index(value) if value in keys else -1
    @staticmethod
    def _load_enabled_axes():
        try:
            from utils.json_utils import load_json
            from utils.paths import get_settings_path
            values = (load_json(get_settings_path()) or {}).get("axis_uses", [True] * 8)
            if isinstance(values, list) and len(values) >= 8:
                return [bool(value) for value in values[:8]]
        except Exception as exc:
            print(f"[SequenceEditor] 축 사용 설정 로드 실패: {exc}")
        return [True] * 8
    def _selected_point_name(self):
        return str(self._selected().get("point_name", "")) \
            if self._kind() in ("POS", "WPOS") else ""
    def _selected_point(self):
        return self.position_points.get(self._selected_point_name())
    def _position_axis_rows(self):
        point = self._selected_point() or {}
        coords = list(point.get("coords", [0.0] * 8))
        speeds = list(point.get("speeds", [100] * 8))
        active = list(self._selected().get("active_axes", [True] * 8))
        while len(coords) < 8: coords.append(0.0)
        while len(speeds) < 8: speeds.append(100)
        while len(active) < 8: active.append(True)
        return [
            {
                "index": index,
                "name": _AXIS_NAMES[index],
                "active": bool(active[index]),
                "position": f"{float(coords[index]):.3f}",
                "speed": str(max(1, min(100, int(float(speeds[index]))))),
            }
            for index in range(8) if self.enabled_axes[index]
        ]
    def _wait_position_axis_rows(self):
        point = self._selected_point() or {}
        coords = (list(point.get("coords", [0.0] * 8)) + [0.0] * 8)[:8]
        active = (
            list(self._selected().get("active_axes", self.enabled_axes)) + [False] * 8
        )[:8]
        return [{
            "index": index,
            "name": _AXIS_NAMES[index],
            "active": bool(active[index]),
            "target": f"{float(coords[index]):.3f}",
        } for index in range(8) if self.enabled_axes[index]]
    def _bool(self, key, default=False): return bool(self._selected().get(key, default))
    def _float(self, key, default=0.0): return float(self._selected().get(key, default))
    def _int(self, key, default=0): return int(self._selected().get(key, default))
    def _timeout_action_index(self):
        return {"continue": 0, "ask": 1, "alarm_go": 2}.get(str(self._selected().get("timeout_action", "continue")), 0)
    def _timer_choices(self):
        return ["직접 설정"] + sorted(str(key) for key in self.timer_library)
    def _timer_index(self, field):
        choices = self._timer_choices()
        value = str(self._selected().get(field, ""))
        return choices.index(value) if value in choices else 0
    def _timer_binding(self):
        return {
            "OUT": ("delay_timer_ref", "delay_time"),
            "TMR": ("timer_ref", "time"),
            "IN": ("timeout_timer_ref", "timeout"),
        }.get(self._kind(), ("", ""))
    def _library_timer_name(self):
        ref_field, _ = self._timer_binding()
        return self._library_timer_name_for(ref_field)
    def _library_timer_name_for(self, ref_field):
        name = str(self._selected().get(ref_field, "")) if ref_field else ""
        return name if name in self.timer_library else ""
    def _library_timer_index(self):
        name = self._library_timer_name()
        choices = self._timer_choices()
        return choices.index(name) if name in choices else 0
    def _library_timer_index_for(self, ref_field):
        name = self._library_timer_name_for(ref_field)
        choices = self._timer_choices()
        return choices.index(name) if name in choices else 0
    def _timer_cards(self):
        ref_field, value_field = self._timer_binding()
        return self._timer_cards_for(ref_field, value_field)
    def _timer_cards_for(self, ref_field, value_field):
        direct_seconds = self._float(value_field) if value_field else 0.0
        cards = [{"name": "", "seconds": direct_seconds, "direct": True}]
        cards.extend(
            {"name": str(name), "seconds": float(self.timer_library[name]), "direct": False}
            for name in sorted(self.timer_library)
        )
        return cards
    def _delay_timer_name(self):
        return self._library_timer_name() if self._kind() == "OUT" else ""
    def _delay_timer_cards(self):
        return self._timer_cards()
    def _alarm_numbers(self):
        numbers = {int(key) for key in USER_ALARMS}
        numbers.add(max(1, self._int("timeout_alarm_no", 1)))
        return sorted(numbers)
    def _alarm_choices(self):
        return [f"A-{number:03d}: {USER_ALARMS.get(number, f'사용자 알람 #{number}')}"
                for number in self._alarm_numbers()]
    def _alarm_index(self):
        number = max(1, self._int("timeout_alarm_no", 1))
        numbers = self._alarm_numbers()
        return numbers.index(number) if number in numbers else 0
    def _cond_type_index(self):
        kind = str(self._selected().get("cond_type", "INPUT")).upper()
        if kind == "VALVE":
            return 0
        aliases = {"POINT": "POSITION", "AXISPOS": "POSITION"}
        kind = aliases.get(kind, kind)
        choices = ["INPUT", "BIT", "MODE", "STATE", "DTCMP", "POSITION"]
        return choices.index(kind) if kind in choices else 0
    def _cond_address_keys(self):
        kind = str(self._selected().get("cond_type", "INPUT")).upper()
        if kind in ("INPUT", "VALVE"):
            return _physical_io_labels("X")
        if kind == "BIT":
            return _internal_bit_labels()
        return []
    def _cond_address_index(self):
        kind = str(self._selected().get("cond_type", "INPUT")).upper()
        value = self._int("cond_value")
        if kind == "VALVE":
            return 16 + max(0, min(15, value - 32 if value >= 32 else value))
        if kind == "INPUT":
            group = self._int("cond_io_type", 0)
            slot = IOManager.group_slot(group) if IOManager else 0
            return slot * 16 + max(0, min(15, value))
        if kind == "BIT":
            bit_id = self._int("cond_bit_id", value - 100 if value >= 100 else value)
            ids = _internal_bit_ids()
            return ids.index(bit_id) if bit_id in ids else 0
        return max(0, min(15, value))

    def _mode_cards(self):
        manager = ModeManager.instance() if ModeManager else None
        return [
            {
                "index": index,
                "name": manager.get_name(index) if manager else f"Mode {index + 1}",
                "state": bool(self.mode_data[index]) if index < len(self.mode_data) else False,
            }
            for index in range(TOTAL_MODE_COUNT)
        ]

    def _selected_mode_index(self):
        return max(0, min(TOTAL_MODE_COUNT - 1, self._int("cond_value")))

    def _selected_mode_name(self):
        index = self._selected_mode_index()
        manager = ModeManager.instance() if ModeManager else None
        return manager.get_name(index) if manager else f"Mode {index + 1}"

    def _selected_run_state_index(self):
        return max(0, min(3, self._int("cond_value")))

    def _selected_cond_point_name(self):
        if str(self._selected().get("cond_type", "")).upper() not in (
                "POSITION", "POINT", "AXISPOS"):
            return ""
        return str(self._selected().get("cond_point_name", ""))

    def _selected_cond_point_index(self):
        keys = self._point_keys()
        name = self._selected_cond_point_name()
        return keys.index(name) if name in keys else -1

    def _position_cond_axis_rows(self):
        point = self.position_points.get(self._selected_cond_point_name(), {})
        coords = list(point.get("coords", [0.0] * 8))
        axes = list(self._selected().get("cond_position_axes", self.enabled_axes))
        coords = (coords + [0.0] * 8)[:8]
        axes = (axes + [False] * 8)[:8]
        return [{
            "index": index,
            "name": _AXIS_NAMES[index],
            "active": bool(axes[index]),
            "target": f"{float(coords[index]):.3f}",
        } for index in range(8) if self.enabled_axes[index]]

    def _data_keys(self):
        return _data_labels()

    def _variable_cards(self, kind):
        store = VariableStore.instance()
        definitions = (store.bit_definitions() if kind == "bit"
                       else store.data_definitions())
        cards = []
        for item in definitions:
            item_id = int(item["id"])
            is_bit = kind == "bit"
            value = store.get_bit(item_id) if is_bit else store.get_data(item_id)
            data_address = None if is_bit else store.data_plc_address(item_id)
            cards.append({
                "id": item_id,
                "name": str(item["name"]),
                "state": bool(value) if is_bit else False,
                "valueText": ("ON" if value else "OFF") if is_bit else str(value),
                "publish": bool(item.get("plc_publish", False)),
                "plc": (f"DT{504 + item_id // 16}.{item_id % 16}" if is_bit
                        else (f"DT{data_address}~DT{data_address + 1}"
                              if data_address is not None else "주소 미지정")),
                "reset": RESET_LABELS.get(
                    item.get("reset_policy", "auto"), "자동 시작 시 초기화",
                ),
            })
        return cards

    def _selected_io_bit_id(self):
        return self._channel() if self._address_class() == 1 else -1

    def _selected_cond_bit_id(self):
        if str(self._selected().get("cond_type", "")).upper() != "BIT":
            return -1
        value = self._int("cond_value", 100)
        return self._int("cond_bit_id", value - 100 if value >= 100 else value)

    def _selected_data_id(self, field, legacy_field):
        step = self._selected()
        if not step:
            return -1
        return int(step.get(field, int(step.get(legacy_field, 60000)) - 60000))

    def _selected_optional_data_id(self, field):
        step = self._selected()
        return int(step.get(field, -1)) if step else -1

    def _data_index_for(self, field, legacy_field):
        step = self._selected()
        legacy = int(step.get(legacy_field, 60000)) - 60000 if step else 0
        item_id = int(step.get(field, legacy)) if step else 0
        ids = _data_ids()
        return ids.index(item_id) if item_id in ids else 0
    def _step_targets(self):
        return [
            f"{number}. {_summary(self.model.steps[row], row, self.model.steps)}"
            for number, row in enumerate(_executable_rows(self.model.steps), 1)
        ]
    def _target_seq_index(self):
        keys = [k for k in self._keys() if k != self.current_sequence]
        target = self._target_sequence()
        return keys.index(target) if target in keys else -1

    def _sequence_cards(self):
        cards = []
        for index, name in enumerate(self._keys()):
            kind = "MAIN" if name == "Main" else (
                "MONITOR" if name == MONITOR_SEQ_KEY else "SUB"
            )
            steps = self.sequences.get(name, [])
            cards.append({
                "index": index,
                "name": name,
                "kind": kind,
                "stepCount": len(_executable_rows(steps)) if isinstance(steps, list) else 0,
            })
        return cards

    sequenceKeys = Property(list, _keys, notify=changed)
    sequenceIndex = Property(int, _seq_index, notify=changed)
    sequenceCards = Property(list, _sequence_cards, notify=changed)
    isMonitorSequence = Property(
        bool, lambda self: self.current_sequence == MONITOR_SEQ_KEY,
        notify=changed,
    )
    selectedRow = Property(int, lambda self: self.selected_row, notify=selectionChanged)
    selectedType = Property(str, _kind, notify=selectionChanged)
    selectedName = Property(str, _name, notify=selectionChanged)
    selectedChannel = Property(int, _channel, notify=selectionChanged)
    selectedIoType = Property(int, _io_type, notify=selectionChanged)
    selectedAddressClass = Property(int, _address_class, notify=selectionChanged)
    addressKeys = Property(list, _address_keys, notify=selectionChanged)
    selectedAddressIndex = Property(int, _address_index, notify=selectionChanged)
    selectedOn = Property(bool, _on, notify=selectionChanged)
    selectedSeconds = Property(float, _seconds, notify=selectionChanged)
    selectedTargetIndex = Property(int, _target_index, notify=selectionChanged)
    selectedTargetSequence = Property(str, _target_sequence, notify=selectionChanged)
    stepTargets = Property(list, _step_targets, notify=changed)
    targetSequenceKeys = Property(list, lambda self: [k for k in self._keys() if k != self.current_sequence], notify=changed)
    targetSequenceIndex = Property(int, _target_seq_index, notify=selectionChanged)
    pointKeys = Property(list, _point_keys, notify=changed)
    selectedPointIndex = Property(int, _point_index, notify=selectionChanged)
    selectedPointName = Property(str, _selected_point_name, notify=selectionChanged)
    hasSelectedPoint = Property(bool, lambda s: s._selected_point() is not None, notify=selectionChanged)
    positionAxisRows = Property(list, _position_axis_rows, notify=selectionChanged)
    waitPositionAxisRows = Property(list, _wait_position_axis_rows, notify=selectionChanged)
    selectedPositionTolerance = Property(
        float, lambda s: max(0.0, s._float("position_tolerance", 0.1)),
        notify=selectionChanged,
    )
    selectedPositionTimeout = Property(
        float, lambda s: max(0.001, s._float("timeout", 5.0)),
        notify=selectionChanged,
    )
    selectedWaitCompletion = Property(bool, lambda s: s._bool("wait_completion", True), notify=selectionChanged)
    selectedPackBase = Property(bool, lambda s: s._bool("pack_base"), notify=selectionChanged)
    selectedDelayEnabled = Property(bool, lambda s: s._bool("delay_enable"), notify=selectionChanged)
    selectedDelaySeconds = Property(float, lambda s: s._float("delay_time"), notify=selectionChanged)
    timerChoices = Property(list, _timer_choices, notify=changed)
    selectedDelayTimerIndex = Property(int, lambda s: s._timer_index("delay_timer_ref"), notify=selectionChanged)
    selectedDelayTimerName = Property(str, _delay_timer_name, notify=selectionChanged)
    delayTimerCards = Property(list, _delay_timer_cards, notify=selectionChanged)
    selectedLibraryTimerIndex = Property(int, _library_timer_index, notify=selectionChanged)
    selectedLibraryTimerName = Property(str, _library_timer_name, notify=selectionChanged)
    timerCards = Property(list, _timer_cards, notify=selectionChanged)
    selectedTimeoutEnabled = Property(bool, lambda s: s._bool("timeout_enabled"), notify=selectionChanged)
    selectedTimeoutSeconds = Property(float, lambda s: s._float("timeout", 5.0), notify=selectionChanged)
    selectedTimeoutTimerName = Property(
        str, lambda s: s._library_timer_name_for("timeout_timer_ref"),
        notify=selectionChanged,
    )
    selectedTimeoutTimerIndex = Property(
        int, lambda s: s._library_timer_index_for("timeout_timer_ref"),
        notify=selectionChanged,
    )
    timeoutTimerCards = Property(
        list, lambda s: s._timer_cards_for("timeout_timer_ref", "timeout"),
        notify=selectionChanged,
    )
    selectedTimeupEnabled = Property(bool, lambda s: s._bool("timeup_enabled"), notify=selectionChanged)
    selectedTimeupSeconds = Property(float, lambda s: s._float("timeup_time", 1.0), notify=selectionChanged)
    selectedTimeupTimerName = Property(
        str, lambda s: s._library_timer_name_for("timeup_timer_ref"),
        notify=selectionChanged,
    )
    selectedTimeupTimerIndex = Property(
        int, lambda s: s._library_timer_index_for("timeup_timer_ref"),
        notify=selectionChanged,
    )
    timeupTimerCards = Property(
        list, lambda s: s._timer_cards_for("timeup_timer_ref", "timeup_time"),
        notify=selectionChanged,
    )
    selectedTimeoutAction = Property(int, _timeout_action_index, notify=selectionChanged)
    selectedTimeoutAlarmNo = Property(int, lambda s: max(1, s._int("timeout_alarm_no", 1)), notify=selectionChanged)
    timeoutAlarmChoices = Property(list, _alarm_choices, notify=selectionChanged)
    selectedTimeoutAlarmIndex = Property(int, _alarm_index, notify=selectionChanged)
    selectedTimerRefIndex = Property(int, lambda s: s._timer_index("timer_ref"), notify=selectionChanged)
    selectedParallel = Property(bool, lambda s: s._bool("parallel"), notify=selectionChanged)
    selectedConditional = Property(bool, lambda s: s._bool("condition"), notify=selectionChanged)
    selectedCondType = Property(int, _cond_type_index, notify=selectionChanged)
    selectedCondValue = Property(int, lambda s: s._int("cond_value"), notify=selectionChanged)
    modeCards = Property(list, _mode_cards, notify=selectionChanged)
    selectedModeIndex = Property(int, _selected_mode_index, notify=selectionChanged)
    selectedModeName = Property(str, _selected_mode_name, notify=selectionChanged)
    selectedRunStateIndex = Property(int, _selected_run_state_index, notify=selectionChanged)
    selectedCondPointName = Property(str, _selected_cond_point_name, notify=selectionChanged)
    selectedCondPointIndex = Property(int, _selected_cond_point_index, notify=selectionChanged)
    positionCondAxisRows = Property(list, _position_cond_axis_rows, notify=selectionChanged)
    selectedPositionCondTolerance = Property(
        float, lambda s: max(0.0, s._float("cond_position_tolerance", 0.1)),
        notify=selectionChanged,
    )
    condAddressKeys = Property(list, _cond_address_keys, notify=selectionChanged)
    selectedCondAddressIndex = Property(int, _cond_address_index, notify=selectionChanged)
    selectedCondOn = Property(bool, lambda s: s._bool("cond_on", True), notify=selectionChanged)
    selectedCmpAddress = Property(int, lambda s: s._int("cmp_dt_addr", 60000), notify=selectionChanged)
    dataKeys = Property(list, _data_keys, notify=selectionChanged)
    bitCards = Property(list, lambda s: s._variable_cards("bit"), notify=selectionChanged)
    dataCards = Property(list, lambda s: s._variable_cards("data"), notify=selectionChanged)
    selectedIoBitId = Property(int, _selected_io_bit_id, notify=selectionChanged)
    selectedCondBitId = Property(int, _selected_cond_bit_id, notify=selectionChanged)
    selectedIoBitName = Property(
        str, lambda s: (_bit_label(s._selected_io_bit_id())
                        if s._selected_io_bit_id() >= 0 else "내부비트 선택"),
        notify=selectionChanged,
    )
    selectedCondBitName = Property(
        str, lambda s: (_bit_label(s._selected_cond_bit_id())
                        if s._selected_cond_bit_id() >= 0 else "내부비트 선택"),
        notify=selectionChanged,
    )
    selectedDatDataId = Property(
        int, lambda s: s._selected_data_id("data_id", "dat_dt_addr"),
        notify=selectionChanged,
    )
    selectedDatMode = Property(
        int, lambda s: 1 if str(s._selected().get("dat_mode", "constant")) == "data" else 0,
        notify=selectionChanged,
    )
    selectedDatLeftDataId = Property(
        int, lambda s: s._selected_optional_data_id("dat_left_data_id"),
        notify=selectionChanged,
    )
    selectedDatRightDataId = Property(
        int, lambda s: s._selected_optional_data_id("dat_right_data_id"),
        notify=selectionChanged,
    )
    selectedCmpDataId = Property(
        int, lambda s: s._selected_data_id("cmp_data_id", "cmp_dt_addr"),
        notify=selectionChanged,
    )
    selectedDatDataName = Property(
        str, lambda s: (_data_label(s._selected_data_id("data_id", "dat_dt_addr"))
                        if s._selected_data_id("data_id", "dat_dt_addr") >= 0
                        else "데이터 선택"),
        notify=selectionChanged,
    )
    selectedDatLeftDataName = Property(
        str, lambda s: (_data_label(s._selected_optional_data_id("dat_left_data_id"))
                        if s._selected_optional_data_id("dat_left_data_id") >= 0
                        else "데이터 A 선택"),
        notify=selectionChanged,
    )
    selectedDatRightDataName = Property(
        str, lambda s: (_data_label(s._selected_optional_data_id("dat_right_data_id"))
                        if s._selected_optional_data_id("dat_right_data_id") >= 0
                        else "데이터 B 선택"),
        notify=selectionChanged,
    )
    selectedCmpDataName = Property(
        str, lambda s: (_data_label(s._selected_data_id("cmp_data_id", "cmp_dt_addr"))
                        if s._selected_data_id("cmp_data_id", "cmp_dt_addr") >= 0
                        else "데이터 선택"),
        notify=selectionChanged,
    )
    selectedCmpDataIndex = Property(
        int, lambda s: s._data_index_for("cmp_data_id", "cmp_dt_addr"),
        notify=selectionChanged,
    )
    selectedCmpOp = Property(int, lambda s: s._int("cmp_op", 0), notify=selectionChanged)
    selectedCmpConst = Property(int, lambda s: s._int("cmp_const"), notify=selectionChanged)
    selectedDatAddress = Property(int, lambda s: s._int("dat_dt_addr", 60000), notify=selectionChanged)
    selectedDatDataIndex = Property(
        int, lambda s: s._data_index_for("data_id", "dat_dt_addr"),
        notify=selectionChanged,
    )
    selectedDatOp = Property(int, lambda s: s._int("dat_op", 0), notify=selectionChanged)
    selectedDatConst = Property(int, lambda s: s._int("dat_const"), notify=selectionChanged)
    selectedDatMathOp = Property(int, lambda s: s._int("dat_math_op", 0), notify=selectionChanged)

    def _notify_row(self):
        self.model.refresh(self.selected_row)
        self.selectionChanged.emit()
        self.changed.emit()

    @Slot(int)
    def selectSequence(self, index):
        keys = self._keys()
        if 0 <= index < len(keys):
            self.current_sequence = keys[index]
            self.model.reset_steps(self.sequences[self.current_sequence])
            self.selected_row = 0 if self.model.steps else -1
            self.changed.emit(); self.selectionChanged.emit()

    @Slot()
    def addSequence(self):
        number = 1
        while f"Sub{number}" in self.sequences:
            number += 1
        suggested = f"Sub{number}"

        def created(accepted, value):
            if not accepted:
                return
            name = str(value).strip()
            if not name:
                return
            if any(name.casefold() == existing.casefold()
                   for existing in self.sequences):
                if self.overlay is not None:
                    self.overlay.show_message(
                        "프로그램 추가",
                        f"'{name}' 프로그램이 이미 존재합니다.", error=True,
                    )
                return
            self.current_sequence = name
            self.sequences[name] = []
            self.selected_row = -1
            self.model.reset_steps(self.sequences[name])
            self.changed.emit(); self.selectionChanged.emit()

        if self.overlay is not None:
            self.overlay.request_text(
                "새 서브 프로그램 이름", suggested, callback=created,
            )
        else:
            created(True, suggested)

    @Slot(int)
    def renameSequence(self, index):
        keys = self._keys()
        if not 0 <= int(index) < len(keys) or self.overlay is None:
            return
        old_name = keys[int(index)]
        if old_name in ("Main", MONITOR_SEQ_KEY):
            return

        def renamed(accepted, value):
            if not accepted:
                return
            new_name = str(value).strip()
            if not new_name or new_name == old_name:
                return
            if any(new_name.casefold() == existing.casefold()
                   for existing in self.sequences if existing != old_name):
                self.overlay.show_message(
                    "프로그램 이름 변경",
                    f"'{new_name}' 프로그램이 이미 존재합니다.", error=True,
                )
                return

            steps = self.sequences.pop(old_name)
            self.sequences[new_name] = steps
            for sequence_steps in self.sequences.values():
                for step in sequence_steps:
                    if (str(step.get("type", "")).upper() == "CALL"
                            and step.get("target_seq") == old_name):
                        step["target_seq"] = new_name
            if self.current_sequence == old_name:
                self.current_sequence = new_name
                self.model.reset_steps(steps)
            self.changed.emit(); self.selectionChanged.emit()

        self.overlay.request_text(
            "서브 프로그램 이름 변경", old_name, callback=renamed,
        )

    @Slot()
    def deleteSequence(self):
        if self.current_sequence in ("Main", MONITOR_SEQ_KEY):
            return
        removed = self.current_sequence
        del self.sequences[removed]
        for steps in self.sequences.values():
            for step in steps:
                if step.get("type") == "CALL" and step.get("target_seq") == removed:
                    step["target_seq"] = ""
        self.current_sequence = "Main"
        self.model.reset_steps(self.sequences["Main"])
        self.selected_row = 0 if self.model.steps else -1
        self.changed.emit(); self.selectionChanged.emit()

    @Slot(int)
    def selectStep(self, row):
        self.selected_row = row if 0 <= row < len(self.model.steps) else -1
        self.selectionChanged.emit()

    @Slot(str)
    def addStep(self, kind):
        kind = kind.upper()
        if self.current_sequence == MONITOR_SEQ_KEY and kind == "POS":
            if self.overlay is not None:
                self.overlay.show_message(
                    "Monitor 안전 제한",
                    "Monitor 프로그램에는 위치이동(POS) 스텝을 추가할 수 없습니다.",
                    error=True,
                )
            return
        count = sum(1 for s in self.model.steps if s.get("type") == kind) + 1
        data = {"type": kind, "name": f"{kind}_{count}"}
        if kind in ("OUT", "IN"):
            data.update({"port": 0, "on": True,
                         "out_type" if kind == "OUT" else "in_type": 0})
            if kind == "OUT": data["delay_enable"] = False
            else:
                data.update({
                    "timeup_enabled": False,
                    "timeup_time": 1.0,
                    "timeout_enabled": False,
                    "timeout": 5.0,
                    "timeout_action": "continue",
                })
        elif kind == "POS":
            data.update({"point_name": self._point_keys()[0] if self._point_keys() else "",
                         "active_axes": [True] * 8, "wait_completion": True})
        elif kind == "WPOS":
            data.update({
                "point_name": self._point_keys()[0] if self._point_keys() else "",
                "active_axes": list(self.enabled_axes),
                "position_tolerance": 0.1,
                "timeout": 5.0,
            })
        elif kind == "TMR": data.update({"time": 1.0})
        elif kind == "JMP": data.update({"target_idx": 0, "condition": False,
                                          "cond_type": "INPUT", "cond_io_type": 0,
                                          "cond_value": 0,
                                          "cond_on": True, "cmp_dt_addr": 60000,
                                          "cmp_op": 0, "cmp_const": 0})
        elif kind == "CALL": data.update({"target_seq": "", "parallel": False})
        elif kind == "DAT":
            ids = _data_ids()
            item_id = ids[0] if ids else -1
            data.update({"data_id": item_id, "dat_dt_addr": 60000 + max(0, item_id),
                         "dat_mode": "constant", "dat_op": 0, "dat_const": 0,
                         "dat_left_data_id": item_id,
                         "dat_right_data_id": item_id, "dat_math_op": 0})
        elif kind == "COMMENT": data = {"type": "COMMENT", "text": "메모"}
        elif kind == "END": data["name"] = "END"
        # Insert immediately below the selected row. With no selection (for
        # example, an empty sequence), append to the end as before.
        insert_row = (
            self.selected_row + 1
            if 0 <= self.selected_row < len(self.model.steps)
            else len(self.model.steps)
        )
        # JMP targets are stored as raw list indices. Preserve their logical
        # destination when a new row is inserted before that destination.
        for step in self.model.steps:
            if str(step.get("type", "")).upper() != "JMP":
                continue
            target = int(step.get("target_idx", step.get("target_step", 0)))
            if target >= insert_row:
                step["target_idx"] = target + 1
                step.pop("target_step", None)
        self.model.beginInsertRows(QModelIndex(), insert_row, insert_row)
        self.model.steps.insert(insert_row, data)
        self.model.endInsertRows()
        self.selected_row = insert_row
        self.selectionChanged.emit(); self.changed.emit()

    @Slot()
    def deleteSelected(self):
        row = self.selected_row
        if not 0 <= row < len(self.model.steps): return
        self.model.beginRemoveRows(QModelIndex(), row, row)
        self.model.steps.pop(row)
        self.model.endRemoveRows()
        self.selected_row = min(row, len(self.model.steps) - 1)
        self.selectionChanged.emit(); self.changed.emit()

    @Slot(int)
    def moveSelected(self, delta):
        old = self.selected_row; new = old + delta
        if not (0 <= old < len(self.model.steps) and 0 <= new < len(self.model.steps)): return
        # Move one row without resetting the complete model. This preserves the
        # ListView's viewport and prevents the scroll position from jumping.
        destination = new if new < old else new + 1
        self.model.beginMoveRows(
            QModelIndex(), old, old, QModelIndex(), destination,
        )
        step = self.model.steps.pop(old)
        self.model.steps.insert(new, step)
        self.model.endMoveRows()
        # Delegates are retained by beginMoveRows(), so explicitly invalidate
        # the affected rows. Display numbers belong to row positions and must
        # remain sequential instead of travelling with the moved delegate.
        first = self.model.index(min(old, new), 0)
        last = self.model.index(max(old, new), 0)
        self.model.dataChanged.emit(first, last, [
            StepListModel.TypeRole,
            StepListModel.SummaryRole,
            StepListModel.ColorRole,
            StepListModel.NameRole,
            StepListModel.DetailRole,
            StepListModel.NumberRole,
        ])
        self.selected_row = new
        self.selectionChanged.emit(); self.changed.emit()
        self.stepMoved.emit(new, -1 if delta < 0 else 1)

    @Slot(str)
    def setName(self, value):
        step = self._selected()
        if not step: return
        step["text" if step.get("type") == "COMMENT" else "name"] = value
        self._notify_row()

    @Slot()
    def editComment(self):
        if self._kind() != "COMMENT" or self.overlay is None:
            return
        current = str(self._selected().get("text", ""))

        def finished(accepted, value):
            if accepted:
                self.setName(str(value))

        self.overlay.request_text("코멘트 입력", current, callback=finished)

    @Slot(int)
    def setChannel(self, channel):
        step = self._selected()
        if not step: return
        kind = self._io_type(); logical = max(0, min(31 if kind == 2 else 15, int(channel)))
        if step.get("type") in ("IN", "TMR"):
            step["port"] = logical + (32 if kind == 1 else 100 if kind == 2 else 0)
        else:
            step["port"] = logical
        step.pop("dio_channel", None)
        self._notify_row()

    @Slot(int)
    def setIoType(self, kind):
        step = self._selected()
        if not step or step.get("type") not in ("OUT", "IN", "TMR"): return
        logical = self._channel(); kind = max(0, min(2, int(kind)))
        step["out_type" if step.get("type") == "OUT" else "in_type"] = kind
        self.setChannel(logical)

    @Slot(int)
    def setAddressClass(self, address_class):
        step = self._selected()
        if not step or step.get("type") not in ("OUT", "IN", "TMR"):
            return
        if int(address_class) == 1:
            ids = _internal_bit_ids()
            item_id = ids[0] if ids else -1
            step["out_type" if step.get("type") == "OUT" else "in_type"] = 2
            step["bit_id"] = item_id
            step["port"] = max(0, item_id) if step.get("type") == "OUT" else 100 + max(0, item_id)
        else:
            step["out_type" if step.get("type") == "OUT" else "in_type"] = 0
            step["port"] = 0
        step.pop("dio_channel", None)
        self._notify_row()

    @Slot(int)
    def setAddressIndex(self, address_index):
        step = self._selected()
        if not step or step.get("type") not in ("OUT", "IN", "TMR"):
            return
        is_input = step.get("type") != "OUT"
        max_physical = max(0, (IOManager.instance().point_count(is_input)
                               if IOManager else 32) - 1)
        index = max(0, min(31 if self._address_class() == 1 else max_physical,
                           int(address_index)))
        key = "out_type" if step.get("type") == "OUT" else "in_type"
        if self._address_class() == 1:
            ids = _internal_bit_ids()
            if not ids:
                return
            selected = ids[max(0, min(len(ids) - 1, int(address_index)))]
            step[key] = 2
            step["bit_id"] = selected
            step["port"] = selected if step.get("type") == "OUT" else 100 + selected
        else:
            slot, logical = divmod(index, 16)
            group = IOManager.group_code(slot) if IOManager else (1 if slot else 0)
            step[key] = group
            # Keep the historical +32 representation for group 2 input
            # recipes; all other groups store a local 0..15 channel.
            step["port"] = (logical + 32 if is_input and group == 1 else logical)
        step.pop("dio_channel", None)
        self._notify_row()

    def _select_variable(self, purpose, item_id):
        step = self._selected()
        item_id = int(item_id)
        if not step:
            return
        if purpose == "io_bit" and step.get("type") in ("OUT", "IN", "TMR"):
            key = "out_type" if step.get("type") == "OUT" else "in_type"
            step[key] = 2
            step["bit_id"] = item_id
            step["port"] = item_id if step.get("type") == "OUT" else 100 + item_id
            step.pop("dio_channel", None)
        elif purpose == "cond_bit" and step.get("type") == "JMP":
            step["cond_type"] = "BIT"
            step["cond_bit_id"] = item_id
            step["cond_value"] = 100 + item_id
        elif purpose == "dat_data" and step.get("type") == "DAT":
            step["data_id"] = item_id
            step["dat_dt_addr"] = 60000 + item_id
        elif purpose == "dat_left_data" and step.get("type") == "DAT":
            step["dat_left_data_id"] = item_id
        elif purpose == "dat_right_data" and step.get("type") == "DAT":
            step["dat_right_data_id"] = item_id
        elif purpose == "cmp_data" and step.get("type") == "JMP":
            step["cmp_data_id"] = item_id
            step["cmp_dt_addr"] = 60000 + item_id
        else:
            return
        self._notify_row()

    @Slot(int)
    def selectIoBit(self, item_id): self._select_variable("io_bit", item_id)

    @Slot(int)
    def selectCondBit(self, item_id): self._select_variable("cond_bit", item_id)

    @Slot(int)
    def selectDatData(self, item_id): self._select_variable("dat_data", item_id)

    @Slot(int)
    def selectDatLeftData(self, item_id): self._select_variable("dat_left_data", item_id)

    @Slot(int)
    def selectDatRightData(self, item_id): self._select_variable("dat_right_data", item_id)

    @Slot(int)
    def selectCmpData(self, item_id): self._select_variable("cmp_data", item_id)

    def _refresh_after_variable_change(self):
        self.model.reset_steps(self.sequences[self.current_sequence])
        self.selectionChanged.emit()
        self.changed.emit()
        self.variableLibraryChanged.emit()

    @Slot(str)
    def addBitVariable(self, purpose):
        if self.overlay is None:
            return

        def named(accepted, value):
            name = str(value).strip() if accepted else ""
            if not name:
                return
            try:
                item_id = VariableStore.instance().add_bit(name, False)
            except ValueError as exc:
                self.overlay.show_message("내부비트 추가", str(exc), error=True)
                return
            self._select_variable(str(purpose), item_id)
            self._refresh_after_variable_change()

        self.overlay.request_text("새 내부비트 이름", callback=named)

    @Slot(str)
    def addDataVariable(self, purpose):
        if self.overlay is None:
            return

        def named(accepted, value):
            name = str(value).strip() if accepted else ""
            if not name:
                return

            def valued(value_accepted, initial):
                if not value_accepted:
                    return
                try:
                    item_id = VariableStore.instance().add_data(name, int(initial))
                except ValueError as exc:
                    self.overlay.show_message("데이터 추가", str(exc), error=True)
                    return
                self._select_variable(str(purpose), item_id)
                self._refresh_after_variable_change()

            self.overlay.request_number(
                f"'{name}' 초기값", 0, decimal=False, signed=True,
                minimum=-(2 ** 31), maximum=2 ** 31 - 1, callback=valued,
            )

        self.overlay.request_text("새 데이터 이름", callback=named)

    @Slot(str, int)
    def renameVariable(self, kind, item_id):
        if self.overlay is None:
            return
        store = VariableStore.instance()
        current = store.bit_name(item_id) if kind == "bit" else store.data_name(item_id)

        def renamed(accepted, value):
            new_name = str(value).strip() if accepted else ""
            if not new_name or new_name == current:
                return
            definitions = (store.bit_definitions() if kind == "bit"
                           else store.data_definitions())
            if any(row["name"] == new_name and row["id"] != int(item_id)
                   for row in definitions):
                self.overlay.show_message(
                    "이름 변경", f"'{new_name}' 이름이 이미 존재합니다.", error=True,
                )
                return
            store.rename(kind, item_id, new_name)
            self._refresh_after_variable_change()

        self.overlay.request_text("이름 변경", current, callback=renamed)

    @Slot(str, int)
    def editVariableValue(self, kind, item_id):
        store = VariableStore.instance()
        if kind == "bit":
            store.set_initial("bit", item_id, not store.get_bit(item_id), apply_now=True)
            self._refresh_after_variable_change()
            return
        if self.overlay is None:
            return

        def valued(accepted, value):
            if accepted:
                store.set_initial("data", item_id, int(value), apply_now=True)
                self._refresh_after_variable_change()

        self.overlay.request_number(
            f"{store.data_name(item_id)} 초기값/현재값", store.get_data(item_id),
            decimal=False, signed=True, minimum=-(2 ** 31), maximum=2 ** 31 - 1,
            callback=valued,
        )

    @Slot(str, int)
    def toggleVariablePublish(self, kind, item_id):
        store = VariableStore.instance()
        definitions = (store.bit_definitions() if kind == "bit"
                       else store.data_definitions())
        item = next((row for row in definitions if row["id"] == int(item_id)), None)
        if item:
            if kind == "data":
                self.configureDataPublish(item_id)
            else:
                store.set_publish(kind, item_id, not item.get("plc_publish", False))
                self._refresh_after_variable_change()

    @Slot(int)
    def configureDataPublish(self, item_id):
        store = VariableStore.instance()
        if self.overlay is None:
            return
        current = store.data_plc_address(item_id)
        suggested = current if current is not None else store.next_free_data_plc_address()
        if suggested is None:
            self.overlay.show_message(
                "PLC 공개 주소", "사용 가능한 데이터 공개 주소가 없습니다.", error=True,
            )
            return

        def addressed(accepted, value):
            if not accepted:
                return
            try:
                store.set_publish("data", item_id, True, address=int(value))
            except (TypeError, ValueError) as exc:
                self.overlay.show_message("PLC 공개 주소", str(exc), error=True)
                return
            self._refresh_after_variable_change()

        self.overlay.request_number(
            f"{store.data_name(item_id)} PLC DINT 시작 주소",
            suggested, decimal=False, signed=False,
            minimum=PLC_DATA_START, maximum=PLC_DATA_LAST_START,
            callback=addressed,
        )

    @Slot(int)
    def unpublishData(self, item_id):
        store = VariableStore.instance()
        if self.overlay is None:
            return

        def confirmed(accepted):
            if accepted:
                store.set_publish("data", item_id, False)
                self._refresh_after_variable_change()

        self.overlay.request_confirm(
            "PLC 공개 해제",
            f"'{store.data_name(item_id)}'의 PLC 공개를 해제하시겠습니까?\n"
            "기존 PLC 주소의 값은 0으로 정리됩니다.",
            callback=confirmed,
        )

    @Slot(str, int)
    def cycleVariableReset(self, kind, item_id):
        VariableStore.instance().cycle_reset_policy(kind, item_id)
        self._refresh_after_variable_change()

    def _variable_reference_count(self, kind, item_id):
        count = 0
        for steps in self.sequences.values():
            if not isinstance(steps, list):
                continue
            for step in steps:
                step_kind = str(step.get("type", "")).upper()
                if kind == "bit":
                    if step_kind in ("OUT", "IN") and int(step.get(
                            "out_type" if step_kind == "OUT" else "in_type", 0)) == 2:
                        raw = int(step.get("port", 0))
                        legacy = raw - 100 if raw >= 100 else raw
                        count += int(step.get("bit_id", legacy)) == int(item_id)
                    if step_kind == "JMP" and str(step.get("cond_type", "")).upper() in ("BIT", "INTERNAL"):
                        raw = int(step.get("cond_value", 100))
                        legacy = raw - 100 if raw >= 100 else raw
                        count += int(step.get("cond_bit_id", legacy)) == int(item_id)
                else:
                    referenced = False
                    if step_kind == "DAT":
                        referenced = int(step.get(
                            "data_id", int(step.get("dat_dt_addr", 60000)) - 60000,
                        )) == int(item_id)
                        if str(step.get("dat_mode", "constant")) == "data":
                            referenced = referenced or (
                                int(step.get("dat_left_data_id", -1)) == int(item_id)
                                or int(step.get("dat_right_data_id", -1)) == int(item_id)
                            )
                    if step_kind == "JMP" and str(step.get("cond_type", "")).upper() in ("DTCMP", "DT", "DATA"):
                        referenced = int(step.get(
                            "cmp_data_id", int(step.get("cmp_dt_addr", 60000)) - 60000,
                        )) == int(item_id)
                    count += bool(referenced)
        return count

    @Slot(str, int)
    def deleteVariable(self, kind, item_id):
        if self.overlay is None:
            return
        references = self._variable_reference_count(kind, item_id)
        if references:
            self.overlay.show_message(
                "삭제 불가", f"시퀀스 스텝 {references}개에서 사용 중입니다.", error=True,
            )
            return
        store = VariableStore.instance()
        name = store.bit_name(item_id) if kind == "bit" else store.data_name(item_id)

        def confirmed(accepted):
            if accepted:
                store.remove(kind, item_id)
                self._refresh_after_variable_change()

        self.overlay.request_confirm(
            "변수 삭제", f"'{name}'을 삭제하시겠습니까?", callback=confirmed,
        )

    @Slot(bool)
    def setOn(self, enabled):
        if self._kind() in ("OUT", "IN", "TMR"): self._selected()["on"] = enabled; self._notify_row()

    @Slot(float)
    def setSeconds(self, seconds):
        if self._kind() == "TMR":
            self._selected()["time"] = max(0.0, float(seconds))
            self._selected().pop("timer_ref", None)
            self._notify_row()

    @Slot(int)
    def setTargetIndex(self, index):
        rows = _executable_rows(self.model.steps)
        index = int(index)
        if self._selected() and 0 <= index < len(rows):
            self._selected()["target_idx"] = rows[index]
            self._notify_row()

    @Slot(int)
    def setTargetSequenceIndex(self, index):
        keys = [k for k in self._keys() if k != self.current_sequence]
        if self._selected() and 0 <= index < len(keys):
            self._selected()["target_seq"] = keys[index]; self._notify_row()

    @Slot(int)
    def setPointIndex(self, index):
        keys = self._point_keys()
        if self._selected() and 0 <= index < len(keys): self._selected()["point_name"] = keys[index]; self._notify_row()
    @Slot()
    def addPositionPoint(self):
        if self._kind() != "POS" or self.overlay is None:
            return
        if len(self.position_points) >= _MAX_POSITION_POINTS:
            self.overlay.show_message(
                "포인트 추가", f"위치 포인트는 최대 {_MAX_POSITION_POINTS}개까지 등록할 수 있습니다.",
                error=True,
            )
            return
        number = 1
        while f"Point_{number}" in self.position_points:
            number += 1

        def named(accepted, value):
            if not accepted:
                return
            name = str(value).strip()
            if not name:
                self.overlay.show_message("포인트 추가", "포인트 이름을 입력하세요.", error=True)
                return
            if name in self.position_points:
                self.overlay.show_message(
                    "포인트 추가", f"'{name}' 포인트가 이미 존재합니다.", error=True,
                )
                return
            self.position_points[name] = {
                "coords": [0.0] * 8,
                "speeds": [100] * 8,
                "visible_mode": -1,
            }
            self._selected()["point_name"] = name
            self._notify_row()

        self.overlay.request_text("새 위치 포인트 이름", f"Point_{number}", callback=named)

    @Slot()
    def renameSelectedPoint(self):
        old_name = self._selected_point_name()
        if not old_name or old_name not in self.position_points or self.overlay is None:
            return

        def renamed(accepted, value):
            if not accepted:
                return
            new_name = str(value).strip()
            if not new_name or new_name == old_name:
                return
            if new_name in self.position_points:
                self.overlay.show_message(
                    "포인트 이름 변경", f"'{new_name}' 포인트가 이미 존재합니다.", error=True,
                )
                return
            reordered = {
                (new_name if name == old_name else name): point
                for name, point in self.position_points.items()
            }
            self.position_points.clear()
            self.position_points.update(reordered)
            for steps in self.sequences.values():
                if not isinstance(steps, list):
                    continue
                for step in steps:
                    if step.get("type") in ("POS", "WPOS") and step.get("point_name") == old_name:
                        step["point_name"] = new_name
                    if (step.get("type") == "POS" and step.get("name") == old_name):
                        step["name"] = new_name
                    if (step.get("type") == "JMP"
                            and str(step.get("cond_type", "")).upper() in (
                                "POSITION", "POINT", "AXISPOS")
                            and step.get("cond_point_name") == old_name):
                        step["cond_point_name"] = new_name
            self._notify_row()

        self.overlay.request_text("위치 포인트 이름 변경", old_name, callback=renamed)

    @Slot()
    def deleteSelectedPoint(self):
        old_name = self._selected_point_name()
        if not old_name or old_name not in self.position_points or self.overlay is None:
            return

        def confirmed(accepted):
            if not accepted:
                return
            self.position_points.pop(old_name, None)
            if self.position_points:
                next_name = self._point_keys()[0]
            else:
                next_name = "Point_1"
                self.position_points[next_name] = {
                    "coords": [0.0] * 8,
                    "speeds": [100] * 8,
                    "visible_mode": -1,
                }
            for steps in self.sequences.values():
                if not isinstance(steps, list):
                    continue
                for step in steps:
                    if step.get("type") in ("POS", "WPOS") and step.get("point_name") == old_name:
                        step["point_name"] = next_name
                    if (step.get("type") == "POS" and step.get("name") == old_name):
                        step["name"] = next_name
                    if (step.get("type") == "JMP"
                            and str(step.get("cond_type", "")).upper() in (
                                "POSITION", "POINT", "AXISPOS")
                            and step.get("cond_point_name") == old_name):
                        step["cond_point_name"] = next_name
            self._notify_row()

        self.overlay.request_confirm(
            "위치 포인트 삭제", f"'{old_name}' 포인트를 삭제하시겠습니까?\n"
            "이 포인트를 참조하는 모든 위치이동 스텝은 다른 포인트로 변경됩니다.",
            callback=confirmed,
        )

    @Slot(int, float)
    def setPointCoordinate(self, index, value):
        point = self._selected_point()
        if point is None or not 0 <= index < 8:
            return
        from utils.axis_limits import get_axis_strokes
        maximum = get_axis_strokes()[index]
        value = float(value)
        if value < 0.0 or value > maximum:
            if self.overlay is not None:
                self.overlay.show_message(
                    "입력 범위 초과",
                    f"{_AXIS_NAMES[index]}축 허용 범위는 0 ~ {maximum:.3f} mm입니다.",
                    error=True,
                )
            return
        coords = list(point.get("coords", [0.0] * 8))
        while len(coords) < 8: coords.append(0.0)
        coords[index] = round(value, 3)
        point["coords"] = coords
        self._notify_row()

    @Slot(int)
    def editPointCoordinate(self, index):
        point = self._selected_point()
        if point is None or self.overlay is None or not 0 <= index < 8:
            return
        coords = list(point.get("coords", [0.0] * 8))
        while len(coords) < 8: coords.append(0.0)
        from utils.axis_limits import get_axis_strokes
        maximum = get_axis_strokes()[index]

        def finished(accepted, value):
            if accepted:
                self.setPointCoordinate(index, value)

        self.overlay.request_number(
            f"{self._selected_point_name()} · {_AXIS_NAMES[index]}축 목표위치 (mm)",
            float(coords[index]), decimal=True, minimum=0, maximum=maximum,
            callback=finished,
        )

    @Slot(int, float)
    def setPointSpeed(self, index, value):
        point = self._selected_point()
        if point is None or not 0 <= index < 8:
            return
        speeds = list(point.get("speeds", [100] * 8))
        while len(speeds) < 8: speeds.append(100)
        speeds[index] = max(1, min(100, int(float(value))))
        point["speeds"] = speeds
        self._notify_row()

    @Slot(int)
    def editPointSpeed(self, index):
        point = self._selected_point()
        if point is None or self.overlay is None or not 0 <= index < 8:
            return
        speeds = list(point.get("speeds", [100] * 8))
        while len(speeds) < 8: speeds.append(100)

        def finished(accepted, value):
            if accepted:
                self.setPointSpeed(index, value)

        self.overlay.request_number(
            f"{self._selected_point_name()} · {_AXIS_NAMES[index]}축 속도 (%)",
            float(speeds[index]), decimal=False, minimum=1, maximum=100,
            callback=finished,
        )

    @Slot(int, bool)
    def setAxisActive(self, index, enabled):
        step = self._selected(); axes = list(step.get("active_axes", [True] * 8)) if step else []
        while len(axes) < 8: axes.append(True)
        if 0 <= index < 8: axes[index] = bool(enabled); step["active_axes"] = axes; self._notify_row()
    @Slot(int, result=bool)
    def axisActive(self, index):
        axes = list(self._selected().get("active_axes", [True] * 8)); return bool(axes[index]) if 0 <= index < len(axes) else True
    @Slot(bool)
    def setWaitCompletion(self, value):
        if self._kind() == "POS": self._selected()["wait_completion"] = bool(value); self._notify_row()
    @Slot(bool)
    def setPackBase(self, value):
        if self._kind() != "POS": return
        if value: self._selected()["pack_base"] = True
        else: self._selected().pop("pack_base", None)
        self._notify_row()

    @Slot()
    def editWaitPositionTolerance(self):
        if self._kind() != "WPOS" or self.overlay is None:
            return

        def valued(accepted, value):
            if accepted:
                self._selected()["position_tolerance"] = round(
                    max(0.0, min(100.0, float(value))), 3,
                )
                self._notify_row()

        self.overlay.request_number(
            "WPOS 위치 허용오차", self._float("position_tolerance", 0.1),
            decimal=True, signed=False, minimum=0.0, maximum=100.0,
            callback=valued,
        )

    @Slot()
    def editWaitPositionTimeout(self):
        if self._kind() != "WPOS" or self.overlay is None:
            return

        def valued(accepted, value):
            if accepted:
                self._selected()["timeout"] = round(
                    max(0.1, min(3600.0, float(value))), 3,
                )
                self._notify_row()

        self.overlay.request_number(
            "WPOS 최대 대기시간", self._float("timeout", 5.0),
            decimal=True, signed=False, minimum=0.1, maximum=3600.0,
            callback=valued,
        )
    @Slot(bool)
    def setDelayEnabled(self, value):
        if self._kind() == "OUT": self._selected()["delay_enable"] = bool(value); self._notify_row()
    @Slot(float)
    def setDelaySeconds(self, value):
        if self._kind() == "OUT":
            self._selected()["delay_time"] = max(0.0, float(value))
            self._selected().pop("delay_timer_ref", None)
            self._notify_row()
    @Slot(int)
    def setDelayTimerIndex(self, index):
        if self._kind() != "OUT": return
        choices = self._timer_choices(); index = max(0, min(len(choices) - 1, int(index)))
        if index == 0:
            self._selected().pop("delay_timer_ref", None)
        else:
            ref = choices[index]
            self._selected()["delay_timer_ref"] = ref
            self._selected()["delay_time"] = float(self.timer_library[ref])
        self._notify_row()
    @Slot(str)
    def selectDelayTimer(self, name):
        if self._kind() == "OUT":
            self.selectLibraryTimer(name)

    def _sync_timer_references(self, timer_ref, seconds):
        for steps in self.sequences.values():
            if not isinstance(steps, list):
                continue
            for candidate in steps:
                for ref_field, value_field in (
                    ("timer_ref", "time"),
                    ("delay_timer_ref", "delay_time"),
                    ("timeup_timer_ref", "timeup_time"),
                    ("timeout_timer_ref", "timeout"),
                ):
                    if candidate.get(ref_field) == timer_ref:
                        candidate[value_field] = seconds

    def _detach_timer_references(self, timer_ref):
        for steps in self.sequences.values():
            if not isinstance(steps, list):
                continue
            for candidate in steps:
                for ref_field in (
                    "timer_ref", "delay_timer_ref", "timeup_timer_ref",
                    "timeout_timer_ref",
                ):
                    if candidate.get(ref_field) == timer_ref:
                        candidate.pop(ref_field, None)

    def _refresh_after_timer_library_change(self):
        self.model.reset_steps(self.sequences[self.current_sequence])
        self.selectionChanged.emit()
        self.changed.emit()
        self.timerLibraryChanged.emit()

    @Slot(str)
    def selectLibraryTimer(self, name):
        self._select_timer(name, *self._timer_binding())

    def _select_timer(self, name, ref_field, value_field):
        if not ref_field:
            return
        name = str(name)
        if not name:
            self._selected().pop(ref_field, None)
        elif name in self.timer_library:
            self._selected()[ref_field] = name
            self._selected()[value_field] = float(self.timer_library[name])
        else:
            return
        self._notify_row()

    @Slot(str)
    def selectTimeupTimer(self, name):
        if self._kind() == "IN":
            self._select_timer(name, "timeup_timer_ref", "timeup_time")

    @Slot(str)
    def selectTimeoutTimer(self, name):
        if self._kind() == "IN":
            self._select_timer(name, "timeout_timer_ref", "timeout")

    @Slot()
    def editLibraryTimerSeconds(self):
        self._edit_timer_seconds(*self._timer_binding())

    def _edit_timer_seconds(self, ref_field, value_field):
        if not ref_field or self.overlay is None:
            return
        step = self._selected()
        timer_ref = str(step.get(ref_field, ""))
        current = float(step.get(value_field, 0.0))

        def finished(accepted, value):
            if not accepted:
                return
            seconds = round(max(0.0, float(value)), 2)
            if timer_ref and timer_ref in self.timer_library:
                self.timer_library[timer_ref] = seconds
                self._sync_timer_references(timer_ref, seconds)
                self._refresh_after_timer_library_change()
            else:
                self._selected()[value_field] = seconds
                self._selected().pop(ref_field, None)
                self._notify_row()

        title = f"타이머: {timer_ref}" if timer_ref else "시간 직접 입력"
        self.overlay.request_number(
            title, current, decimal=True, minimum=0, maximum=99999,
            callback=finished,
        )

    @Slot()
    def editTimeupSeconds(self):
        if self._kind() == "IN":
            self._edit_timer_seconds("timeup_timer_ref", "timeup_time")

    @Slot()
    def editTimeoutSeconds(self):
        if self._kind() == "IN":
            self._edit_timer_seconds("timeout_timer_ref", "timeout")

    @Slot()
    def editDelaySeconds(self):
        if self._kind() == "OUT":
            self.editLibraryTimerSeconds()

    @Slot()
    def addLibraryTimer(self):
        self._add_library_timer(*self._timer_binding())

    def _add_library_timer(self, ref_field, value_field):
        if not ref_field or self.overlay is None:
            return

        def named(accepted, value):
            if not accepted:
                return
            name = str(value).strip()
            if not name:
                self.overlay.show_message("타이머 추가", "타이머 이름을 입력하세요.", error=True)
                return
            if name in self.timer_library:
                self.overlay.show_message("타이머 추가", f"'{name}' 타이머가 이미 존재합니다.", error=True)
                return

            def timed(time_accepted, seconds):
                if not time_accepted:
                    return
                seconds = round(max(0.0, float(seconds)), 2)
                self.timer_library[name] = seconds
                if self._selected():
                    self._selected()[ref_field] = name
                    self._selected()[value_field] = seconds
                self._notify_row()
                self.timerLibraryChanged.emit()

            self.overlay.request_number(
                f"'{name}' 시간 (초)", 1.0, decimal=True,
                minimum=0, maximum=99999, callback=timed,
            )

        self.overlay.request_text("새 타이머 이름", callback=named)

    @Slot()
    def addTimeupTimer(self):
        if self._kind() == "IN":
            self._add_library_timer("timeup_timer_ref", "timeup_time")

    @Slot()
    def addTimeoutTimer(self):
        if self._kind() == "IN":
            self._add_library_timer("timeout_timer_ref", "timeout")

    @Slot()
    def addDelayTimer(self):
        if self._kind() == "OUT":
            self.addLibraryTimer()

    @Slot()
    def deleteLibraryTimer(self):
        ref_field, _ = self._timer_binding()
        self._delete_library_timer(ref_field)

    def _delete_library_timer(self, ref_field):
        if self.overlay is None:
            return
        timer_ref = self._library_timer_name_for(ref_field)
        if not timer_ref:
            return

        def confirmed(accepted):
            if not accepted:
                return
            self.timer_library.pop(timer_ref, None)
            self._detach_timer_references(timer_ref)
            self._refresh_after_timer_library_change()

        self.overlay.request_confirm(
            "타이머 삭제", f"'{timer_ref}' 타이머를 삭제하시겠습니까?",
            callback=confirmed,
        )

    @Slot()
    def deleteTimeupTimer(self):
        if self._kind() == "IN":
            self._delete_library_timer("timeup_timer_ref")

    @Slot()
    def deleteTimeoutTimer(self):
        if self._kind() == "IN":
            self._delete_library_timer("timeout_timer_ref")

    @Slot()
    def deleteDelayTimer(self):
        if self._kind() == "OUT":
            self.deleteLibraryTimer()

    @Slot(str)
    def renameLibraryTimer(self, timer_ref):
        if self.overlay is None:
            return
        timer_ref = str(timer_ref)
        if not timer_ref or timer_ref not in self.timer_library:
            return

        def renamed(accepted, value):
            if not accepted:
                return
            new_name = str(value).strip()
            if not new_name or new_name == timer_ref:
                return
            if new_name in self.timer_library:
                self.overlay.show_message(
                    "타이머 이름 변경",
                    f"'{new_name}' 타이머가 이미 존재합니다.", error=True,
                )
                return
            reordered = {
                (new_name if name == timer_ref else name): seconds
                for name, seconds in self.timer_library.items()
            }
            self.timer_library.clear()
            self.timer_library.update(reordered)
            for steps in self.sequences.values():
                if not isinstance(steps, list):
                    continue
                for candidate in steps:
                    for ref_field in (
                        "timer_ref", "delay_timer_ref", "timeup_timer_ref",
                        "timeout_timer_ref",
                    ):
                        if candidate.get(ref_field) == timer_ref:
                            candidate[ref_field] = new_name
                    if (candidate.get("type") == "TMR"
                            and candidate.get("name") == timer_ref):
                        candidate["name"] = new_name
            self._refresh_after_timer_library_change()

        self.overlay.request_text(
            "타이머 이름 변경", timer_ref, callback=renamed,
        )

    @Slot(str)
    def renameDelayTimer(self, timer_ref):
        self.renameLibraryTimer(timer_ref)
    @Slot(bool)
    def setTimeupEnabled(self, value):
        if self._kind() == "IN":
            self._selected()["timeup_enabled"] = bool(value)
            self._notify_row()
    @Slot(float)
    def setTimeupSeconds(self, value):
        if self._kind() == "IN":
            self._selected()["timeup_time"] = max(0.0, float(value))
            self._selected().pop("timeup_timer_ref", None)
            self._notify_row()
    @Slot(bool)
    def setTimeoutEnabled(self, value):
        if self._kind() == "IN":
            self._selected()["timeout_enabled"] = bool(value)
            if value:
                self._selected().setdefault("timeout", 5.0)
                self._selected().setdefault("timeout_action", "continue")
                self._selected().setdefault("timeout_alarm_no", 1)
            self._notify_row()
    @Slot(float)
    def setTimeoutSeconds(self, value):
        if self._kind() == "IN":
            self._selected()["timeout"] = max(0.0, float(value))
            self._selected().pop("timeout_timer_ref", None)
            self._notify_row()
    @Slot(int)
    def setTimeoutAction(self, index):
        if self._kind() == "IN": self._selected()["timeout_action"] = ("continue", "ask", "alarm_go")[max(0, min(2, index))]; self._notify_row()
    @Slot(int)
    def setTimeoutAlarmNo(self, value):
        if self._kind() == "IN": self._selected()["timeout_alarm_no"] = max(1, min(999, int(value))); self._notify_row()
    @Slot(int)
    def setTimeoutAlarmIndex(self, index):
        numbers = self._alarm_numbers()
        if self._kind() == "IN" and 0 <= index < len(numbers):
            self._selected()["timeout_alarm_no"] = numbers[index]
            self._notify_row()
    @Slot(int)
    def setTimerRefIndex(self, index):
        if self._kind() != "TMR": return
        choices = self._timer_choices(); index = max(0, min(len(choices) - 1, int(index)))
        if index == 0:
            self._selected().pop("timer_ref", None)
        else:
            ref = choices[index]
            self._selected()["timer_ref"] = ref
            self._selected()["time"] = float(self.timer_library[ref])
        self._notify_row()
    @Slot(bool)
    def setParallel(self, value):
        if self._kind() == "CALL": self._selected()["parallel"] = bool(value); self._notify_row()
    @Slot(bool)
    def setConditional(self, value):
        if self._kind() == "JMP": self._selected()["condition"] = bool(value); self._notify_row()
    @Slot(int)
    def setCondType(self, index):
        kind = ("INPUT", "BIT", "MODE", "STATE", "DTCMP", "POSITION")[
            max(0, min(5, index))
        ]
        self._selected()["cond_type"] = kind
        self._selected()["cond_value"] = 100 if kind == "BIT" else 0
        if kind == "INPUT":
            self._selected()["cond_io_type"] = 0
        elif kind == "BIT":
            ids = _internal_bit_ids()
            item_id = ids[0] if ids else -1
            self._selected()["cond_bit_id"] = item_id
            self._selected()["cond_value"] = 100 + max(0, item_id)
        elif kind == "DTCMP":
            ids = _data_ids()
            item_id = ids[0] if ids else -1
            self._selected()["cmp_data_id"] = item_id
            self._selected()["cmp_dt_addr"] = 60000 + max(0, item_id)
        elif kind == "STATE":
            self._selected()["cond_on"] = True
        elif kind == "POSITION":
            keys = self._point_keys()
            self._selected()["cond_point_name"] = keys[0] if keys else ""
            self._selected()["cond_position_axes"] = list(self.enabled_axes)
            self._selected()["cond_position_tolerance"] = 0.1
            self._selected()["cond_on"] = True
        self._notify_row()
    @Slot(int)
    def setCondValue(self, value): self._selected()["cond_value"] = int(value); self._notify_row()
    @Slot(int)
    def selectModeCondition(self, index):
        if self._kind() != "JMP" or not 0 <= int(index) < TOTAL_MODE_COUNT:
            return
        self._selected()["cond_type"] = "MODE"
        self._selected()["cond_value"] = int(index)
        self._notify_row()
    @Slot(int)
    def setRunStateIndex(self, index):
        if self._kind() != "JMP":
            return
        self._selected()["cond_type"] = "STATE"
        self._selected()["cond_value"] = max(0, min(3, int(index)))
        self._selected()["cond_on"] = True
        self._notify_row()
    @Slot(int)
    def setCondAddressIndex(self, index):
        if self._kind() != "JMP":
            return
        kind = str(self._selected().get("cond_type", "INPUT")).upper()
        if kind in ("INPUT", "VALVE"):
            count = IOManager.instance().point_count(True) if IOManager else 32
            compact = max(0, min(max(0, count - 1), int(index)))
            slot, logical = divmod(compact, 16)
            self._selected()["cond_type"] = "INPUT"
            self._selected()["cond_io_type"] = (
                IOManager.group_code(slot) if IOManager else (1 if slot else 0)
            )
            self._selected()["cond_value"] = logical
        elif kind == "BIT":
            ids = _internal_bit_ids()
            if not ids:
                return
            item_id = ids[max(0, min(len(ids) - 1, int(index)))]
            self._selected()["cond_bit_id"] = item_id
            self._selected()["cond_value"] = 100 + item_id
        else:
            return
        self._notify_row()
    @Slot(bool)
    def setCondOn(self, value): self._selected()["cond_on"] = bool(value); self._notify_row()

    @Slot(int)
    def setCondPointIndex(self, index):
        keys = self._point_keys()
        if (self._kind() == "JMP" and 0 <= int(index) < len(keys)
                and str(self._selected().get("cond_type", "")).upper() == "POSITION"):
            self._selected()["cond_point_name"] = keys[int(index)]
            self._notify_row()

    @Slot(int, bool)
    def setPositionCondAxisActive(self, index, active):
        if self._kind() != "JMP" or not 0 <= int(index) < 8:
            return
        axes = list(self._selected().get("cond_position_axes", self.enabled_axes))
        axes = (axes + [False] * 8)[:8]
        axes[int(index)] = bool(active)
        self._selected()["cond_position_axes"] = axes
        self._notify_row()

    @Slot()
    def editPositionCondTolerance(self):
        if self._kind() != "JMP" or self.overlay is None:
            return

        def valued(accepted, value):
            if accepted:
                self._selected()["cond_position_tolerance"] = round(
                    max(0.0, min(100.0, float(value))), 3,
                )
                self._notify_row()

        self.overlay.request_number(
            "포인트 위치 비교 허용오차", self._float("cond_position_tolerance", 0.1),
            decimal=True, signed=False, minimum=0.0, maximum=100.0,
            callback=valued,
        )
    @Slot(int)
    def setCmpAddress(self, value): self._selected()["cmp_dt_addr"] = max(60000, min(60099, int(value))); self._notify_row()
    @Slot(int)
    def setCmpDataIndex(self, index):
        ids = _data_ids()
        if self._kind() != "JMP" or not ids: return
        item_id = ids[max(0, min(len(ids) - 1, int(index)))]
        self._selected()["cmp_data_id"] = item_id
        self._selected()["cmp_dt_addr"] = 60000 + item_id
        self._notify_row()
    @Slot(int)
    def setCmpOp(self, value): self._selected()["cmp_op"] = max(0, min(5, int(value))); self._notify_row()
    @Slot(int)
    def setCmpConst(self, value): self._selected()["cmp_const"] = max(-(2**31), min(2**31-1, int(value))); self._notify_row()
    @Slot(int)
    def setDatAddress(self, value): self._selected()["dat_dt_addr"] = max(60000, min(60099, int(value))); self._notify_row()
    @Slot(int)
    def setDatDataIndex(self, index):
        ids = _data_ids()
        if self._kind() != "DAT" or not ids: return
        item_id = ids[max(0, min(len(ids) - 1, int(index)))]
        self._selected()["data_id"] = item_id
        self._selected()["dat_dt_addr"] = 60000 + item_id
        self._notify_row()
    @Slot(int)
    def setDatMode(self, value):
        if self._kind() != "DAT": return
        mode = "data" if int(value) == 1 else "constant"
        self._selected()["dat_mode"] = mode
        if mode == "data":
            ids = _data_ids()
            fallback = ids[0] if ids else -1
            self._selected().setdefault("dat_left_data_id", fallback)
            self._selected().setdefault("dat_right_data_id", fallback)
            self._selected().setdefault("dat_math_op", 0)
        self._notify_row()
    @Slot(int)
    def setDatOp(self, value): self._selected()["dat_op"] = max(0, min(2, int(value))); self._notify_row()
    @Slot(int)
    def setDatConst(self, value): self._selected()["dat_const"] = max(-(2**31), min(2**31-1, int(value))); self._notify_row()
    @Slot(int)
    def setDatMathOp(self, value):
        if self._kind() == "DAT":
            self._selected()["dat_math_op"] = max(0, min(3, int(value)))
            self._notify_row()

    @Slot()
    def save(self):
        monitor_steps = self.sequences.get(MONITOR_SEQ_KEY, [])
        position_rows = [index for index, step in enumerate(monitor_steps)
                         if str(step.get("type", "")).upper() == "POS"]
        position_path = self._monitor_position_path()
        if position_path:
            self.current_sequence = MONITOR_SEQ_KEY
            self.model.reset_steps(monitor_steps)
            self.selected_row = position_rows[0] if position_rows else 0
            self.changed.emit()
            self.selectionChanged.emit()
            if self.overlay is not None:
                path_text = " → ".join(position_path)
                self.overlay.show_message(
                    "저장 불가",
                    "Monitor에서 위치이동(POS)에 도달할 수 있습니다.\n"
                    f"경로: {path_text}\n"
                    "POS 스텝 또는 해당 CALL을 제거한 후 저장하세요.",
                    error=True,
                )
            return
        for sequence_name, steps in self.sequences.items():
            for index, step in enumerate(steps if isinstance(steps, list) else []):
                if str(step.get("type", "")).upper() != "WPOS":
                    continue
                point_name = str(step.get("point_name", ""))
                axes = list(step.get("active_axes", []))
                error = ""
                if point_name not in self.position_points:
                    error = "WPOS에서 기다릴 위치 포인트를 선택하세요."
                elif not any(bool(value) for value in axes[:8]):
                    error = "WPOS에서 비교할 축을 한 개 이상 선택하세요."
                elif float(step.get("timeout", 0.0)) <= 0:
                    error = "WPOS 최대 대기시간은 0보다 커야 합니다."
                if error:
                    self.current_sequence = sequence_name
                    self.model.reset_steps(steps)
                    self.selected_row = index
                    self.changed.emit()
                    self.selectionChanged.emit()
                    if self.overlay is not None:
                        self.overlay.show_message("저장 불가", error, error=True)
                    return
        for sequence_name, steps in self.sequences.items():
            for index, step in enumerate(steps if isinstance(steps, list) else []):
                if (str(step.get("type", "")).upper() != "JMP"
                        or not step.get("condition", False)
                        or str(step.get("cond_type", "")).upper() not in (
                            "POSITION", "POINT", "AXISPOS")):
                    continue
                point_name = str(step.get("cond_point_name", ""))
                axes = list(step.get("cond_position_axes", []))
                error = ""
                if point_name not in self.position_points:
                    error = "비교할 위치 포인트를 선택하세요."
                elif not any(bool(value) for value in axes[:8]):
                    error = "위치를 비교할 축을 한 개 이상 선택하세요."
                if error:
                    self.current_sequence = sequence_name
                    self.model.reset_steps(steps)
                    self.selected_row = index
                    self.changed.emit()
                    self.selectionChanged.emit()
                    if self.overlay is not None:
                        self.overlay.show_message("저장 불가", error, error=True)
                    return
        self.acceptRequested.emit()

    @Slot()
    def cancel(self): self.rejectRequested.emit()


class SequenceEditorSession(QObject):
    """Owns one editor session without creating another Qt Quick renderer."""

    changed = Signal()
    timerLibraryChanged = Signal()
    variableLibraryChanged = Signal()

    def __init__(self, parent=None, overlay=None):
        super().__init__(parent)
        self._overlay = overlay
        self._model = None
        self._backend = None
        self._callback = None
        self._visible = False
        self._sequences = {"Main": []}
        self._points = {}
        self._mode_data = []

    model = Property(QObject, lambda self: self._model, notify=changed)
    backend = Property(QObject, lambda self: self._backend, notify=changed)
    visible = Property(bool, lambda self: self._visible, notify=changed)

    def open(self, sequence_data=None, position_points=None, timer_library=None,
             mode_data=None, callback=None):
        timers = timer_library if timer_library is not None else {}
        self._points = copy.deepcopy(position_points or {})
        self._mode_data = list(mode_data or [])
        if isinstance(sequence_data, dict):
            self._sequences = copy.deepcopy(sequence_data)
        elif isinstance(sequence_data, list):
            self._sequences = {"Main": copy.deepcopy(sequence_data)}
        else:
            self._sequences = {"Main": []}
        self._sequences.setdefault("Main", [])
        normalize_all_sequences(self._sequences, timers)

        self._model = StepListModel(self)
        self._backend = SequenceEditorBackend(
            self._sequences, timers, self._points, self._model, self,
            overlay=self._overlay, mode_data=self._mode_data,
        )
        self._backend.acceptRequested.connect(lambda: self._finish(True))
        self._backend.rejectRequested.connect(lambda: self._finish(False))
        self._backend.timerLibraryChanged.connect(self.timerLibraryChanged.emit)
        self._backend.variableLibraryChanged.connect(self.variableLibraryChanged.emit)
        self._callback = callback
        self._visible = True
        self.changed.emit()

    def _finish(self, accepted):
        callback, self._callback = self._callback, None
        self._visible = False
        self.changed.emit()
        if callback is not None:
            callback(bool(accepted), self)

    def get_sequence_data(self):
        return self._sequences

    def get_position_points(self):
        return self._points
