"""QML-rendered application chrome with narrow Python state bridges."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QVBoxLayout, QWidget


_COMPONENTS = os.path.join(os.path.dirname(__file__), "qml", "components")


class TopBarBackend(QObject):
    changed = Signal()
    jogRequested = Signal()
    alarmRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False
        self._recipe = "No Data"
        self._mode = "모드: 정지"
        self._mode_color = "#95a5a6"
        self._alarm = ""
        self.op_status = 0

    connected = Property(bool, lambda s: s._connected, notify=changed)
    recipeName = Property(str, lambda s: s._recipe, notify=changed)
    modeText = Property(str, lambda s: s._mode, notify=changed)
    modeColor = Property(str, lambda s: s._mode_color, notify=changed)
    alarmText = Property(str, lambda s: s._alarm, notify=changed)

    @Slot()
    def requestJog(self): self.jogRequested.emit()

    @Slot()
    def requestAlarm(self): self.alarmRequested.emit()

    def set_connected(self, connected):
        connected = bool(connected)
        if connected != self._connected:
            self._connected = connected; self.changed.emit()

    def set_recipe(self, recipe):
        recipe = str(recipe)
        if recipe != self._recipe:
            self._recipe = recipe; self.changed.emit()

    def update_monitor(self, data):
        status = int(data.get("op_status", self.op_status))
        alarms = list(data.get("axis_alarms", []))
        if status == 1:
            mode, color = "모드: 자동운전", "#2ecc71"
        elif status == 2:
            mode, color = "모드: 확인운전", "#f1c40f"
        else:
            mode, color = "모드: 정지", "#95a5a6"
        alarm = "[!] 비상정지" if 9 in alarms else (f"[!] 알람 ({len(alarms)}축)" if alarms else "")
        if (status, mode, color, alarm) != (self.op_status, self._mode, self._mode_color, self._alarm):
            self.op_status, self._mode, self._mode_color, self._alarm = status, mode, color, alarm
            self.changed.emit()


class QmlTopBar(QWidget):
    sig_jog_clicked = Signal()
    sig_alarm_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self._backend = TopBarBackend(self)
        self._backend.jogRequested.connect(self.sig_jog_clicked)
        self._backend.alarmRequested.connect(self.sig_alarm_clicked)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self._view = QQuickWidget(self)
        self._view.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self._view.rootContext().setContextProperty("topBackend", self._backend)
        self._view.setSource(QUrl.fromLocalFile(os.path.join(_COMPONENTS, "TopBarHost.qml")))
        layout.addWidget(self._view)

    @property
    def op_status(self): return self._backend.op_status

    def set_comm_status(self, connected): self._backend.set_connected(connected)
    def set_mold_data(self, name): self._backend.set_recipe(name)
    def _on_monitor_data(self, data): self._backend.update_monitor(data)


class NavBackend(QObject):
    changed = Signal()
    selected = Signal(str, int)

    def __init__(self, keys, labels, parent=None):
        super().__init__(parent)
        self._keys = list(keys)
        self._labels = list(labels)
        self._current = 0

    labels = Property(list, lambda s: s._labels, notify=changed)
    currentIndex = Property(int, lambda s: s._current, notify=changed)

    @Slot(int)
    def choose(self, index):
        if 0 <= index < len(self._keys): self.selected.emit(self._keys[index], index)

    def set_current(self, index):
        if index != self._current:
            self._current = index; self.changed.emit()

    def set_labels(self, labels):
        labels = list(labels)
        if labels != self._labels:
            self._labels = labels; self.changed.emit()


class QmlBottomBar(QWidget):
    sig_selected = Signal(str, int)

    def __init__(self, keys, labels, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self._backend = NavBackend(keys, labels, self)
        self._backend.selected.connect(self.sig_selected)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self._view = QQuickWidget(self)
        self._view.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self._view.rootContext().setContextProperty("navBackend", self._backend)
        self._view.setSource(QUrl.fromLocalFile(os.path.join(_COMPONENTS, "BottomNavHost.qml")))
        layout.addWidget(self._view)

    def set_current(self, index): self._backend.set_current(index)
    def set_labels(self, labels): self._backend.set_labels(labels)
