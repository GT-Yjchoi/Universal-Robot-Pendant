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
from PySide6.QtWidgets import QDialog, QVBoxLayout

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
        channel = int(step.get("dio_channel", step.get("port", 0)))
        state = "ON" if step.get("on", True) else "OFF"
        return f"{name}  ·  {kind}{channel} {state}"
    if kind == "TMR":
        return f"{name}  ·  {float(step.get('time', 0)):.3f}s"
    if kind == "JMP":
        return f"{name}  ·  → {int(step.get('target_idx', 0)) + 1}"
    if kind == "CALL":
        return f"{name}  ·  {step.get('target_seq', '')}"
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

    def __init__(self, sequences, timer_library, model, parent=None):
        super().__init__(parent)
        self.sequences = sequences
        self.timer_library = timer_library
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
        return max(0, min(7, int(step.get("dio_channel", step.get("port", 0))))) if step else 0
    def _on(self): return bool(self._selected().get("on", True))
    def _seconds(self): return float(self._selected().get("time", 1.0)) if self._selected() else 1.0
    def _target_index(self): return int(self._selected().get("target_idx", 0)) if self._selected() else 0
    def _target_sequence(self): return str(self._selected().get("target_seq", ""))
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
    selectedOn = Property(bool, _on, notify=selectionChanged)
    selectedSeconds = Property(float, _seconds, notify=selectionChanged)
    selectedTargetIndex = Property(int, _target_index, notify=selectionChanged)
    selectedTargetSequence = Property(str, _target_sequence, notify=selectionChanged)
    stepTargets = Property(list, _step_targets, notify=changed)
    targetSequenceKeys = Property(list, lambda self: [k for k in self._keys() if k != self.current_sequence], notify=changed)
    targetSequenceIndex = Property(int, _target_seq_index, notify=selectionChanged)

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
            data.update({"dio_channel": 0, "port": 0, "on": True})
        elif kind == "TMR": data["time"] = 1.0
        elif kind == "JMP": data.update({"target_idx": 0, "condition": False})
        elif kind == "CALL": data["target_seq"] = ""
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
        step["dio_channel"] = max(0, min(7, int(channel)))
        step["port"] = step["dio_channel"]
        self._notify_row()

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

    @Slot()
    def save(self): self.acceptRequested.emit()

    @Slot()
    def cancel(self): self.rejectRequested.emit()


class SequenceEditorQmlDialog(QDialog):
    def __init__(self, sequence_data=None, position_points=None, timer_library=None,
                 plc_client=None, mode_data=None, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setWindowState(Qt.WindowFullScreen)
        self.timer_library = timer_library if timer_library is not None else {}
        self.points_library = copy.deepcopy(position_points or {})
        if isinstance(sequence_data, dict): self.sequences = copy.deepcopy(sequence_data)
        elif isinstance(sequence_data, list): self.sequences = {"Main": copy.deepcopy(sequence_data)}
        else: self.sequences = {"Main": []}
        self.sequences.setdefault("Main", [])
        normalize_all_sequences(self.sequences, self.timer_library)

        self.model = StepListModel(self)
        self.backend = SequenceEditorBackend(self.sequences, self.timer_library, self.model, self)
        self.backend.acceptRequested.connect(self.accept)
        self.backend.rejectRequested.connect(self.reject)
        self.view = QQuickWidget(self)
        self.view.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self.view.setClearColor(QColor("#0F161E"))
        self.view.rootContext().setContextProperty("stepModel", self.model)
        self.view.rootContext().setContextProperty("seqEditor", self.backend)
        self.view.setSource(QUrl.fromLocalFile(_QML_PATH))
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.addWidget(self.view)

    def get_sequence_data(self): return self.sequences
    def get_position_points(self): return self.points_library
