"""QML packing page. Python owns data/PLC; Qt Quick owns every visual element."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, QUrl
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QVBoxLayout, QWidget


_QML_PATH = os.path.join(os.path.dirname(__file__), "PagePacking.qml")


class PackingBackend(QObject):
    changed = Signal()
    animationChanged = Signal()
    configChanged = Signal()

    STACK_ORDERS = (
        ("x", "y", "z"), ("x", "z", "y"), ("y", "x", "z"),
        ("y", "z", "x"), ("z", "x", "y"), ("z", "y", "x"),
    )

    def __init__(self, owner):
        super().__init__(owner)
        self._owner = owner
        self._current = [1, 1, 1]
        self._anim = [0, 0, 0]
        self._sim_state = 1
        self._playing = True

    def _cfg(self):
        return self._owner.packing_config

    def _axis_rows(self):
        cfg = self._cfg()
        colors = ("#00E5FF", "#FFD280", "#64FFDA")
        rows = []
        for index, axis in enumerate(("x", "y", "z")):
            rows.append({
                "axis": axis.upper(), "key": axis, "color": colors[index],
                "current": self._current[index],
                "count": max(1, int(cfg.get(f"{axis}_count", (5, 4, 3)[index]))),
                "pitch": float(cfg.get(f"{axis}_pitch", 10.0)),
                "direction": 1 if int(cfg.get(f"{axis}_dir", 1 if index < 2 else -1)) > 0 else -1,
            })
        return rows

    axes = Property(list, _axis_rows, notify=changed)
    enabled = Property(bool, lambda s: bool(s._cfg().get("enabled", False)), notify=changed)
    playing = Property(bool, lambda s: s._playing, notify=animationChanged)
    simState = Property(int, lambda s: s._sim_state, notify=animationChanged)
    anim = Property(list, lambda s: list(s._anim), notify=animationChanged)
    orderIndex = Property(int, lambda s: int(s._cfg().get("stack_order", 0)) % 6, notify=changed)
    orderText = Property(
        str,
        lambda s: "→".join(a.upper() for a in s.STACK_ORDERS[s.orderIndex]),
        notify=changed,
    )

    def _base_text(self):
        names, seen = [], set()
        sequences = self._owner.sequence_data
        if isinstance(sequences, list):
            sequences = {"Main": sequences}
        for steps in sequences.values() if isinstance(sequences, dict) else ():
            for step in steps if isinstance(steps, list) else ():
                name = step.get("point_name") if isinstance(step, dict) and step.get("type") == "POS" and step.get("pack_base") else None
                if name and name not in seen:
                    seen.add(name); names.append(name)
        return "베이스: " + ", ".join(names) if names else "⚠ POS 스텝에서 '파렛타이징 베이스'를 지정하세요"

    baseText = Property(str, _base_text, notify=changed)

    def refresh(self):
        self.changed.emit()
        self.animationChanged.emit()

    def _commit(self):
        self.changed.emit()
        self.configChanged.emit()
        self._owner.sig_packing_changed.emit()
        self.resetSimulation()

    @Slot(bool)
    def setEnabled(self, value):
        if bool(self._cfg().get("enabled", False)) == bool(value):
            return
        self._cfg()["enabled"] = bool(value)
        self._commit()

    @Slot()
    def cycleOrder(self):
        self._cfg()["stack_order"] = (self.orderIndex + 1) % 6
        self._commit()

    @Slot(str, str, float)
    def setAxisValue(self, axis, field, value):
        axis = axis.lower()
        if axis not in ("x", "y", "z") or field not in ("count", "pitch"):
            return
        clean = max(1, int(value)) if field == "count" else max(0.0, round(float(value), 2))
        key = f"{axis}_{field}"
        if self._cfg().get(key) == clean:
            return
        self._cfg()[key] = clean
        self._commit()

    @Slot(str)
    def toggleDirection(self, axis):
        axis = axis.lower()
        if axis not in ("x", "y", "z"):
            return
        key = f"{axis}_dir"
        self._cfg()[key] = -1 if int(self._cfg().get(key, 1)) > 0 else 1
        self._commit()

    @Slot(str, int)
    def setCurrentIndex(self, axis, one_based):
        axis = axis.lower()
        if axis not in ("x", "y", "z"):
            return
        count = int(self._cfg().get(f"{axis}_count", 1))
        value = max(1, min(count, int(one_based)))
        plc = self._owner.plc_client
        if plc and plc.is_connected:
            plc.submit(plc.write_pack_idx, axis, value - 1)

    @Slot()
    def toggleSimulation(self):
        self._playing = not self._playing
        if self._playing:
            if self._sim_state == 2:
                self._anim = [0, 0, 0]
            self._sim_state = 1
            self._owner._sim_timer.start()
        else:
            self._owner._sim_timer.stop()
        self.animationChanged.emit()

    @Slot()
    def resetSimulation(self):
        self._anim = [0, 0, 0]
        self._sim_state = 1
        self._playing = True
        if self._owner.isVisible():
            self._owner._sim_timer.start()
        self.animationChanged.emit()

    def advance(self):
        rows = self._axis_rows()
        counts = {row["key"]: row["count"] for row in rows}
        values = dict(zip(("x", "y", "z"), self._anim))
        order = self.STACK_ORDERS[self.orderIndex]
        finished = False
        for index, axis in enumerate(order):
            values[axis] += 1
            if values[axis] >= counts[axis]:
                if index == 2:
                    finished = True
                    break
                values[axis] = 0
            else:
                break
        self._anim = [values["x"], values["y"], values["z"]]
        if finished:
            last = order[-1]
            self._anim[("x", "y", "z").index(last)] = counts[last]
            self._playing = False
            self._sim_state = 2
            self._owner._sim_timer.stop()
        self.animationChanged.emit()

    def update_monitor(self, data):
        values = list(data.get("pack_idx", (0, 0, 0)))[:3]
        current = [int(v) + 1 for v in values]
        if current != self._current:
            self._current = current
            self.changed.emit()


class PagePackingQml(QWidget):
    sig_packing_changed = Signal()

    def __init__(self, position_points=None, sequence_data=None, plc_client=None, packing_config=None):
        super().__init__()
        self.position_points = position_points if position_points is not None else {}
        self.sequence_data = sequence_data if sequence_data is not None else {}
        self.plc_client = plc_client
        self._pending_monitor = None
        self.packing_config = packing_config if packing_config is not None else {}
        self._apply_defaults()
        self._backend = PackingBackend(self)
        self._sim_timer = QTimer(self)
        self._sim_timer.setInterval(500)
        self._sim_timer.timeout.connect(self._backend.advance)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._view = QQuickWidget(self)
        self._view.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self._view.rootContext().setContextProperty("packingBackend", self._backend)
        self._view.setSource(QUrl.fromLocalFile(_QML_PATH))
        layout.addWidget(self._view)
        if plc_client:
            plc_client.sig_monitor_data.connect(self._on_monitor_data)

    def _on_monitor_data(self, data):
        if not self.isVisible():
            self._pending_monitor = dict(data)
            return
        self._backend.update_monitor(data)

    def _apply_defaults(self):
        defaults = {
            "x_count": 5, "x_pitch": 10.0, "x_dir": 1,
            "y_count": 4, "y_pitch": 10.0, "y_dir": 1,
            "z_count": 3, "z_pitch": 10.0, "z_dir": -1,
            "stack_order": 0, "enabled": False,
        }
        for key, value in defaults.items():
            self.packing_config.setdefault(key, value)

    def get_packing_config(self):
        return dict(self.packing_config)

    def set_pack_enabled(self, enabled):
        self.packing_config["enabled"] = bool(enabled)
        self._backend.refresh()

    def refresh_ui(self):
        self._apply_defaults()
        self._backend.refresh()
        self._backend.resetSimulation()

    def update_language(self, lang_code=None):
        self._backend.refresh()

    def showEvent(self, event):
        self._backend.resetSimulation()
        super().showEvent(event)
        if self._pending_monitor is not None:
            data, self._pending_monitor = self._pending_monitor, None
            self._backend.update_monitor(data)

    def hideEvent(self, event):
        self._sim_timer.stop()
        super().hideEvent(event)
