"""Single QML overlay layer for application-wide non-blocking popups."""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, Property, Signal, Slot
from utils.paths import get_settings_path


class OverlayBackend(QObject):
    numberRequested = Signal(str, float, bool, bool, float, float, bool)
    messageRequested = Signal(str, str, bool)
    confirmRequested = Signal(str, str, str, str)
    reorderRequested = Signal(str, list)
    textRequested = Signal(str, str, bool)
    selectRequested = Signal(str, list, int)
    fineRequested = Signal(str, float, float, float)
    historyRequested = Signal(list, list)
    fineValueUpdated = Signal(float)
    alarmChanged = Signal()
    jogChanged = Signal()

    def __init__(self, owner):
        super().__init__(owner)
        self._owner = owner

    alarmVisible = Property(bool, lambda s: s._owner.has_any_alarm(), notify=alarmChanged)
    alarmTitle = Property(str, lambda s: s._owner._alarm_value("title", ""), notify=alarmChanged)
    alarmMessage = Property(str, lambda s: s._owner._alarm_value("message", ""), notify=alarmChanged)
    alarmColor = Property(str, lambda s: "#f39c12" if s._owner._alarm_value("style", "alarm") == "comm" else "#ff4646", notify=alarmChanged)
    alarmResetVisible = Property(bool, lambda s: bool(s._owner._alarm_value("show_reset", False)), notify=alarmChanged)
    alarmCloseVisible = Property(bool, lambda s: bool(s._owner._alarm_value("show_close", False)), notify=alarmChanged)
    alarmPage = Property(str, lambda s: s._owner._alarm_page(), notify=alarmChanged)
    alarmMultiple = Property(bool, lambda s: len(s._owner._alarm_order) > 1, notify=alarmChanged)
    jogVisible = Property(bool, lambda s: s._owner._jog_visible, notify=jogChanged)
    jogSpeed = Property(int, lambda s: s._owner._jog_speed, notify=jogChanged)
    jogValves = Property(list, lambda s: s._owner._jog_valves, notify=jogChanged)

    @Slot(float)
    def acceptNumber(self, value): self._owner._number_done(True, value)

    @Slot()
    def rejectNumber(self): self._owner._number_done(False, 0.0)

    @Slot()
    def closeMessage(self): self._owner._message_done()

    @Slot(bool)
    def resolveConfirm(self, accepted): self._owner._confirm_done(accepted)

    @Slot(list)
    def acceptReorder(self, values): self._owner._reorder_done(True, values)

    @Slot()
    def rejectReorder(self): self._owner._reorder_done(False, [])

    @Slot(str)
    def acceptText(self, value): self._owner._text_done(True, value)

    @Slot()
    def rejectText(self): self._owner._text_done(False, "")

    @Slot(int, str)
    def acceptSelection(self, index, value): self._owner._select_done(True, index, value)

    @Slot()
    def rejectSelection(self): self._owner._select_done(False, -1, "")

    @Slot(float)
    def adjustFine(self, delta): self._owner._fine_adjust(delta)

    @Slot()
    def closeFine(self): self._owner._fine_done()

    @Slot()
    def closeHistory(self): self._owner._history_done()

    @Slot()
    def previousAlarm(self): self._owner._move_alarm(-1)

    @Slot()
    def nextAlarm(self): self._owner._move_alarm(1)

    @Slot()
    def closeAlarm(self): self._owner._close_current_alarm()

    @Slot()
    def resetPressed(self): self._owner.sig_reset_pressed.emit()

    @Slot()
    def resetReleased(self): self._owner.sig_reset_released.emit()

    @Slot()
    def closeJog(self): self._owner.close_overlay()

    @Slot(str, bool)
    def jogAxis(self, name, active): self._owner._jog_axis(name, active)

    @Slot(int)
    def setJogSpeed(self, speed): self._owner._set_jog_speed(speed)

    @Slot(int, bool)
    def setJogValve(self, index, active): self._owner._set_jog_valve(index, active)


class QmlOverlayLayer(QObject):
    """Non-visual popup/alarm/JOG controller for the single QML scene."""

    def __init__(self, parent):
        super().__init__(parent)
        self._number_callback = None
        self._message_callback = None
        self._confirm_callback = None
        self._reorder_callback = None
        self._text_callback = None
        self._select_callback = None
        self._fine_callback = None
        self._popup_active = False
        self._alarms = {}
        self._alarm_order = []
        self._alarm_index = 0
        self._jog_visible = False
        self._jog_speed = 1
        self._jog_valves = []
        self._plc = getattr(parent, "plc_client", None)
        self._backend = OverlayBackend(self)
        if self._plc is not None:
            self._plc.sig_monitor_data.connect(self._update_jog_monitor)

    @property
    def backend(self):
        return self._backend

    def request_number(self, title, value=0, *, decimal=False, signed=False,
                       minimum=-999999999, maximum=999999999, password=False,
                       callback=None):
        self._number_callback = callback
        self._popup_active = True
        self._backend.numberRequested.emit(
            str(title), float(value), bool(decimal), bool(signed),
            float(minimum), float(maximum), bool(password),
        )

    def show_message(self, title, message, *, error=False, callback=None):
        self._message_callback = callback
        self._popup_active = True
        self._backend.messageRequested.emit(str(title), str(message), bool(error))

    def request_confirm(self, title, message, *, accept_text="확인", reject_text="취소", callback=None):
        self._confirm_callback = callback
        self._popup_active = True
        self._backend.confirmRequested.emit(str(title), str(message), str(accept_text), str(reject_text))

    def request_reorder(self, title, values, *, callback=None):
        self._reorder_callback = callback
        self._popup_active = True
        self._backend.reorderRequested.emit(str(title), list(values))

    def request_text(self, title, value="", *, password=False, callback=None):
        self._text_callback = callback
        self._popup_active = True
        self._backend.textRequested.emit(str(title), str(value), bool(password))

    def request_selection(self, title, values, current=-1, *, callback=None):
        self._select_callback = callback
        self._popup_active = True
        self._backend.selectRequested.emit(str(title), list(values), int(current))

    def request_fine_adjust(self, title, value, minimum, maximum, *, callback=None):
        self._fine_callback = callback
        self._popup_active = True
        self._backend.fineRequested.emit(str(title), float(value), float(minimum), float(maximum))

    def show_history(self):
        from utils.alarm_history import load_history as load_alarm_history
        from utils.op_history import load_history as load_op_history
        alarm_labels = {"AXIS":"축 알람", "ESTOP":"비상정지", "STEP":"스텝 알람",
                        "USER":"사용자 알람", "COMM":"통신 오류"}
        op_labels = {"RUN":"운전", "VALVE":"밸브", "POS":"위치", "SPEED":"속도",
                     "TIMER":"타이머", "MODE":"모드", "RECIPE":"레시피",
                     "PARAM":"파라미터", "ALARM_RESET":"알람리셋", "JOG":"JOG"}
        alarms = []
        for entry in reversed(load_alarm_history()):
            row = dict(entry)
            row["categoryLabel"] = alarm_labels.get(row.get("category", ""), row.get("category", ""))
            row["codeLabel"] = str(row.get("code") or "-")
            alarms.append(row)
        operations = []
        for entry in reversed(load_op_history()):
            row = dict(entry)
            row["categoryLabel"] = op_labels.get(row.get("category", ""), row.get("category", ""))
            operations.append(row)
        self._popup_active = True
        self._backend.historyRequested.emit(alarms, operations)

    def _number_done(self, accepted, value):
        callback, self._number_callback = self._number_callback, None
        self._popup_active = False
        self._sync_visible()
        if callback is not None: callback(bool(accepted), float(value))

    def _message_done(self):
        callback, self._message_callback = self._message_callback, None
        self._popup_active = False
        self._sync_visible()
        if callback is not None: callback()

    def _confirm_done(self, accepted):
        callback, self._confirm_callback = self._confirm_callback, None
        self._popup_active = False
        self._sync_visible()
        if callback is not None: callback(bool(accepted))

    def _reorder_done(self, accepted, values):
        callback, self._reorder_callback = self._reorder_callback, None
        self._popup_active = False; self._sync_visible()
        if callback is not None: callback(bool(accepted), list(values))

    def _text_done(self, accepted, value):
        callback, self._text_callback = self._text_callback, None
        self._popup_active = False; self._sync_visible()
        if callback is not None: callback(bool(accepted), str(value))

    def _select_done(self, accepted, index, value):
        callback, self._select_callback = self._select_callback, None
        self._popup_active = False; self._sync_visible()
        if callback is not None: callback(bool(accepted), int(index), str(value))

    def _fine_adjust(self, delta):
        if self._fine_callback is None: return
        try: value = self._fine_callback(float(delta))
        except Exception as exc:
            print(f"[Fine adjust] {exc}"); return
        if value is not None: self._backend.fineValueUpdated.emit(float(value))

    def _fine_done(self):
        self._fine_callback = None; self._popup_active = False; self._sync_visible()

    def _history_done(self):
        self._popup_active = False
        self._sync_visible()

    def _sync_visible(self):
        # OverlayHost always exists in the single QML scene. Individual QML
        # controls bind to backend state and therefore need no QWidget layer.
        pass

    def _alarm_value(self, key, default=None):
        if not self._alarm_order: return default
        alarm_id = self._alarm_order[min(self._alarm_index, len(self._alarm_order) - 1)]
        return self._alarms.get(alarm_id, {}).get(key, default)

    def _alarm_page(self):
        return f"{self._alarm_index + 1}/{len(self._alarm_order)}" if self._alarm_order else ""

    def add_alarm(self, alarm_id, title, message, style="alarm", show_reset=True, show_close=False):
        if alarm_id not in self._alarms:
            self._alarm_order.append(alarm_id)
            self._alarm_index = len(self._alarm_order) - 1
        self._alarms[alarm_id] = dict(title=title, message=message, style=style,
                                      show_reset=show_reset, show_close=show_close)
        self._backend.alarmChanged.emit(); self._sync_visible()

    def remove_alarm(self, alarm_id):
        if alarm_id in self._alarms:
            del self._alarms[alarm_id]; self._alarm_order.remove(alarm_id)
            self._alarm_index = min(self._alarm_index, max(0, len(self._alarm_order) - 1))
            self._backend.alarmChanged.emit(); self._sync_visible()

    def has_any_alarm(self): return bool(self._alarm_order)

    def show_error(self, axis_list, error_codes=None):
        names = {1:"X축",2:"Y축",3:"Z축",4:"Y2축",5:"Z2축",6:"θ축",7:"R1축",8:"R2축"}
        lines = []
        for axis in [a for a in axis_list if a != 9]:
            code = error_codes[axis-1] if error_codes and len(error_codes) >= axis else 0
            lines.append(f"{names.get(axis, str(axis)+'축')}: E-{code:04X}" if code else names.get(axis, f"{axis}축"))
        if lines: self.add_alarm("axis", "[!] AXIS ALARM [!]", "축 알람 발생\n"+"\n".join(lines))
        else: self.remove_alarm("axis")

    def hide_axis_alarm(self): self.remove_alarm("axis")
    def show_estop(self): self.add_alarm("estop", "[!] E-STOP [!]", "비상정지가 활성화되었습니다.")
    def hide_estop(self): self.remove_alarm("estop")

    def show_user_alarm(self, alarm_no):
        from ui.alarm_catalog import USER_ALARMS
        self.add_alarm("user_alarm", "[!] USER ALARM [!]", f"A-{alarm_no:03d}: {USER_ALARMS.get(alarm_no, f'사용자 알람 #{alarm_no}')}" )
    def hide_user_alarm(self): self.remove_alarm("user_alarm")

    def show_step_alarm(self, alarm_id):
        from ui.alarm_catalog import STEP_ALARM_DESCRIPTIONS
        desc = STEP_ALARM_DESCRIPTIONS.get(alarm_id, f"정의되지 않은 에러 (ID={alarm_id})")
        self.add_alarm("step_alarm", "[!] STEP ALARM [!]", f"E-{alarm_id:02d}: {desc}")
    def hide_step_alarm(self): self.remove_alarm("step_alarm")

    def show_comm_error(self):
        self.add_alarm("comm", "[!] COMM ERROR [!]", "PLC와의 통신이 끊어졌습니다.\n자동으로 재연결을 시도합니다.", "comm", False, True)
    def hide_comm_error(self): self.remove_alarm("comm")

    def _move_alarm(self, delta):
        if self._alarm_order:
            self._alarm_index = max(0, min(len(self._alarm_order)-1, self._alarm_index+delta))
            self._backend.alarmChanged.emit()

    def _close_current_alarm(self):
        if self._alarm_order: self.remove_alarm(self._alarm_order[self._alarm_index])

    def _submit(self, func, *args):
        if self._plc is not None:
            self._plc.submit(func, *args, priority=0)

    def _load_jog_valves(self):
        try:
            with open(get_settings_path(), "r", encoding="utf-8") as stream:
                configs = json.load(stream).get("valve_config", [])
            try:
                from utils.io_manager import IOManager
                point_count = IOManager.instance().point_count(False)
            except Exception:
                point_count = 32
            rows = [c for c in configs
                    if c.get("jog_valve", False)
                    and 0 <= int(c.get("index", -1)) < point_count]
            rows.sort(key=lambda c: c.get("jog_order", 99))
            return [{"name": c.get("name", "밸브"), "index": int(c.get("index", 0)),
                     "mode": c.get("mode", "toggle"), "on": False} for c in rows[:10]]
        except Exception as exc:
            print(f"[JOG] valve config load error: {exc}"); return []

    def show_jog(self):
        self._jog_valves = self._load_jog_valves()
        self._jog_visible = True
        self._backend.jogChanged.emit(); self._sync_visible()
        self._set_jog_speed(self._jog_speed)

    def close_overlay(self):
        if not self._jog_visible: return
        self._jog_visible = False
        # Release every axis command defensively when the panel closes.
        for name in ("X +","X -","Y +","Y -","Z +","Z -","A +","A -"):
            self._jog_axis(name, False)
        self._backend.jogChanged.emit(); self._sync_visible()

    def _jog_axis(self, name, active):
        bits = {"X +":0,"X -":1,"Y +":2,"Y -":3,"Z +":4,"Z -":5,"A +":6,"A -":7}
        bit = bits.get(name)
        if bit is not None and self._plc and self._plc.is_connected:
            self._submit(self._plc.write_axis_jog_bit, bit, bool(active))

    def _set_jog_speed(self, speed):
        speed = max(1, min(5, int(speed)))
        if speed != self._jog_speed:
            self._jog_speed = speed; self._backend.jogChanged.emit()
        if self._plc and self._plc.is_connected:
            self._submit(self._plc.write_words, 0x09, self._plc.ADDR_JOG_SPEED, [speed])

    def _set_jog_valve(self, index, active):
        if not self._plc or not self._plc.is_connected: return
        bit_index = int(index)
        address = self._plc.ADDR_OUTPUT_BASE + bit_index // 16
        self._submit(self._plc.write_bit, 0x09, address, bit_index % 16, bool(active))

    @Slot(dict)
    def _update_jog_monitor(self, data):
        if not self._jog_visible or not self._jog_valves: return
        outputs = list(data.get("outputs", []))
        changed = False
        rows = []
        for row in self._jog_valves:
            item = dict(row); index = item["index"]
            word, bit = divmod(index, 16)
            on = word < len(outputs) and bool(int(outputs[word]) & (1 << bit))
            if item["on"] != on: changed = True
            item["on"] = on; rows.append(item)
        if changed:
            self._jog_valves = rows; self._backend.jogChanged.emit()
    sig_reset_pressed = Signal()
    sig_reset_released = Signal()
