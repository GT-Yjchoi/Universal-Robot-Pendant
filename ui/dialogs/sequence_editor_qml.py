"""QML sequence editor with a Python data model and legacy recipe compatibility."""

from __future__ import annotations

import copy
import os

from PySide6.QtCore import (
    QByteArray,
    Property,
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor
from PySide6.QtQuickWidgets import QQuickWidget

from ui.dialogs.sequence_editor_dialog import MONITOR_SEQ_KEY, normalize_all_sequences


_QML_PATH = os.path.join(os.path.dirname(__file__), "SequenceEditor.qml")
_COLORS = {
    "POS": "#468CFF", "OUT": "#FFA500", "IN": "#FF69B4",
    "TMR": "#F1C40F", "JMP": "#00E5FF", "CALL": "#FF00FF",
    "DAT": "#00FF9C", "END": "#FF4646", "COMMENT": "#FFD700",
}


def _summary(step: dict, row: int) -> str:
    kind = str(step.get("type", "")).upper()
    if kind == "COMMENT":
        return f"// {step.get('text', '')}"
    name = step.get("name") or f"{kind} {row + 1}"
    if kind in ("OUT", "IN"):
        channel = int(step.get("port", step.get("dio_channel", 0)))
        state = "ON" if step.get("on", True) else "OFF"
        group = int(step.get("out_type" if kind == "OUT" else "in_type", 0))
        labels = ("SYS", "VALVE", "M")
        return f"{name}  ·  {labels[min(group, 2)]}{channel} {state}"
    if kind == "TMR":
        return f"{name}  ·  {float(step.get('time', 0)):.3f}s"
    if kind == "JMP":
        return f"{name}  ·  → {int(step.get('target_idx', 0)) + 1}"
    if kind == "CALL":
        return f"{name}  ·  {step.get('target_seq', '')}"
    if kind == "POS":
        return f"{name}  ·  {step.get('point_name', '')}"
    if kind == "DAT":
        ops = ("=", "+=", "-=")
        op = max(0, min(2, int(step.get("dat_op", 0))))
        return f"{name}  ·  DT{int(step.get('dat_dt_addr', 60000))} {ops[op]} {int(step.get('dat_const', 0))}"
    return str(name)


class StepListModel(QAbstractListModel):
    TypeRole = Qt.UserRole + 1
    SummaryRole = Qt.UserRole + 2
    ColorRole = Qt.UserRole + 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps: list[dict] = []

    def roleNames(self):
        return {
            self.TypeRole: QByteArray(b"stepType"),
            self.SummaryRole: QByteArray(b"summary"),
            self.ColorRole: QByteArray(b"stepColor"),
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self.steps)

    def data(self, index, role):
        row = index.row()
        if not 0 <= row < len(self.steps):
            return None
        step = self.steps[row]
        kind = str(step.get("type", "")).upper()
        return {
            self.TypeRole: kind,
            self.SummaryRole: _summary(step, row),
            self.ColorRole: _COLORS.get(kind, "#95A5A6"),
        }.get(role)

    def reset_steps(self, steps):
        self.beginResetModel()
        self.steps = steps
        self.endResetModel()

    def refresh(self, row):
        if 0 <= row < len(self.steps):
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, [self.TypeRole, self.SummaryRole, self.ColorRole])


class SequenceEditorBackend(QObject):
    changed = Signal()
    selectionChanged = Signal()
    acceptRequested = Signal()
    rejectRequested = Signal()

    def __init__(self, sequences, timer_library, position_points, model, parent=None):
        super().__init__(parent)
        self.sequences = sequences
        self.timer_library = timer_library
        self.position_points = position_points
        self.model = model
        self.current_sequence = "Main" if "Main" in sequences else next(iter(sequences))
        self.selected_row = -1
        self.model.reset_steps(self.sequences[self.current_sequence])

    def _keys(self):
        reserved = {"Main", MONITOR_SEQ_KEY}
        keys = ["Main"] if "Main" in self.sequences else []
        keys.extend(sorted(k for k in self.sequences if k not in reserved))
        if MONITOR_SEQ_KEY in self.sequences:
            keys.append(MONITOR_SEQ_KEY)
        return keys

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
        if step.get("type") == "IN":
            if kind == 1 and value >= 32: value -= 32
            if kind == 2 and value >= 100: value -= 100
        return max(0, min(31, value))
    def _io_type(self):
        step = self._selected(); key = "out_type" if step.get("type") == "OUT" else "in_type"
        return max(0, min(2, int(step.get(key, 0)))) if step else 0
    def _on(self): return bool(self._selected().get("on", True))
    def _seconds(self): return float(self._selected().get("time", 1.0)) if self._selected() else 1.0
    def _target_index(self): return int(self._selected().get("target_idx", 0)) if self._selected() else 0
    def _target_sequence(self): return str(self._selected().get("target_seq", ""))
    def _point_keys(self): return sorted(self.position_points.keys())
    def _point_index(self):
        keys = self._point_keys(); value = str(self._selected().get("point_name", ""))
        return keys.index(value) if value in keys else -1
    def _bool(self, key, default=False): return bool(self._selected().get(key, default))
    def _float(self, key, default=0.0): return float(self._selected().get(key, default))
    def _int(self, key, default=0): return int(self._selected().get(key, default))
    def _timeout_action_index(self):
        return {"continue": 0, "ask": 1, "alarm_go": 2}.get(str(self._selected().get("timeout_action", "continue")), 0)
    def _cond_type_index(self):
        return ["INPUT", "VALVE", "BIT", "MODE", "STATE", "DTCMP"].index(
            str(self._selected().get("cond_type", "INPUT")).upper()
        ) if str(self._selected().get("cond_type", "INPUT")).upper() in ["INPUT", "VALVE", "BIT", "MODE", "STATE", "DTCMP"] else 0
    def _step_targets(self): return [_summary(s, i) for i, s in enumerate(self.model.steps)]
    def _target_seq_index(self):
        keys = [k for k in self._keys() if k != self.current_sequence]
        target = self._target_sequence()
        return keys.index(target) if target in keys else -1

    sequenceKeys = Property(list, _keys, notify=changed)
    sequenceIndex = Property(int, _seq_index, notify=changed)
    selectedRow = Property(int, lambda self: self.selected_row, notify=selectionChanged)
    selectedType = Property(str, _kind, notify=selectionChanged)
    selectedName = Property(str, _name, notify=selectionChanged)
    selectedChannel = Property(int, _channel, notify=selectionChanged)
    selectedIoType = Property(int, _io_type, notify=selectionChanged)
    selectedOn = Property(bool, _on, notify=selectionChanged)
    selectedSeconds = Property(float, _seconds, notify=selectionChanged)
    selectedTargetIndex = Property(int, _target_index, notify=selectionChanged)
    selectedTargetSequence = Property(str, _target_sequence, notify=selectionChanged)
    stepTargets = Property(list, _step_targets, notify=changed)
    targetSequenceKeys = Property(list, lambda self: [k for k in self._keys() if k != self.current_sequence], notify=changed)
    targetSequenceIndex = Property(int, _target_seq_index, notify=selectionChanged)
    pointKeys = Property(list, _point_keys, notify=changed)
    selectedPointIndex = Property(int, _point_index, notify=selectionChanged)
    selectedWaitCompletion = Property(bool, lambda s: s._bool("wait_completion", True), notify=selectionChanged)
    selectedPackBase = Property(bool, lambda s: s._bool("pack_base"), notify=selectionChanged)
    selectedDelayEnabled = Property(bool, lambda s: s._bool("delay_enable"), notify=selectionChanged)
    selectedDelaySeconds = Property(float, lambda s: s._float("delay_time"), notify=selectionChanged)
    selectedTimeoutEnabled = Property(bool, lambda s: s._bool("timeout_enabled"), notify=selectionChanged)
    selectedTimeoutSeconds = Property(float, lambda s: s._float("timeout", 5.0), notify=selectionChanged)
    selectedTimeoutAction = Property(int, _timeout_action_index, notify=selectionChanged)
    selectedParallel = Property(bool, lambda s: s._bool("parallel"), notify=selectionChanged)
    selectedConditional = Property(bool, lambda s: s._bool("condition"), notify=selectionChanged)
    selectedCondType = Property(int, _cond_type_index, notify=selectionChanged)
    selectedCondValue = Property(int, lambda s: s._int("cond_value"), notify=selectionChanged)
    selectedCondOn = Property(bool, lambda s: s._bool("cond_on", True), notify=selectionChanged)
    selectedCmpAddress = Property(int, lambda s: s._int("cmp_dt_addr", 60000), notify=selectionChanged)
    selectedCmpOp = Property(int, lambda s: s._int("cmp_op", 0), notify=selectionChanged)
    selectedCmpConst = Property(int, lambda s: s._int("cmp_const"), notify=selectionChanged)
    selectedDatAddress = Property(int, lambda s: s._int("dat_dt_addr", 60000), notify=selectionChanged)
    selectedDatOp = Property(int, lambda s: s._int("dat_op", 0), notify=selectionChanged)
    selectedDatConst = Property(int, lambda s: s._int("dat_const"), notify=selectionChanged)

    def _notify_row(self):
        self.model.refresh(self.selected_row)
        self.selectionChanged.emit()
        self.changed.emit()

    @Slot(int)
    def selectSequence(self, index):
        keys = self._keys()
        if 0 <= index < len(keys):
            self.current_sequence = keys[index]
            self.selected_row = -1
            self.model.reset_steps(self.sequences[self.current_sequence])
            self.changed.emit(); self.selectionChanged.emit()

    @Slot()
    def addSequence(self):
        number = 1
        while f"Sub{number}" in self.sequences:
            number += 1
        self.current_sequence = f"Sub{number}"
        self.sequences[self.current_sequence] = []
        self.selected_row = -1
        self.model.reset_steps(self.sequences[self.current_sequence])
        self.changed.emit(); self.selectionChanged.emit()

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
        self.selected_row = -1
        self.model.reset_steps(self.sequences["Main"])
        self.changed.emit(); self.selectionChanged.emit()

    @Slot(int)
    def selectStep(self, row):
        self.selected_row = row if 0 <= row < len(self.model.steps) else -1
        self.selectionChanged.emit()

    @Slot(str)
    def addStep(self, kind):
        kind = kind.upper()
        count = sum(1 for s in self.model.steps if s.get("type") == kind) + 1
        data = {"type": kind, "name": f"{kind}_{count}"}
        if kind in ("OUT", "IN"):
            data.update({"port": 0, "on": True,
                         "out_type" if kind == "OUT" else "in_type": 0})
            if kind == "OUT": data["delay_enable"] = False
            else: data.update({"timeout_enabled": False, "timeout_action": "continue"})
        elif kind == "POS":
            data.update({"point_name": self._point_keys()[0] if self._point_keys() else "",
                         "active_axes": [True] * 8, "wait_completion": True})
        elif kind == "TMR": data["time"] = 1.0
        elif kind == "JMP": data.update({"target_idx": 0, "condition": False,
                                          "cond_type": "INPUT", "cond_value": 0,
                                          "cond_on": True, "cmp_dt_addr": 60000,
                                          "cmp_op": 0, "cmp_const": 0})
        elif kind == "CALL": data.update({"target_seq": "", "parallel": False})
        elif kind == "DAT": data.update({"dat_dt_addr": 60000, "dat_op": 0, "dat_const": 0})
        elif kind == "COMMENT": data = {"type": "COMMENT", "text": "메모"}
        elif kind == "END": data["name"] = "END"
        self.model.beginInsertRows(QModelIndex(), len(self.model.steps), len(self.model.steps))
        self.model.steps.append(data)
        self.model.endInsertRows()
        self.selected_row = len(self.model.steps) - 1
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
        self.model.beginResetModel()
        self.model.steps[old], self.model.steps[new] = self.model.steps[new], self.model.steps[old]
        self.model.endResetModel()
        self.selected_row = new
        self.selectionChanged.emit(); self.changed.emit()

    @Slot(str)
    def setName(self, value):
        step = self._selected()
        if not step: return
        step["text" if step.get("type") == "COMMENT" else "name"] = value
        self._notify_row()

    @Slot(int)
    def setChannel(self, channel):
        step = self._selected()
        if not step: return
        kind = self._io_type(); logical = max(0, min(31 if kind == 2 else 15, int(channel)))
        if step.get("type") == "IN":
            step["port"] = logical + (32 if kind == 1 else 100 if kind == 2 else 0)
        else:
            step["port"] = logical
        step.pop("dio_channel", None)
        self._notify_row()

    @Slot(int)
    def setIoType(self, kind):
        step = self._selected()
        if not step or step.get("type") not in ("OUT", "IN"): return
        logical = self._channel(); kind = max(0, min(2, int(kind)))
        step["out_type" if step.get("type") == "OUT" else "in_type"] = kind
        self.setChannel(logical)

    @Slot(bool)
    def setOn(self, enabled):
        if self._selected(): self._selected()["on"] = enabled; self._notify_row()

    @Slot(float)
    def setSeconds(self, seconds):
        if self._selected(): self._selected()["time"] = max(0.0, float(seconds)); self._notify_row()

    @Slot(int)
    def setTargetIndex(self, index):
        if self._selected(): self._selected()["target_idx"] = max(0, int(index)); self._notify_row()

    @Slot(int)
    def setTargetSequenceIndex(self, index):
        keys = [k for k in self._keys() if k != self.current_sequence]
        if self._selected() and 0 <= index < len(keys):
            self._selected()["target_seq"] = keys[index]; self._notify_row()

    @Slot(int)
    def setPointIndex(self, index):
        keys = self._point_keys()
        if self._selected() and 0 <= index < len(keys): self._selected()["point_name"] = keys[index]; self._notify_row()
    @Slot(int, bool)
    def setAxisActive(self, index, enabled):
        step = self._selected(); axes = list(step.get("active_axes", [True] * 8)) if step else []
        while len(axes) < 8: axes.append(True)
        if 0 <= index < 8: axes[index] = bool(enabled); step["active_axes"] = axes; self._notify_row()
    @Slot(int, result=bool)
    def axisActive(self, index):
        axes = list(self._selected().get("active_axes", [True] * 8)); return bool(axes[index]) if 0 <= index < len(axes) else True
    @Slot(bool)
    def setWaitCompletion(self, value): self._selected()["wait_completion"] = bool(value); self._notify_row()
    @Slot(bool)
    def setPackBase(self, value):
        if value: self._selected()["pack_base"] = True
        else: self._selected().pop("pack_base", None)
        self._notify_row()
    @Slot(bool)
    def setDelayEnabled(self, value): self._selected()["delay_enable"] = bool(value); self._notify_row()
    @Slot(float)
    def setDelaySeconds(self, value): self._selected()["delay_time"] = max(0.0, float(value)); self._notify_row()
    @Slot(bool)
    def setTimeoutEnabled(self, value): self._selected()["timeout_enabled"] = bool(value); self._notify_row()
    @Slot(float)
    def setTimeoutSeconds(self, value): self._selected()["timeout"] = max(0.0, float(value)); self._notify_row()
    @Slot(int)
    def setTimeoutAction(self, index): self._selected()["timeout_action"] = ("continue", "ask", "alarm_go")[max(0, min(2, index))]; self._notify_row()
    @Slot(bool)
    def setParallel(self, value): self._selected()["parallel"] = bool(value); self._notify_row()
    @Slot(bool)
    def setConditional(self, value): self._selected()["condition"] = bool(value); self._notify_row()
    @Slot(int)
    def setCondType(self, index): self._selected()["cond_type"] = ("INPUT", "VALVE", "BIT", "MODE", "STATE", "DTCMP")[max(0, min(5, index))]; self._notify_row()
    @Slot(int)
    def setCondValue(self, value): self._selected()["cond_value"] = int(value); self._notify_row()
    @Slot(bool)
    def setCondOn(self, value): self._selected()["cond_on"] = bool(value); self._notify_row()
    @Slot(int)
    def setCmpAddress(self, value): self._selected()["cmp_dt_addr"] = max(60000, min(60099, int(value))); self._notify_row()
    @Slot(int)
    def setCmpOp(self, value): self._selected()["cmp_op"] = max(0, min(5, int(value))); self._notify_row()
    @Slot(int)
    def setCmpConst(self, value): self._selected()["cmp_const"] = max(-32768, min(32767, int(value))); self._notify_row()
    @Slot(int)
    def setDatAddress(self, value): self._selected()["dat_dt_addr"] = max(60000, min(60099, int(value))); self._notify_row()
    @Slot(int)
    def setDatOp(self, value): self._selected()["dat_op"] = max(0, min(2, int(value))); self._notify_row()
    @Slot(int)
    def setDatConst(self, value): self._selected()["dat_const"] = max(-32768, min(32767, int(value))); self._notify_row()

    @Slot()
    def save(self): self.acceptRequested.emit()

    @Slot()
    def cancel(self): self.rejectRequested.emit()


class SequenceEditorQmlDialog(QQuickWidget):
    """Full-screen QML editor hosted as a child scene, without a modal event loop."""

    def __init__(self, sequence_data=None, position_points=None, timer_library=None,
                 plc_client=None, mode_data=None, parent=None):
        host = parent.window() if parent is not None else None
        super().__init__(host)
        self._finished_callback = None
        self.timer_library = timer_library if timer_library is not None else {}
        self.points_library = copy.deepcopy(position_points or {})
        if isinstance(sequence_data, dict): self.sequences = copy.deepcopy(sequence_data)
        elif isinstance(sequence_data, list): self.sequences = {"Main": copy.deepcopy(sequence_data)}
        else: self.sequences = {"Main": []}
        self.sequences.setdefault("Main", [])
        normalize_all_sequences(self.sequences, self.timer_library)

        self.model = StepListModel(self)
        self.backend = SequenceEditorBackend(self.sequences, self.timer_library,
                                             self.points_library, self.model, self)
        self.backend.acceptRequested.connect(lambda: self._finish(True))
        self.backend.rejectRequested.connect(lambda: self._finish(False))
        self.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self.setClearColor(QColor("#0F161E"))
        self.setAttribute(Qt.WA_AlwaysStackOnTop, True)
        self.rootContext().setContextProperty("stepModel", self.model)
        self.rootContext().setContextProperty("seqEditor", self.backend)
        self.setSource(QUrl.fromLocalFile(_QML_PATH))
        self.hide()

    @property
    def view(self):
        """Compatibility alias used by smoke checks."""
        return self

    def open(self, callback=None):
        self._finished_callback = callback
        if self.parentWidget() is not None:
            self.resize(self.parentWidget().size())
        self.show()
        self.raise_()
        self.setFocus(Qt.OtherFocusReason)

    def _finish(self, accepted):
        callback, self._finished_callback = self._finished_callback, None
        self.hide()
        if callback is not None:
            callback(bool(accepted), self)
        self.deleteLater()

    def get_sequence_data(self): return self.sequences
    def get_position_points(self): return self.points_library
