"""Pendant-owned named variables shared by every sequence executor.

Variable IDs are stable implementation keys and are never shown as PLC
addresses.  Definitions are saved with each recipe; current values live in
RAM.  Selected values can be mirrored read-only to the PLC export block.
"""

from __future__ import annotations

import threading
from copy import deepcopy

from PySide6.QtCore import QObject, Signal


MAX_BITS = 128
MAX_DATA = 100
PLC_DATA_START = 512
PLC_DATA_END = 711
PLC_DATA_LAST_START = PLC_DATA_END - 1
INT32_MIN = -(2 ** 31)
INT32_MAX = 2 ** 31 - 1
RESET_POLICIES = ("auto", "recipe", "app", "manual")
RESET_LABELS = {
    "auto": "자동 시작 시 초기화",
    "recipe": "레시피 로드 시 초기화",
    "app": "앱 시작 시 초기화",
    "manual": "수동 초기화",
}


def _clamp_i32(value):
    return max(INT32_MIN, min(INT32_MAX, int(value)))


class VariableStore(QObject):
    definitionsChanged = Signal()
    valuesChanged = Signal()

    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.RLock()
        self._bits: list[dict] = []
        self._data: list[dict] = []
        self._bit_values: dict[int, bool] = {}
        self._data_values: dict[int, int] = {}
        # IDs are stable pendant-only implementation keys. PLC addresses are
        # assigned separately and only when a data value is explicitly shared.
        self._next_bit_id = 0
        self._next_data_id = 0
        self._dirty_bits = True
        self._dirty_data: set[int] = set()
        self._pending_data_clears: set[int] = set()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _normalise_policy(value):
        value = str(value or "auto")
        return value if value in RESET_POLICIES else "auto"

    @staticmethod
    def _unique_name(items, requested, fallback):
        base = str(requested or fallback).strip() or fallback
        used = {str(item.get("name", "")).strip() for item in items}
        if base not in used:
            return base
        suffix = 2
        while f"{base} {suffix}" in used:
            suffix += 1
        return f"{base} {suffix}"

    @staticmethod
    def _definition(raw, kind):
        item_id = int(raw.get("id", 0))
        initial = bool(raw.get("initial", False)) if kind == "bit" \
            else _clamp_i32(raw.get("initial", 0))
        published = bool(raw.get("plc_publish", False))
        address = None
        if kind == "data" and published:
            raw_address = raw.get("plc_dt_address")
            # Version 2 recipes used a hidden ID-derived address. Preserve it
            # once during migration, but all new assignments are explicit.
            if raw_address is None:
                raw_address = PLC_DATA_START + item_id * 2
            try:
                candidate = int(raw_address)
                if (PLC_DATA_START <= candidate <= PLC_DATA_LAST_START
                        and (candidate - PLC_DATA_START) % 2 == 0):
                    address = candidate
                else:
                    published = False
            except (TypeError, ValueError):
                published = False
        return {
            "id": item_id,
            "name": str(raw.get("name", "")).strip(),
            "initial": initial,
            "reset_policy": VariableStore._normalise_policy(
                raw.get("reset_policy", "auto")
            ),
            "plc_publish": published,
            **({"plc_dt_address": address} if kind == "data" else {}),
        }

    def bit_definitions(self):
        with self._lock:
            return deepcopy(sorted(self._bits, key=lambda item: item["id"]))

    def data_definitions(self):
        with self._lock:
            return deepcopy(sorted(self._data, key=lambda item: item["id"]))

    def bit_ids(self):
        return [item["id"] for item in self.bit_definitions()]

    def data_ids(self):
        return [item["id"] for item in self.data_definitions()]

    def _find(self, kind, item_id):
        items = self._bits if kind == "bit" else self._data
        item_id = int(item_id)
        return next((item for item in items if int(item["id"]) == item_id), None)

    def bit_name(self, item_id):
        with self._lock:
            item = self._find("bit", item_id)
            return str(item["name"]) if item else f"내부비트 {int(item_id) + 1}"

    def data_name(self, item_id):
        with self._lock:
            item = self._find("data", item_id)
            return str(item["name"]) if item else f"데이터 {int(item_id) + 1}"

    def add_bit(self, name="", initial=False, *, item_id=None):
        with self._lock:
            if item_id is None:
                item_id = self._next_bit_id if self._next_bit_id < MAX_BITS else None
            else:
                item_id = int(item_id)
            if item_id is None or not 0 <= item_id < MAX_BITS:
                raise ValueError(f"내부비트는 최대 {MAX_BITS}개까지 만들 수 있습니다.")
            existing = self._find("bit", item_id)
            if existing:
                return item_id
            item = {
                "id": item_id,
                "name": self._unique_name(self._bits, name, f"내부비트 {item_id + 1}"),
                "initial": bool(initial),
                "reset_policy": "auto",
                "plc_publish": False,
            }
            self._bits.append(item)
            self._bit_values[item_id] = bool(initial)
            self._next_bit_id = max(self._next_bit_id, item_id + 1)
            self._dirty_bits = True
        self.definitionsChanged.emit(); self.valuesChanged.emit()
        return item_id

    def add_data(self, name="", initial=0, *, item_id=None):
        with self._lock:
            if item_id is None:
                item_id = self._next_data_id if self._next_data_id < MAX_DATA else None
            else:
                item_id = int(item_id)
            if item_id is None or not 0 <= item_id < MAX_DATA:
                raise ValueError(f"데이터는 최대 {MAX_DATA}개까지 만들 수 있습니다.")
            existing = self._find("data", item_id)
            if existing:
                return item_id
            initial = _clamp_i32(initial)
            item = {
                "id": item_id,
                "name": self._unique_name(self._data, name, f"데이터 {item_id + 1}"),
                "initial": initial,
                "reset_policy": "auto",
                "plc_publish": False,
                "plc_dt_address": None,
            }
            self._data.append(item)
            self._data_values[item_id] = initial
            self._next_data_id = max(self._next_data_id, item_id + 1)
            self._dirty_data.add(item_id)
        self.definitionsChanged.emit(); self.valuesChanged.emit()
        return item_id

    def remove(self, kind, item_id):
        with self._lock:
            items = self._bits if kind == "bit" else self._data
            removed = next(
                (item for item in items if int(item["id"]) == int(item_id)), None,
            )
            before = len(items)
            items[:] = [item for item in items if int(item["id"]) != int(item_id)]
            if len(items) == before:
                return False
            if kind == "bit":
                self._bit_values.pop(int(item_id), None)
                self._dirty_bits = True
            else:
                if removed and removed.get("plc_dt_address") is not None:
                    self._pending_data_clears.add(int(removed["plc_dt_address"]))
                self._data_values.pop(int(item_id), None)
                self._dirty_data.add(int(item_id))
        self.definitionsChanged.emit(); self.valuesChanged.emit()
        return True

    def rename(self, kind, item_id, name):
        with self._lock:
            item = self._find(kind, item_id)
            if not item:
                return False
            items = self._bits if kind == "bit" else self._data
            others = [candidate for candidate in items if candidate is not item]
            item["name"] = self._unique_name(
                others, name, "내부비트" if kind == "bit" else "데이터"
            )
        self.definitionsChanged.emit()
        return True

    def set_initial(self, kind, item_id, value, *, apply_now=True):
        with self._lock:
            item = self._find(kind, item_id)
            if not item:
                return False
            value = bool(value) if kind == "bit" else _clamp_i32(value)
            item["initial"] = value
        if apply_now:
            if kind == "bit":
                self.set_bit(item_id, value)
            else:
                self.set_data(item_id, value)
        self.definitionsChanged.emit()
        return True

    def set_publish(self, kind, item_id, enabled, *, address=None):
        with self._lock:
            item = self._find(kind, item_id)
            if not item:
                return False
            if kind == "bit":
                item["plc_publish"] = bool(enabled)
                self._dirty_bits = True
            else:
                old_address = item.get("plc_dt_address")
                if not enabled:
                    item["plc_publish"] = False
                    item["plc_dt_address"] = None
                    if old_address is not None:
                        self._pending_data_clears.add(int(old_address))
                else:
                    if address is None:
                        raise ValueError("PLC로 공개할 데이터의 DT 시작 주소를 선택하세요.")
                    address = int(address)
                    if not (PLC_DATA_START <= address <= PLC_DATA_LAST_START):
                        raise ValueError(
                            f"DINT 시작 주소는 DT{PLC_DATA_START}~DT{PLC_DATA_LAST_START} 범위여야 합니다."
                        )
                    if (address - PLC_DATA_START) % 2:
                        raise ValueError("DINT는 2워드이므로 짝수 DT 시작 주소를 선택하세요.")
                    conflict = next((
                        candidate for candidate in self._data
                        if int(candidate["id"]) != int(item_id)
                        and candidate.get("plc_publish")
                        and candidate.get("plc_dt_address") == address
                    ), None)
                    if conflict:
                        raise ValueError(
                            f"DT{address}~DT{address + 1}은(는) "
                            f"'{conflict['name']}'에서 사용 중입니다."
                        )
                    if old_address is not None and int(old_address) != address:
                        self._pending_data_clears.add(int(old_address))
                    item["plc_publish"] = True
                    item["plc_dt_address"] = address
                self._dirty_data.add(int(item_id))
        self.definitionsChanged.emit()
        return True

    def data_plc_address(self, item_id):
        with self._lock:
            item = self._find("data", item_id)
            if not item or not item.get("plc_publish"):
                return None
            address = item.get("plc_dt_address")
            return int(address) if address is not None else None

    def next_free_data_plc_address(self):
        with self._lock:
            used = {
                int(item["plc_dt_address"])
                for item in self._data
                if item.get("plc_publish") and item.get("plc_dt_address") is not None
            }
            return next((
                address for address in range(
                    PLC_DATA_START, PLC_DATA_LAST_START + 1, 2,
                ) if address not in used
            ), None)

    def cycle_reset_policy(self, kind, item_id):
        with self._lock:
            item = self._find(kind, item_id)
            if not item:
                return "auto"
            current = self._normalise_policy(item.get("reset_policy"))
            item["reset_policy"] = RESET_POLICIES[
                (RESET_POLICIES.index(current) + 1) % len(RESET_POLICIES)
            ]
            result = item["reset_policy"]
        self.definitionsChanged.emit()
        return result

    def get_bit(self, item_id):
        with self._lock:
            return bool(self._bit_values.get(int(item_id), False))

    def set_bit(self, item_id, value):
        item_id = int(item_id)
        with self._lock:
            if not self._find("bit", item_id):
                self.add_bit(item_id=item_id)
            value = bool(value)
            changed = self._bit_values.get(item_id) != value
            self._bit_values[item_id] = value
            if changed:
                self._dirty_bits = True
        if changed:
            self.valuesChanged.emit()
        return value

    def get_data(self, item_id):
        with self._lock:
            return int(self._data_values.get(int(item_id), 0))

    def set_data(self, item_id, value):
        item_id = int(item_id)
        with self._lock:
            if not self._find("data", item_id):
                self.add_data(item_id=item_id)
            value = _clamp_i32(value)
            changed = self._data_values.get(item_id) != value
            self._data_values[item_id] = value
            if changed:
                self._dirty_data.add(item_id)
        if changed:
            self.valuesChanged.emit()
        return value

    def operate_data(self, item_id, operation, operand):
        item_id = int(item_id)
        operation = int(operation)
        operand = int(operand)
        with self._lock:
            current = self.get_data(item_id)
            result = operand if operation == 0 else current + operand if operation == 1 \
                else current - operand if operation == 2 else current
            return self.set_data(item_id, result)

    def calculate_data(self, target_id, left_id, operation, right_id):
        """Atomically evaluate two data values and store the signed DINT result."""
        target_id = int(target_id)
        left_id = int(left_id)
        right_id = int(right_id)
        operation = int(operation)
        with self._lock:
            left = self.get_data(left_id)
            right = self.get_data(right_id)
            if operation == 0:
                result = left + right
            elif operation == 1:
                result = left - right
            elif operation == 2:
                result = left * right
            elif operation == 3:
                if right == 0:
                    raise ZeroDivisionError("데이터 나눗셈의 제수가 0입니다.")
                quotient = abs(left) // abs(right)
                result = -quotient if (left < 0) != (right < 0) else quotient
            else:
                raise ValueError(f"unsupported data math operation: {operation}")
            return self.set_data(target_id, result)

    def reset(self, reason):
        with self._lock:
            for item in self._bits:
                if item.get("reset_policy") == reason:
                    self._bit_values[item["id"]] = bool(item["initial"])
            for item in self._data:
                if item.get("reset_policy") == reason:
                    self._data_values[item["id"]] = _clamp_i32(item["initial"])
                    self._dirty_data.add(item["id"])
            self._dirty_bits = True
        self.valuesChanged.emit()

    def reset_auto(self):
        self.reset("auto")

    def mark_all_dirty(self):
        with self._lock:
            self._dirty_bits = True
            self._dirty_data.update(int(item["id"]) for item in self._data)

    def export_snapshot(self, *, consume=True):
        with self._lock:
            bits_dirty = self._dirty_bits
            data_dirty = set(self._dirty_data)
            bit_words = [0] * 8
            for item in self._bits:
                item_id = int(item["id"])
                if item.get("plc_publish") and self._bit_values.get(item_id, False):
                    bit_words[item_id // 16] |= 1 << (item_id % 16)
            data_values = {int(address): 0 for address in self._pending_data_clears}
            for item in self._data:
                item_id = int(item["id"])
                address = item.get("plc_dt_address")
                if (item_id in data_dirty and item.get("plc_publish")
                        and address is not None):
                    data_values[int(address)] = self._data_values.get(item_id, 0)
            if consume:
                self._dirty_bits = False
                self._dirty_data.clear()
                self._pending_data_clears.clear()
            return bits_dirty, bit_words, data_values

    def to_dict(self):
        with self._lock:
            return {
                "version": 3,
                "next_bit_id": self._next_bit_id,
                "next_data_id": self._next_data_id,
                "bits": deepcopy(sorted(self._bits, key=lambda item: item["id"])),
                "data": deepcopy(sorted(self._data, key=lambda item: item["id"])),
            }

    def load_from_dict(self, raw, sequences=None):
        raw = raw if isinstance(raw, dict) else {}
        bits = []
        data = []
        for item in raw.get("bits", []) if isinstance(raw.get("bits", []), list) else []:
            try:
                definition = self._definition(item, "bit")
                if 0 <= definition["id"] < MAX_BITS and definition["name"]:
                    bits.append(definition)
            except (TypeError, ValueError):
                continue
        for item in raw.get("data", []) if isinstance(raw.get("data", []), list) else []:
            try:
                definition = self._definition(item, "data")
                if 0 <= definition["id"] < MAX_DATA and definition["name"]:
                    data.append(definition)
            except (TypeError, ValueError):
                continue
        # Invalid/duplicate legacy assignments stay pendant-internal instead
        # of silently sharing the same PLC words.
        used_addresses = set()
        for item in sorted(data, key=lambda row: row["id"]):
            address = item.get("plc_dt_address")
            if item.get("plc_publish") and address in used_addresses:
                item["plc_publish"] = False
                item["plc_dt_address"] = None
            elif item.get("plc_publish") and address is not None:
                used_addresses.add(address)
        with self._lock:
            previous_addresses = {
                int(item["plc_dt_address"])
                for item in self._data
                if item.get("plc_publish") and item.get("plc_dt_address") is not None
            }
            self._bits = sorted({item["id"]: item for item in bits}.values(), key=lambda x: x["id"])
            self._data = sorted({item["id"]: item for item in data}.values(), key=lambda x: x["id"])
            self._bit_values = {item["id"]: bool(item["initial"]) for item in self._bits}
            self._data_values = {item["id"]: _clamp_i32(item["initial"]) for item in self._data}
            min_next_bit = max((item["id"] + 1 for item in self._bits), default=0)
            min_next_data = max((item["id"] + 1 for item in self._data), default=0)
            self._next_bit_id = max(min_next_bit, int(raw.get("next_bit_id", 0)))
            self._next_data_id = max(min_next_data, int(raw.get("next_data_id", 0)))
            new_addresses = {
                int(item["plc_dt_address"])
                for item in self._data
                if item.get("plc_publish") and item.get("plc_dt_address") is not None
            }
            self._pending_data_clears.update(previous_addresses - new_addresses)
        self.ensure_legacy_references(sequences or {})
        self.mark_all_dirty()
        self.definitionsChanged.emit(); self.valuesChanged.emit()

    def ensure_legacy_references(self, sequences):
        """Migrate fixed M/virtual-DT recipe fields to stable variable IDs."""
        try:
            from utils.internal_bit_names import load_all
            legacy_names = load_all()
        except Exception:
            legacy_names = {}
        step_lists = sequences.values() if isinstance(sequences, dict) else ()
        for steps in step_lists:
            if not isinstance(steps, list):
                continue
            for step in steps:
                kind = str(step.get("type", "")).upper()
                io_type = int(step.get("out_type" if kind == "OUT" else "in_type", 0))
                if kind in ("OUT", "IN") and io_type == 2:
                    raw_port = int(step.get("port", 0))
                    item_id = int(step.get("bit_id", raw_port - 100 if raw_port >= 100 else raw_port))
                    if 0 <= item_id < MAX_BITS:
                        self.add_bit(legacy_names.get(f"M{item_id:02d}", ""), item_id=item_id)
                        step["bit_id"] = item_id
                cond_type = str(step.get("cond_type", "")).upper()
                if kind == "JMP" and cond_type in ("BIT", "INTERNAL"):
                    raw_value = int(step.get("cond_value", 100))
                    item_id = int(step.get("cond_bit_id", raw_value - 100 if raw_value >= 100 else raw_value))
                    if 0 <= item_id < MAX_BITS:
                        self.add_bit(legacy_names.get(f"M{item_id:02d}", ""), item_id=item_id)
                        step["cond_bit_id"] = item_id
                if kind == "DAT":
                    raw_address = int(step.get("dat_dt_addr", 60000))
                    item_id = int(step.get("data_id", raw_address - 60000))
                    if 0 <= item_id < MAX_DATA:
                        self.add_data(item_id=item_id)
                        step["data_id"] = item_id
                    if str(step.get("dat_mode", "constant")) == "data":
                        for field in ("dat_left_data_id", "dat_right_data_id"):
                            source_id = int(step.get(field, -1))
                            if 0 <= source_id < MAX_DATA:
                                self.add_data(item_id=source_id)
                if kind == "JMP" and cond_type in ("DTCMP", "DT", "DATA"):
                    raw_address = int(step.get("cmp_dt_addr", 60000))
                    item_id = int(step.get("cmp_data_id", raw_address - 60000))
                    if 0 <= item_id < MAX_DATA:
                        self.add_data(item_id=item_id)
                        step["cmp_data_id"] = item_id
