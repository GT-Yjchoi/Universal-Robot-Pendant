"""
자동운전 페이지 QML(GPU) — PageAuto drop-in.
UI/스크롤만 QML. 로직(속도·운전모드·확인창·monitor)은 PageAuto 와 동일.
확인 오버레이는 기존 Python AutoConfirmOverlay 재사용 (동작 보존).
"""
import os

from PySide6.QtCore import (Qt, QObject, Signal, Slot, Property, QUrl, QTimer)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget
from PySide6.QtQuickWidgets import QQuickWidget

from ui.pages.page_manual_qml import AxisModel, IoModel, IoBackend
from ui.pages.page_auto import AutoConfirmOverlay   # 확인창 로직 재사용

try:
    from utils.languages import LanguageManager
except ImportError:
    LanguageManager = None
try:
    from utils.io_manager import IOManager
except ImportError:
    IOManager = None

_QML_PATH = os.path.join(os.path.dirname(__file__), "PageAuto.qml")

_GRAY = {"bg": "#3E4A59", "fg": "#95A5A6", "bd": "#2C3E50"}


def _spd_color(level):
    return "#E74C3C" if level <= 3 else "#F1C40F" if level <= 6 else "#2ECC71"


class AutoBackend(QObject):
    changed = Signal()

    def __init__(self, page):
        super().__init__(page)
        self._p = page

    # ---- properties ----
    def _speed(self):
        return self._p.speed_level

    def _speed_color(self):
        return _spd_color(self._p.speed_level)

    def _btn_states(self):
        m = self._p.current_mode
        lm = LanguageManager.instance() if LanguageManager else None
        t_auto = lm.get_text("btn_auto_run") if lm else "AUTO RUN"
        t_chk = lm.get_text("btn_check_run") if lm else "CHECK RUN"
        t_stop = lm.get_text("btn_stop") if lm else "STOP"
        auto = ({"bg": "#2ECC71", "fg": "white", "bd": "#27AE60"} if m == 1 else _GRAY)
        chk = ({"bg": "#F1C40F", "fg": "black", "bd": "#D4AC0D"} if m == 2 else _GRAY)
        stop = ({"bg": "#E74C3C", "fg": "white", "bd": "#C0392B"} if m in (1, 2) else _GRAY)
        return [dict(auto, text=t_auto), dict(chk, text=t_chk), dict(stop, text=t_stop)]

    def _sub_visible(self):
        return self._p.current_mode == 2

    def _sub_states(self):
        crs = self._p._check_run_state
        start = ({"bg": "#27AE60", "fg": "white"} if crs == 1
                 else {"bg": "#34495E", "fg": "#BBBBBB"})
        pause = ({"bg": "#E67E22", "fg": "white"} if crs == 0
                 else {"bg": "#34495E", "fg": "#BBBBBB"})
        return [start, pause]

    def _info_title(self):
        lm = LanguageManager.instance() if LanguageManager else None
        return lm.get_text("info_title") if lm else "생산 정보"

    def _info_rows(self):
        lm = LanguageManager.instance() if LanguageManager else None

        def nm(k, fb):
            if not lm:
                return fb
            t = lm.get_text(k)
            return fb if (t == k or t == "") else t
        stack, pack, reserve = self._p._info
        return [
            {"name": "스택수량", "val": f"{stack} 회"},
            {"name": "포장수량", "val": f"{pack} 회"},
            {"name": "예약수량", "val": f"{reserve} 회"},
        ]

    def _home_text(self):
        return "원점복귀완료" if self._p._home_done else "원점복귀"

    def _home_done_v(self):
        return self._p._home_done

    def _home_blocked(self):
        # 자동운전/확인운전 중에는 원점복귀 차단(자동·확인 버튼과 동일 가드)
        return self._p.current_mode in (1, 2)

    speedLevel = Property(int, _speed, notify=changed)
    speedColor = Property(str, _speed_color, notify=changed)
    btnStates = Property(list, _btn_states, notify=changed)
    subVisible = Property(bool, _sub_visible, notify=changed)
    subStates = Property(list, _sub_states, notify=changed)
    infoTitle = Property(str, _info_title, notify=changed)
    infoRows = Property(list, _info_rows, notify=changed)
    homeText = Property(str, _home_text, notify=changed)
    homeDone = Property(bool, _home_done_v, notify=changed)
    homeBlocked = Property(bool, _home_blocked, notify=changed)

    # ---- slots ----
    @Slot(int)
    def changeSpeed(self, delta):
        self._p._change_speed(delta)

    @Slot(int)
    def ctrlClicked(self, idx):
        if idx == 0:
            self._p._on_auto_clicked()
        elif idx == 1:
            self._p._on_check_clicked()
        else:
            self._p._on_stop_clicked()

    @Slot(int)
    def subClicked(self, idx):
        self._p._send_check_state(1 if idx == 0 else 0)

    @Slot()
    def homeClicked(self):
        self._p._on_home_clicked()


class PageAutoQml(QWidget):
    sig_speed_changed = Signal(int)

    def __init__(self, plc_client=None, speed_state=None, local_runtime=None):
        super().__init__()
        self.plc_client = plc_client
        self.local_runtime = local_runtime
        self.current_mode = 0
        self._prev_op_status = 0
        self._check_run_state = 0
        self._info = (0, 0, 0.0)
        self._home_done = False        # DT165==1 이면 True (원점복귀완료 표시)
        self.speed_state = speed_state if speed_state is not None else {"speed_level": 10}
        self.speed_level = int(self.speed_state.get("speed_level", 10))

        self._axis = AxisModel(self)
        self._io_in = IoModel([f"X{v:02X}" for v in range(0x00, 0x20)], self)
        self._io_out = IoModel([f"Y{v:02X}" for v in range(0x00, 0x20)], self)
        self._io_be = IoBackend(self)
        self._be = AutoBackend(self)

        self._apply_io_names()

        self._view = QQuickWidget(self)
        self._view.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self._view.setClearColor(QColor("#16202B"))
        ctx = self._view.rootContext()
        ctx.setContextProperty("axisModel", self._axis)
        ctx.setContextProperty("ioInModel", self._io_in)
        ctx.setContextProperty("ioOutModel", self._io_out)
        ctx.setContextProperty("ioBackend", self._io_be)
        ctx.setContextProperty("autoBackend", self._be)
        self._view.setSource(QUrl.fromLocalFile(_QML_PATH))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)

        # 원점복귀 상태(DT165)는 모니터 범위(DT100~163) 밖이라 별도 폴링.
        # 안전 핵심 모니터 파이프라인(MONITOR_COUNT/파서)은 건드리지 않음.
        self._home_timer = QTimer(self)
        self._home_timer.setInterval(500)
        self._home_timer.timeout.connect(self._poll_home_status)

        if self.plc_client:
            self.plc_client.sig_monitor_data.connect(self._on_monitor_data)
            self.plc_client.sig_connected.connect(self._refresh_axis_visibility)
        if self.local_runtime:
            self.local_runtime.sig_monitor_data.connect(self._on_monitor_data)
        if IOManager:
            IOManager.instance().sig_names_changed.connect(self._apply_io_names)
        if LanguageManager:
            LanguageManager.instance().sig_lang_changed.connect(self.update_language)

    def _apply_io_names(self):
        if not IOManager:
            return
        mgr = IOManager.instance()
        for i in range(32):
            self._io_in.set_label(i, mgr.get_input_name(i))
            self._io_out.set_label(i, mgr.get_output_name(i))

    # ---- 로직 (PageAuto 와 동일) ----
    def _change_speed(self, delta):
        new_val = max(1, min(10, self.speed_level + delta))
        if new_val == self.speed_level:
            return
        old_val = self.speed_level
        self.speed_level = new_val
        self.speed_state["speed_level"] = new_val
        self._be.changed.emit()
        if self.plc_client:
            self.plc_client.send_speed_override(self.speed_level)
        self.sig_speed_changed.emit(self.speed_level)
        try:
            from utils.op_history import record as op_record
            op_record("SPEED", f"전체속도 {old_val} → {new_val}")
        except Exception:
            pass

    def refresh_speed_from_state(self):
        new_val = max(1, min(10, int(self.speed_state.get("speed_level", 10))))
        self.speed_level = new_val
        self.speed_state["speed_level"] = new_val
        self._be.changed.emit()
        if self.plc_client:
            self.plc_client.send_speed_override(self.speed_level)

    def _send_mode(self, mode):
        if self.local_runtime:
            self.local_runtime.start_mode(mode)
            return
        if self.plc_client:
            self.plc_client.send_control_command(mode)

    def _on_stop_clicked(self):
        self._send_mode(0)
        self._send_check_state(0)
        try:
            from utils.op_history import record as op_record
            op_record("RUN", "정지 버튼")
        except Exception:
            pass

    def _send_check_state(self, state):
        if self.local_runtime:
            if state:
                self.local_runtime.resume()
            else:
                self.local_runtime.pause()
            return
        if self.plc_client:
            self.plc_client.send_check_run_command(state)

    def _show_home_required(self):
        AutoConfirmOverlay("원점복귀 필요", "원점복귀를 먼저 완료해주세요.",
                           self.window(), btn_yes="확인", btn_no=None).exec()

    def _can_start_run(self):
        if self.current_mode in (1, 2):
            return False
        if self.local_runtime:
            return self.local_runtime.is_connected
        if not self._home_done:
            self._show_home_required()
            return False
        return True

    def _on_auto_clicked(self):
        if not self._can_start_run():
            return
        if AutoConfirmOverlay("자동 운전", "자동 운전을 시작하시겠습니까?",
                              self.window()).exec():
            self._send_mode(1)
            try:
                from utils.op_history import record as op_record
                op_record("RUN", "자동 운전 시작")
            except Exception:
                pass

    def _on_check_clicked(self):
        if not self._can_start_run():
            return
        if AutoConfirmOverlay("확인 운전", "확인 운전을 시작하시겠습니까?",
                              self.window()).exec():
            self._send_mode(2)
            try:
                from utils.op_history import record as op_record
                op_record("RUN", "확인 운전 시작")
            except Exception:
                pass

    def _on_home_clicked(self):
        # 원점복귀: 확인 후 DT164 에 1 기록(영역 0x09, write_words).
        # 자동운전/확인운전 중에는 차단(자동·확인 버튼과 동일 가드).
        if self.local_runtime:
            return
        if self.current_mode in (1, 2):
            return
        if not self.plc_client or not self.plc_client.is_connected:
            return
        if AutoConfirmOverlay("원점복귀", "원점복귀를 하시겠습니까?",
                              self.window()).exec():
            try:
                self.plc_client.write_words(0x09, 164, [1])
            except Exception as e:
                print(f"[Auto] 원점복귀 명령(DT164) 실패: {e}")
                return
            self._home_done = False        # 진행 시작 — DT165 폴링이 완료 반영
            self._be.changed.emit()
            try:
                from utils.op_history import record as op_record
                op_record("RUN", "원점복귀 명령(DT164=1)")
            except Exception:
                pass

    def _poll_home_status(self):
        # DT165==1 → 원점복귀완료. (모니터 범위 밖이라 별도 read_words 폴링)
        if not self.plc_client or not self.plc_client.is_connected:
            return
        try:
            vals = self.plc_client.read_words(0x09, 165, 1)
        except Exception:
            return
        done = bool(vals and vals[0] == 1)
        if done != self._home_done:
            self._home_done = done
            self._be.changed.emit()

    def _on_monitor_data(self, data):
        mode = data.get('op_status', 0)
        if self._prev_op_status == 2 and mode == 0:
            self._send_check_state(0)
        self._prev_op_status = mode

        if not self.isVisible():
            return
        if 'inputs' in data:
            self._io_in.update_from_words(data['inputs'])
        if 'outputs' in data:
            self._io_out.update_from_words(data['outputs'])
        if 'axis_pos' in data:
            self._axis.set_values(data['axis_pos'])

        self.current_mode = mode
        self._check_run_state = data.get('check_run_status', 0)
        self._info = (data.get('stack_count', data.get('total_count', 0)),
                      data.get('pack_count', 0),
                      data.get('reserve_count', data.get('setting_count', 0)))
        self._be.changed.emit()

    def _refresh_axis_visibility(self):
        if not self.plc_client or not self.plc_client.is_connected:
            return
        try:
            d = self.plc_client.read_words(0x09, self.plc_client.AXIS_PARAM_ADDR, 1)
            if d:
                self._axis.set_visibility(d[0])
        except Exception as e:
            print(f"Axis Config Load Error: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._refresh_axis_visibility)
        QTimer.singleShot(0, self._poll_home_status)
        self._home_timer.start()

    def hideEvent(self, event):
        self._home_timer.stop()
        super().hideEvent(event)

    def update_language(self, lang_code=None):
        self._io_be.refresh_titles()
        self._apply_io_names()
        self._be.changed.emit()
