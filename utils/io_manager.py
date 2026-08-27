"""Shared configurable PLC I/O group and name registry.

Each configured group represents one 16-bit PLC word.  Input group slots map
to DT140..DT143, output request slots to DT210..DT213, and output feedback
slots to DT144..DT147.  ``start`` only controls the PLC-style X/Y address
shown to the operator; the group slot controls the DT word.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


MAX_GROUPS = 4
POINTS_PER_GROUP = 16
MAX_POINTS = MAX_GROUPS * POINTS_PER_GROUP

# Numeric step type 2 is internal M bits and 3 is a legacy mode input.
PHYSICAL_GROUP_CODES = (0, 1, 4, 5)

DEFAULT_INPUT_GROUPS = [0x00, 0x20]
DEFAULT_OUTPUT_GROUPS = [0x00, 0x20]

OUTPUT_RESET = "RESET"
OUTPUT_LATCH = "LATCH"

DEFAULT_INPUTS = [
    "비상정지", "안전문", "사출기 전자동", "형개완료",
    "형폐완료", "에젝터 전진완료", "에젝터 후퇴완료", "예비1",
] + [f"X{i:02X}" for i in range(8, 16)] \
    + [f"X{i:02X}" for i in range(0x20, 0x30)] + [""] * 32

DEFAULT_OUTPUTS = [
    "형개허가", "형폐허가", "에젝터 허가", "싸이클스타트",
    "컨베어출력1", "컨베어출력2", "예비1", "예비2",
] + [f"Y{i:02X}" for i in range(8, 16)] \
    + [f"Y{i:02X}" for i in range(0x20, 0x30)] + [""] * 32


def _normalise_groups(values, defaults):
    groups = []
    for value in values if isinstance(values, (list, tuple)) else ():
        if isinstance(value, dict):
            value = value.get("start", 0)
        try:
            start = int(value)
        except (TypeError, ValueError):
            continue
        start = max(0, min(0xF0, start)) & 0xF0
        if start not in groups:
            groups.append(start)
        if len(groups) >= MAX_GROUPS:
            break
    return groups or list(defaults)


def _padded_names(values, defaults):
    result = list(defaults[:MAX_POINTS])
    if len(result) < MAX_POINTS:
        result.extend([""] * (MAX_POINTS - len(result)))
    for index, value in enumerate(values if isinstance(values, (list, tuple)) else ()):
        if index >= MAX_POINTS:
            break
        result[index] = str(value)
    return result


def _padded_output_stop_modes(values, defaults=None):
    source = values if isinstance(values, (list, tuple)) else ()
    fallback = defaults if isinstance(defaults, (list, tuple)) else ()
    result = []
    for index in range(MAX_POINTS):
        value = source[index] if index < len(source) else (
            fallback[index] if index < len(fallback) else OUTPUT_RESET
        )
        result.append(OUTPUT_LATCH if str(value).upper() == OUTPUT_LATCH else OUTPUT_RESET)
    return result


class IOManager(QObject):
    sig_names_changed = Signal()

    _instance = None

    def __init__(self):
        super().__init__()
        self.inputs = list(DEFAULT_INPUTS)
        self.outputs = list(DEFAULT_OUTPUTS)
        self.input_groups = list(DEFAULT_INPUT_GROUPS)
        self.output_groups = list(DEFAULT_OUTPUT_GROUPS)
        # Backward-compatible and fail-safe default: outputs created before
        # this setting existed are reset when automatic operation stops.
        self.output_stop_modes = [OUTPUT_RESET] * MAX_POINTS

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def group_code(slot):
        slot = int(slot)
        return PHYSICAL_GROUP_CODES[slot] if 0 <= slot < MAX_GROUPS else 0

    @staticmethod
    def group_slot(type_code):
        try:
            return PHYSICAL_GROUP_CODES.index(int(type_code))
        except ValueError:
            return 0

    def groups(self, is_input):
        return list(self.input_groups if is_input else self.output_groups)

    def group_count(self, is_input):
        return len(self.input_groups if is_input else self.output_groups)

    def point_count(self, is_input):
        return self.group_count(is_input) * POINTS_PER_GROUP

    def address(self, is_input, compact_index):
        compact_index = int(compact_index)
        slot, bit = divmod(max(0, compact_index), POINTS_PER_GROUP)
        groups = self.input_groups if is_input else self.output_groups
        start = groups[slot] if 0 <= slot < len(groups) else slot * 0x10
        return f"{'X' if is_input else 'Y'}{start + bit:02X}"

    def group_label(self, is_input, slot):
        groups = self.input_groups if is_input else self.output_groups
        if not 0 <= int(slot) < len(groups):
            return ""
        start = groups[int(slot)]
        prefix = "X" if is_input else "Y"
        return f"그룹 {int(slot) + 1}  {prefix}{start:02X}~{prefix}{start + 15:02X}"

    def display_label(self, is_input, compact_index):
        address = self.address(is_input, compact_index)
        name = (self.get_input_name(compact_index) if is_input
                else self.get_output_name(compact_index))
        return f"{address} [{name}]" if str(name).strip() and name != address else address

    def load_from_dict(self, data):
        data = data if isinstance(data, dict) else {}
        self.input_groups = _normalise_groups(
            data.get("input_groups", []), DEFAULT_INPUT_GROUPS,
        )
        self.output_groups = _normalise_groups(
            data.get("output_groups", []), DEFAULT_OUTPUT_GROUPS,
        )
        self.inputs = _padded_names(data.get("inputs", []), DEFAULT_INPUTS)
        self.outputs = _padded_names(data.get("outputs", []), DEFAULT_OUTPUTS)
        self.output_stop_modes = _padded_output_stop_modes(
            data.get("output_stop_modes", []), [OUTPUT_RESET] * MAX_POINTS,
        )
        self.sig_names_changed.emit()

    def to_dict(self):
        return {
            "input_groups": list(self.input_groups),
            "output_groups": list(self.output_groups),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "output_stop_modes": list(self.output_stop_modes),
        }

    def update_names(self, new_inputs, new_outputs, output_stop_modes=None):
        self.inputs = _padded_names(new_inputs, self.inputs)
        self.outputs = _padded_names(new_outputs, self.outputs)
        if output_stop_modes is not None:
            self.output_stop_modes = _padded_output_stop_modes(
                output_stop_modes, self.output_stop_modes,
            )
        self.sig_names_changed.emit()

    def set_groups(self, is_input, starts):
        current = self.input_groups if is_input else self.output_groups
        groups = _normalise_groups(starts, current or [0])
        if is_input:
            self.input_groups = groups
        else:
            self.output_groups = groups
        self.sig_names_changed.emit()

    def set_group_configuration(self, is_input, starts, names, output_stop_modes=None):
        """Apply group layout and its compact name table as one update."""
        current_groups = self.input_groups if is_input else self.output_groups
        groups = _normalise_groups(starts, current_groups or [0])
        current_names = self.inputs if is_input else self.outputs
        padded = _padded_names(names, current_names)
        if is_input:
            self.input_groups = groups
            self.inputs = padded
        else:
            self.output_groups = groups
            self.outputs = padded
            if output_stop_modes is not None:
                self.output_stop_modes = _padded_output_stop_modes(
                    output_stop_modes, self.output_stop_modes,
                )
        self.sig_names_changed.emit()

    def get_input_name(self, idx):
        idx = int(idx)
        if 0 <= idx < len(self.inputs) and str(self.inputs[idx]).strip():
            return self.inputs[idx]
        return self.address(True, idx)

    def get_output_name(self, idx):
        idx = int(idx)
        if 0 <= idx < len(self.outputs) and str(self.outputs[idx]).strip():
            return self.outputs[idx]
        return self.address(False, idx)

    def get_output_stop_mode(self, idx):
        idx = int(idx)
        if 0 <= idx < len(self.output_stop_modes):
            return self.output_stop_modes[idx]
        return OUTPUT_RESET

    def reset_output_indices(self):
        """Return configured compact output indices that reset on auto stop."""
        return [
            index for index in range(self.point_count(False))
            if self.get_output_stop_mode(index) == OUTPUT_RESET
        ]
