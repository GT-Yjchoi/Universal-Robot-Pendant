"""
타이머 라이브러리 페이지 QML(GPU) — PageTimer drop-in.
6열 카드 GPU 스크롤. active 깜빡임/큐잉·_sync_steps_time(PLC patch)·
reorder 로직은 PageTimer 와 동일. 다이얼로그 재사용.
"""
import os
import time

from PySide6.QtCore import (Qt, QObject, Signal, Slot, Property, QUrl, QTimer,
                            QAbstractListModel, QModelIndex, QByteArray)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget
from PySide6.QtQuickWidgets import QQuickWidget

_QML_PATH = os.path.join(os.path.dirname(__file__), "PageTimer.qml")
_R_NAME = Qt.UserRole + 1
_R_SEC = Qt.UserRole + 2


class TimerModel(QAbstractListModel):
    def __init__(self, lib, parent=None):
        super().__init__(parent)
        self._lib = lib
        self._names = []

    def rowCount(self, p=QModelIndex()):
        return len(self._names)

    def roleNames(self):
        return {_R_NAME: QByteArray(b"tname"), _R_SEC: QByteArray(b"tsec")}

    def data(self, ix, role):
        i = ix.row()
        if not (0 <= i < len(self._names)):
            return None
        nm = self._names[i]
        if role == _R_NAME:
            return nm
        if role == _R_SEC:
            return f"{float(self._lib.get(nm, 0)):.1f} SEC"
        return None

    def rebuild(self):
        self.beginResetModel()
        self._names = list(self._lib.keys())
        self.endResetModel()

    def update_one(self, name):
        if name in self._names:
            r = self._names.index(name)
            self.dataChanged.emit(self.index(r, 0), self.index(r, 0),
                                  [_R_NAME, _R_SEC])


class TimerBackend(QObject):
    changed = Signal()        # active/blink 변경 → QML 하이라이트 갱신

    def __init__(self, page):
        super().__init__(page)
        self._p = page

    def _active(self):
        return self._p._active_timer_name or ""

    def _blink(self):
        return self._p._blink_state

    activeName = Property(str, _active, notify=changed)
    blinkOn = Property(bool, _blink, notify=changed)

    @Slot(str)
    def editTimer(self, name):
        self._p._on_card_clicked(name)

    @Slot()
    def reorder(self):
        self._p._on_reorder_clicked()


class PageTimerQml(QWidget):
    sig_timer_changed = Signal()

    def __init__(self, sequence_data=None, timer_library=None, plc_client=None,
                 local_runtime=None):
        super().__init__()
        self.plc_client = plc_client
        self.local_runtime = local_runtime
        self.sequence_data = sequence_data if sequence_data is not None else {}
        self.timer_library = timer_library if timer_library is not None else {}

        # active 하이라이트 상태 (PageTimer 와 동일 필드)
        self._active_timer_name = None
        self._blink_state = False
        self._highlight_min_sec = 0.5
        self._active_min_end = 0.0
        self._active_queue = []
        self._pending_monitor = None

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._on_blink)
        self._pending_clear = QTimer(self)
        self._pending_clear.setSingleShot(True)
        self._pending_clear.timeout.connect(self._on_hold_expired)

        self._model = TimerModel(self.timer_library, self)
        self._be = TimerBackend(self)

        self._view = QQuickWidget(self)
        self._view.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self._view.setClearColor(QColor("#16202B"))
        ctx = self._view.rootContext()
        ctx.setContextProperty("timerModel", self._model)
        ctx.setContextProperty("timerBackend", self._be)
        self._view.setSource(QUrl.fromLocalFile(_QML_PATH))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)

        if self.plc_client:
            self.plc_client.sig_monitor_data.connect(self._on_monitor_data)
        if self.local_runtime:
            self.local_runtime.sig_monitor_data.connect(self._on_monitor_data)
        QTimer.singleShot(0, self.refresh_grid)

    # ---- 호환 ----
    def refresh_grid(self):
        self._model.rebuild()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.refresh_grid)
        if self._pending_monitor is not None:
            data, self._pending_monitor = self._pending_monitor, None
            QTimer.singleShot(0, lambda d=data: self._on_monitor_data(d))

    # ---- 편집 (PageTimer._on_card_clicked) ----
    def _on_card_clicked(self, name):
        time_sec = self.timer_library.get(name, 0.0)
        def finished(accepted, value):
            if not accepted: return
            new_sec = round(float(value), 2)
            old_sec = self.timer_library.get(name, time_sec)
            self.timer_library[name] = new_sec
            self._model.update_one(name)
            self._sync_steps_time(name, new_sec)
            print(f"[Timer Library] Updated '{name}': {new_sec} sec")
            try:
                from utils.op_history import record as op_record
                op_record("TIMER", f"타이머 '{name}' {old_sec:.2f}s → {new_sec:.2f}s")
            except Exception:
                pass
        self.window().qml_overlay.request_number(
            f"타이머: {name}", time_sec, decimal=True, minimum=0, maximum=99999,
            callback=finished,
        )

    # ---- Update pendant-owned recipe references only ----
    def _sync_steps_time(self, timer_name, new_sec):
        patch_count = 0
        for steps in self.sequence_data.values():
            if not isinstance(steps, list):
                continue
            for step in steps:
                if step.get("type") == "COMMENT":
                    continue
                if step.get("type") == "TMR" and step.get("timer_ref") == timer_name:
                    step["time"] = new_sec
                    patch_count += 1
                elif step.get("type") == "OUT" and step.get("delay_timer_ref") == timer_name:
                    step["delay_time"] = new_sec
                    patch_count += 1
        if patch_count:
            print(f"[Timer Library] Synced {patch_count} pendant step(s) referencing '{timer_name}'")
        self.sig_timer_changed.emit()

    def _on_reorder_clicked(self):
        if not self.timer_library:
            return
        def finished(accepted, new_order):
            if not accepted: return
            reordered = {n: self.timer_library[n] for n in new_order if n in self.timer_library}
            self.timer_library.clear(); self.timer_library.update(reordered)
            self.refresh_grid(); self.sig_timer_changed.emit()
        self.window().qml_overlay.request_reorder(
            "타이머 순서 변경", list(self.timer_library.keys()), callback=finished,
        )

    # ---- 실시간 active (PageTimer 와 동일 로직) ----
    def _on_monitor_data(self, data):
        if not isinstance(data, dict):
            return
        if not self.isVisible():
            self._pending_monitor = dict(data)
            if self._blink_timer.isActive():
                self._blink_timer.stop()
            return
        op_status = data.get('op_status', 0)
        current_slot = data.get('sub_seq_idx', 0)
        current_step = data.get('current_step', 0)
        if op_status in (1, 2):
            if data.get("pendant_sequence"):
                active = self._find_active_timer(data.get("local_sequence", "Main"), current_step)
            else:
                active = self._find_active_timer(current_slot, current_step)
        else:
            active = None
        self._handle_active_change(active)

    def _handle_active_change(self, active):
        now = time.monotonic()
        holding = now < self._active_min_end
        if active == self._active_timer_name:
            return
        if holding:
            if active is None:
                return
            if not self._active_queue or self._active_queue[-1] != active:
                self._active_queue.append(active)
            return
        self._show_active(active)

    def _show_active(self, active):
        self._pending_clear.stop()
        self._active_timer_name = active
        if active is not None:
            self._active_min_end = time.monotonic() + self._highlight_min_sec
            self._blink_state = True
            self._blink_timer.start()
            self._pending_clear.start(int(self._highlight_min_sec * 1000))
        else:
            self._active_min_end = 0.0
            self._blink_timer.stop()
            self._blink_state = False
        self._be.changed.emit()

    def _on_hold_expired(self):
        if self._active_queue:
            self._show_active(self._active_queue.pop(0))
        else:
            self._show_active(None)

    def _find_active_timer(self, current_slot, step_idx):
        if isinstance(current_slot, str):
            seq_name = current_slot
        elif current_slot == 0:
            seq_name = "Main"
        elif current_slot == 39:
            seq_name = "Monitor"
        else:
            reserved = {"Main", "Monitor"}
            subs = sorted([k for k in self.sequence_data.keys()
                           if k not in reserved])
            idx = current_slot - 1
            if idx < 0 or idx >= len(subs):
                return None
            seq_name = subs[idx]
        steps = self.sequence_data.get(seq_name, [])
        n = 0
        for step in steps:
            if step.get("type") == "COMMENT":
                continue
            if n == step_idx:
                if step.get("type") == "TMR":
                    return step.get("timer_ref")
                return None
            n += 1
        return None

    def _on_blink(self):
        self._blink_state = not self._blink_state
        self._be.changed.emit()
