"""
설정 페이지 QML(GPU) — PageSettings drop-in (7탭).

원칙: PLC 기록/저장/로드 로직은 page_settings.py 와 **문자 단위로 동일**.
값의 출처만 QWidget → 백엔드 상태배열(동일 값/타입)로 교체.
  - _build_valve_config / _save_valve_config(_silent) / _load_valve_config
  - _save_params / _load_params (DT 패킹·인덱스·스케일 IDENTICAL)
  - _save_axis_settings / _load_axis_settings
  - _apply_io_names / _load_io_input_names / _sync_valve_names_to_io
  - 알람 CRUD / PLC 연결·상태 / 인터록 / WiFi·Ethernet
WiFi/이더넷 작업은 Python 워커에서 처리하고 모든 시각 팝업은 공통 QML 오버레이를 사용한다.

⚠ valve/param/interlock/dataset 의 실제 동작·모션한계는 실장비에서 전수
재검증 필수 (무PLC 환경에선 UI/스크롤/로직구조까지만 검증 가능).
"""
import json
import os

from PySide6.QtCore import (Qt, QObject, Signal, Slot, Property, QUrl, QTimer,
                            QAbstractListModel, QModelIndex, QByteArray)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget, QApplication
from PySide6.QtQuickWidgets import QQuickWidget

from utils.paths import get_settings_path as _get_settings_path
from utils.json_utils import load_json, save_json
from utils import backlight

# 네트워크 상태 워커는 Python 백엔드에 유지한다. 시각 팝업은 모두 QML이다.
from ui.pages.page_settings import (
    WifiScanWorker, EthernetStatusWorker, WifiStatusWorker, AXIS_NAMES)
try:
    from utils.io_manager import IOManager
except ImportError:
    IOManager = None
try:
    from utils.languages import LanguageManager
except ImportError:
    LanguageManager = None

_QML_PATH = os.path.join(os.path.dirname(__file__), "PageSettings.qml")

_DEF_Y0X = ["형개허가", "형폐허가", "에젝터 허가", "싸이클스타트",
            "컨베어출력1", "컨베어출력2", "예비1", "예비2",
            "예비 Y08", "예비 Y09", "예비 Y0A", "예비 Y0B",
            "예비 Y0C", "예비 Y0D", "예비 Y0E", "예비 Y0F"]
_DEF_Y2X = ["척 1 (Chuck 1)", "척 2 (Chuck 2)", "척 3 (Chuck 3)", "척 4 (Chuck 4)",
            "흡착 1 (Vac 1)", "흡착 2 (Vac 2)", "흡착 3 (Vac 3)", "흡착 4 (Vac 4)",
            "포스쳐 반전", "포스쳐 복귀", "스위블 회전", "스위블 복귀",
            "니퍼 컷팅 1", "니퍼 컷팅 2", "컨베이어 출력", "공급기 출력"]


# ───────────────────────── 모델 ─────────────────────────
class _ListModel(QAbstractListModel):
    def __init__(self, roles, parent=None):
        super().__init__(parent)
        self._roles = {Qt.UserRole + 1 + i: QByteArray(r.encode())
                       for i, r in enumerate(roles)}
        self._rnames = list(roles)
        self._rows = []

    def rowCount(self, p=QModelIndex()):
        return len(self._rows)

    def roleNames(self):
        return self._roles

    def data(self, ix, role):
        i = ix.row()
        if 0 <= i < len(self._rows):
            key = self._rnames[role - (Qt.UserRole + 1)]
            return self._rows[i].get(key)
        return None

    def reset(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def update_row(self, i, d):
        if 0 <= i < len(self._rows):
            self._rows[i].update(d)
            self.dataChanged.emit(self.index(i, 0), self.index(i, 0),
                                  list(self._roles.keys()))


# ───────────────────────── 백엔드 ─────────────────────────
class SettingsBackend(QObject):
    changed = Signal()                 # 일반/상태 프로퍼티 갱신
    sig_valve_config_changed = Signal()

    def __init__(self, page):
        super().__init__(page)
        self._p = page

    # ---- 상태 프로퍼티 getter ----
    def _g(attr, default=""):
        def _get(self):
            return getattr(self._p, attr, default)
        return _get

    ipText = Property(str, _g("_ip", "192.168.0.10"), notify=changed)
    portText = Property(str, _g("_port", "9094"), notify=changed)
    plcConnected = Property(bool, lambda s: s._p._plc_connected, notify=changed)
    connText = Property(str, lambda s: "해제" if s._p._plc_connected else "연결",
                        notify=changed)
    statusText = Property(str, lambda s: s._p._status_text, notify=changed)
    statusColor = Property(str, lambda s: s._p._status_color, notify=changed)
    lang = Property(str, lambda s: s._p._lang, notify=changed)
    brightness = Property(int, lambda s: s._p._brightness, notify=changed)
    homeOn = Property(bool, lambda s: s._p._p_home, notify=changed)
    wSsid = Property(str, lambda s: s._p._w["ssid"], notify=changed)
    wSignal = Property(str, lambda s: s._p._w["signal"], notify=changed)
    wIp = Property(str, lambda s: s._p._w["ip"], notify=changed)
    wIface = Property(str, lambda s: s._p._w["iface"], notify=changed)
    wToggleText = Property(str, lambda s: s._p._w["toggle"], notify=changed)
    eIface = Property(str, lambda s: s._p._e["iface"], notify=changed)
    eState = Property(str, lambda s: s._p._e["state"], notify=changed)
    eStateColor = Property(str, lambda s: s._p._e["scolor"], notify=changed)
    eIp = Property(str, lambda s: s._p._e["ip"], notify=changed)
    eMethod = Property(str, lambda s: s._p._e["method"], notify=changed)
    eGw = Property(str, lambda s: s._p._e["gw"], notify=changed)
    eConn = Property(str, lambda s: s._p._e["conn"], notify=changed)
    netPriority = Property(str, lambda s: s._p._net_prio, notify=changed)
    ilOpen = Property(bool, lambda s: s._p._il_open, notify=changed)

    # ---- 슬롯: 전부 page 의 verbatim 로직 호출 ----
    @Slot(int)
    def tabChanged(self, idx):
        self._p._on_tab_changed(idx)

    @Slot()
    def editIp(self):
        self._p._edit_general("ip")

    @Slot()
    def editPort(self):
        self._p._edit_general("port")

    @Slot()
    def connectClicked(self):
        self._p._on_connect_clicked()

    @Slot(str)
    def setLang(self, code):
        self._p._set_language(code)

    @Slot(int)
    def setBrightness(self, pct):
        self._p._set_brightness(pct)

    @Slot(int)
    def previewBrightness(self, pct):
        # 드래그 중: sysfs 즉시 반영만(JSON 저장 X, changed emit X → 바인딩 충돌 방지).
        try:
            backlight.set_percent(pct, persist=False)
            self._p._brightness = backlight._clamp(pct)
        except Exception:
            pass

    @Slot()
    def exitClicked(self):
        self._p._on_exit_clicked()

    @Slot(int)
    def editInName(self, i):
        self._p._edit_io_name(i, True)

    @Slot(int)
    def editOutName(self, i):
        self._p._edit_io_name(i, False)

    @Slot()
    def applyIoNames(self):
        self._p._apply_io_names()

    @Slot(int)
    def toggleAxisUse(self, i):
        self._p._p_use[i] = not self._p._p_use[i]
        self._p._refresh_param_model()

    @Slot(int)
    def toggleAxisDir(self, i):
        self._p._p_dir[i] = 1 - self._p._p_dir[i]
        self._p._refresh_param_model()

    @Slot(int)
    def editStroke(self, i):
        self._p._edit_stroke(i)

    @Slot(int)
    def editAccel(self, i):
        self._p._edit_num(self._p._p_accel, i)

    @Slot(int)
    def editPpr(self, i):
        self._p._edit_num(self._p._p_ppr, i)

    @Slot()
    def toggleHome(self):
        self._p._on_home_toggle_clicked()

    @Slot(int)
    def datasetPressed(self, i):
        self._p._on_dataset_pressed(i)

    @Slot(int)
    def datasetReleased(self, i):
        self._p._on_dataset_released(i)

    @Slot()
    def saveParams(self):
        self._p._save_params()

    @Slot()
    def saveValveConfig(self):
        self._p._save_valve_config()

    @Slot(int)
    def toggleValveEnabled(self, i):
        self._p._v_enabled[i] = not self._p._v_enabled[i]
        self._p._refresh_valve_row(i)

    @Slot(int)
    def editValveName(self, i):
        self._p._edit_valve_name(i)

    @Slot(int)
    def toggleValveMode(self, i):
        self._p._v_mode[i] = not self._p._v_mode[i]
        self._p._refresh_valve_row(i)

    @Slot(int)
    def moveValveUp(self, i):
        self._p._move_valve_up(i)

    @Slot(int)
    def moveValveDown(self, i):
        self._p._move_valve_down(i)

    @Slot(int)
    def toggleValveJog(self, i):
        self._p._on_jog_valve_toggled(i)

    @Slot(int)
    def jogOrderUp(self, i):
        self._p._move_jog_order(i, -1)

    @Slot(int)
    def jogOrderDown(self, i):
        self._p._move_jog_order(i, +1)

    @Slot()
    def addAlarm(self):
        self._p._add_alarm()

    @Slot(int)
    def editAlarm(self, no):
        self._p._edit_alarm(no)

    @Slot(int)
    def deleteAlarm(self, no):
        self._p._delete_alarm(no)

    @Slot()
    def saveAlarms(self):
        self._p._save_alarms()

    @Slot()
    def openInterlock(self):
        self._p._open_interlock_dialog()

    @Slot(int)
    def ilCycle(self, idx):
        self._p._il_cycle(idx)

    @Slot(int)
    def ilToggleExcl(self, g):
        self._p._il_toggle_excl(g)

    @Slot(int)
    def ilToggleMand(self, g):
        self._p._il_toggle_mand(g)

    @Slot()
    def ilClear(self):
        self._p._il_clear()

    @Slot()
    def ilAccept(self):
        self._p._il_accept()

    @Slot()
    def ilReject(self):
        self._p._il_reject()

    @Slot(str)
    def wifiBtn(self, key):
        self._p._wifi_btn(key)

    @Slot(int)
    def wifiItemActivated(self, idx):
        self._p._on_wifi_item_activated(idx)


# ───────────────────────── 페이지 ─────────────────────────
class PageSettingsQml(QWidget):
    sig_valve_config_changed = Signal()

    def __init__(self):
        super().__init__()
        self.plc_client = None

        # ---- 상태 배열 (원본 위젯 내용과 1:1) ----
        self._ip = "192.168.0.10"
        self._port = "9094"
        self._plc_connected = False
        self._status_text = "● Disconnected"
        self._status_color = "#FF4646"
        self._lang = (LanguageManager.instance().current_lang
                      if LanguageManager else "KR")
        try:
            self._brightness = backlight.get_percent()
        except Exception:
            self._brightness = 100

        self._v_enabled = [i >= 16 for i in range(32)]
        self._v_name = [(_DEF_Y2X[i - 16] if i >= 16 else _DEF_Y0X[i])
                        for i in range(32)]
        self._v_mode = [True] * 32          # True=toggle
        self._jog_order = []
        self._JOG_MAX = 10          # JOG 팝업 최대 밸브 수

        self._p_use = [False] * 8
        self._p_dir = [0] * 8
        self._p_stroke = ["0.000 mm"] * 8
        self._p_accel = ["100"] * 8
        self._p_ppr = ["15000"] * 8
        self._p_home = False

        mgr = IOManager.instance() if IOManager else None
        self._in_name = [(mgr.get_input_name(i) if mgr else "") for i in range(32)]
        self._out_name = [(mgr.get_output_name(i) if mgr else "") for i in range(32)]

        self._w = {"ssid": "-", "signal": "-", "ip": "-", "iface": "-",
                   "toggle": "연결"}
        self._e = {"iface": "-", "state": "-", "scolor": "#DDDDDD", "ip": "-",
                   "method": "-", "gw": "-", "conn": "-"}
        self._net_prio = "wifi"  # 인터넷 우선(기본 무선). 탭 진입 시 실측 반영.
        self._last_wifi_ssid = ""
        self._wifi = None
        self._scan_worker = None
        self._wifi_status_worker = None
        self._eth_status_worker = None
        self._wifi_nets = []

        # ---- 인터록 오버레이 상태 (별도 윈도우 X) ----
        self._il_open = False
        self._il_groups = []
        self._il_mandatory = []
        self._il_exclusive = []
        self._il_get_name = None
        self._il_colors = []
        self._il_max_group = 8

        # ---- 모델 ----
        self._io_model = _ListModel(["xaddr", "inname", "yaddr", "outname"], self)
        self._param_model = _ListModel(
            ["axname", "axuse", "axdir", "axstroke", "axaccel", "axppr"], self)
        self._valve_model = _ListModel(
            ["vyaddr", "venabled", "vname", "vtoggle", "vjog"], self)
        self._alarm_model = _ListModel(["ano", "amsg", "anoraw"], self)
        self._wifi_model = _ListModel(["wtext"], self)
        self._il_mode_model = _ListModel(
            ["mtext", "mbg", "mborder", "mbw", "mfg"], self)
        self._il_grp_model = _ListModel(
            ["gnum", "glabel", "gcardbg", "gcardborder", "glabelbg",
             "extext", "exbg", "exborder", "exbw", "exfg",
             "mntext", "mnbg", "mnborder", "mnbw", "mnfg"], self)
        self._be = SettingsBackend(self)
        self._be.sig_valve_config_changed.connect(self.sig_valve_config_changed)

        # ---- QML ----
        self._view = QQuickWidget(self)
        self._view.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self._view.setClearColor(QColor("#16202B"))
        ctx = self._view.rootContext()
        ctx.setContextProperty("ioModel", self._io_model)
        ctx.setContextProperty("paramModel", self._param_model)
        ctx.setContextProperty("valveModel", self._valve_model)
        ctx.setContextProperty("alarmModel", self._alarm_model)
        ctx.setContextProperty("wifiModel", self._wifi_model)
        ctx.setContextProperty("ilModeModel", self._il_mode_model)
        ctx.setContextProperty("ilGroupModel", self._il_grp_model)
        ctx.setContextProperty("settingsBackend", self._be)
        self._view.setSource(QUrl.fromLocalFile(_QML_PATH))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)

        # WiFi 주기 타이머 (page_settings 와 동일)
        self._wifi_scan_timer = QTimer(self)
        self._wifi_scan_timer.setInterval(15000)
        self._wifi_scan_timer.timeout.connect(self._auto_scan_tick)
        self._net_status_timer = QTimer(self)
        self._net_status_timer.setInterval(3000)
        self._net_status_timer.timeout.connect(self._net_status_tick)

        if IOManager:
            IOManager.instance().sig_names_changed.connect(self._on_manager_changed)

        self._load_plc_settings()
        self._load_valve_config()
        self._load_io_input_names()
        self._refresh_all_models()
        self.update_language()

    def _overlay(self):
        return getattr(self.window(), "qml_overlay", None)

    def _message(self, title, message, *, error=False):
        overlay = self._overlay()
        if overlay:
            overlay.show_message(title, message, error=error)

    # ---- 모델 갱신 ----
    def _io_row(self, i):
        xa = i if i < 16 else i + 16
        ya = i if i < 16 else i + 16
        return {"xaddr": f"X{xa:02X}", "inname": self._in_name[i],
                "yaddr": f"Y{ya:02X}", "outname": self._out_name[i]}

    def _refresh_io_model(self):
        self._io_model.reset([self._io_row(i) for i in range(32)])

    def _refresh_io_row(self, i):
        self._io_model.update_row(i, self._io_row(i))

    def _refresh_param_model(self):
        rows = []
        for i in range(8):
            rows.append({"axname": AXIS_NAMES[i], "axuse": self._p_use[i],
                         "axdir": self._p_dir[i], "axstroke": self._p_stroke[i],
                         "axaccel": self._p_accel[i], "axppr": self._p_ppr[i]})
        self._param_model.reset(rows)
        self._be.changed.emit()

    def _valve_row(self, i):
        ya = i if i < 16 else i + 16
        return {"vyaddr": f"Y{ya:02X}", "venabled": self._v_enabled[i],
                "vname": self._v_name[i], "vtoggle": self._v_mode[i],
                "vjog": i in self._jog_order}

    def _refresh_valve_model(self):
        # 전체 reset — 로드/초기화 전용 (ListView 스크롤 맨위로 튐)
        self._valve_model.reset([self._valve_row(i) for i in range(32)])

    def _refresh_valve_row(self, i):
        # 단일 행 dataChanged — 스크롤 위치 보존 (버튼 조작용)
        self._valve_model.update_row(i, self._valve_row(i))

    def _refresh_alarm_model(self):
        from ui.overlays.alarm_overlay import USER_ALARMS
        rows = [{"ano": f"A-{no:03d}", "amsg": USER_ALARMS[no], "anoraw": no}
                for no in sorted(USER_ALARMS.keys())]
        self._alarm_model.reset(rows)

    def _refresh_wifi_model(self):
        self._wifi_model.reset([{"wtext": t} for t in self._wifi_nets])

    def _refresh_all_models(self):
        self._refresh_io_model()
        self._refresh_param_model()
        self._refresh_valve_model()
        self._refresh_alarm_model()
        self._refresh_wifi_model()

    # ===================================================================
    # 밸브 설정 — page_settings.py 와 동일 (값 출처만 상태배열)
    # ===================================================================
    def _edit_valve_name(self, idx):
        overlay = self._overlay()
        if overlay:
            def done(accepted, value):
                if accepted and value.strip():
                    self._v_name[idx] = value.strip()
                    self._refresh_valve_row(idx)
            overlay.request_text("밸브 이름 입력", self._v_name[idx], callback=done)

    def _move_valve_up(self, idx):
        if idx == 0:
            return
        self._swap_valve_data(idx, idx - 1)

    def _move_valve_down(self, idx):
        if idx >= 31:
            return
        self._swap_valve_data(idx, idx + 1)

    def _swap_valve_data(self, a, b):
        self._v_enabled[a], self._v_enabled[b] = self._v_enabled[b], self._v_enabled[a]
        self._v_name[a], self._v_name[b] = self._v_name[b], self._v_name[a]
        self._v_mode[a], self._v_mode[b] = self._v_mode[b], self._v_mode[a]
        self._refresh_valve_row(a)
        self._refresh_valve_row(b)

    def _on_jog_valve_toggled(self, valve_idx):
        # 원본 _on_jog_valve_toggled 와 동일 로직 (체크 상태는 멤버십으로 표현)
        if valve_idx not in self._jog_order:
            if len(self._jog_order) >= self._JOG_MAX:
                return
            self._jog_order.append(valve_idx)
        else:
            self._jog_order.remove(valve_idx)
        self._refresh_valve_row(valve_idx)

    def _move_jog_order(self, valve_idx, direction):
        if valve_idx not in self._jog_order:
            return
        pos = self._jog_order.index(valve_idx)
        new_pos = pos + direction
        if 0 <= new_pos < len(self._jog_order):
            self._jog_order[pos], self._jog_order[new_pos] = \
                self._jog_order[new_pos], self._jog_order[pos]
        self._refresh_valve_row(valve_idx)

    def _build_valve_config(self):
        valve_config = []
        for i in range(32):
            mode = "toggle" if self._v_mode[i] else "momentary"
            jog_pos = self._jog_order.index(i) if i in self._jog_order else -1
            valve_config.append({
                "index": i,
                "name": self._v_name[i],
                "mode": mode,
                "enabled": self._v_enabled[i],
                "jog_valve": i in self._jog_order,
                "jog_order": jog_pos,
                "order": i
            })
        return valve_config

    def _save_valve_config_silent(self):
        try:
            path = _get_settings_path()
            settings = load_json(path) or {}
            settings["valve_config"] = self._build_valve_config()
            save_json(path, settings)
            self._be.sig_valve_config_changed.emit()
            print("[Settings] 밸브 설정 자동 저장 완료")
        except Exception as e:
            print(f"[Settings] 밸브 설정 자동 저장 실패: {e}")

    def _save_valve_config(self):
        try:
            path = _get_settings_path()
            settings = load_json(path) or {}
            settings["valve_config"] = self._build_valve_config()
            save_json(path, settings)
            print("[Settings] 밸브 설정 저장 완료")
            self._be.sig_valve_config_changed.emit()
            self._sync_valve_names_to_io()
            self._message("저장 완료", "밸브 설정이 저장되었습니다.")
        except Exception as e:
            print(f"[Settings] 밸브 설정 저장 실패: {e}")

    def _load_valve_config(self):
        try:
            path = _get_settings_path()
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    valve_config = settings.get("valve_config", None)
                    if valve_config and len(valve_config) == 32:
                        jog_entries = [(cfg.get("jog_order", -1), i)
                                       for i, cfg in enumerate(valve_config)
                                       if cfg.get("jog_valve", False)]
                        jog_entries.sort(key=lambda x: x[0])
                        self._jog_order = [idx for _, idx in jog_entries]
                        for i, cfg in enumerate(valve_config):
                            self._v_enabled[i] = cfg.get("enabled", True)
                            self._v_name[i] = cfg.get("name", f"밸브 {i+1}")
                            self._v_mode[i] = (cfg.get("mode", "toggle") == "toggle")
                        print("[Settings] 밸브 설정 로드 완료")
        except Exception as e:
            print(f"[Settings] 밸브 설정 로드 실패: {e}")
        self._sync_valve_names_to_io()

    def _sync_valve_names_to_io(self):
        if not IOManager:
            return
        mgr = IOManager.instance()
        for i in range(32):
            name = self._v_name[i] if i < len(self._v_name) else f"Y{i:02X}"
            mgr.outputs[i] = name
            self._out_name[i] = name
        self._refresh_io_model()
        mgr.sig_names_changed.emit()
        print("[Settings] IO 출력 이름을 밸브 설정과 동기화 완료")

    # ===================================================================
    # 시스템 파라미터 — DT 패킹 IDENTICAL (page_settings._save/_load_params)
    # ===================================================================
    def _edit_stroke(self, i):
        text = self._p_stroke[i].replace(" mm", "").strip()
        overlay = self._overlay()
        if overlay:
            def done(accepted, value):
                if accepted:
                    self._p_stroke[i] = f"{float(value):.3f} mm"
                    self._refresh_param_model()
            overlay.request_number("스트로크 (mm)", float(text or 0), decimal=True,
                                   signed=True, callback=done)

    def _edit_num(self, arr, i):
        overlay = self._overlay()
        if overlay:
            def done(accepted, value):
                if accepted:
                    arr[i] = str(int(value) if float(value).is_integer() else value)
                    self._refresh_param_model()
            overlay.request_number("값 입력", float(arr[i] or 0), decimal=True,
                                   signed=True, callback=done)

    def _on_home_toggle_clicked(self):
        self._p_home = not self._p_home
        self._be.changed.emit()
        if self.plc_client and self.plc_client.is_connected:
            self.plc_client.submit(self.plc_client.send_jog_mode, 1 if self._p_home else 0)

    def _on_dataset_pressed(self, axis_index):
        if not self.plc_client or not self.plc_client.is_connected:
            return
        val = (1 << axis_index)
        self.plc_client.submit(self.plc_client.write_words, 0x09,
                               self.plc_client.ADDR_AXIS_DATASET, [val])

    def _on_dataset_released(self, axis_index):
        if not self.plc_client or not self.plc_client.is_connected:
            return
        self.plc_client.submit(self.plc_client.write_words, 0x09,
                               self.plc_client.ADDR_AXIS_DATASET, [0])

    def _load_params(self):
        axis_uses_from_file = self._load_axis_settings()
        if not self.plc_client or not self.plc_client.is_connected:
            if axis_uses_from_file:
                for i in range(8):
                    if i < len(axis_uses_from_file):
                        self._p_use[i] = bool(axis_uses_from_file[i])
            self._refresh_param_model()
            return
        self.plc_client.submit(
            self.plc_client.read_words, 0x09, self.plc_client.AXIS_PARAM_ADDR, 50,
            callback=self._on_params_loaded,
        )

    def _on_params_loaded(self, data, error):
        try:
            if error is not None:
                raise error
            if not data or len(data) < 50:
                raise RuntimeError("PLC axis parameter response is incomplete")
            use_bits = data[0]
            for i in range(8):
                self._p_use[i] = bool((use_bits >> i) & 1)
            for i in range(8):
                self._p_dir[i] = data[1 + i]
            for i in range(8):
                idx = 9 + (i * 2)
                low, high = data[idx], data[idx + 1]
                val = (high << 16) | low
                if val > 0x7FFFFFFF:
                    val -= 0x100000000
                real_val = val / 1000.0
                self._p_stroke[i] = f"{real_val:.3f} mm"
            for i in range(8):
                self._p_accel[i] = str(data[25 + i])
            for i in range(8):
                idx = 34 + i * 2
                low = data[idx] if idx < len(data) else 0
                high = data[idx + 1] if idx + 1 < len(data) else 0
                val = low | (high << 16)
                self._p_ppr[i] = str(val if val > 0 else 15000)
        except Exception as e:
            print(f"Param Load Error: {e}")
        self._refresh_param_model()

    def _save_params(self):
        if not self.plc_client or not self.plc_client.is_connected:
            self._message("전송 실패", "PLC가 연결되어 있지 않습니다.", error=True)
            return
        try:
            send_data = [0] * 50
            use_mask = 0
            axis_uses_list = []
            for i in range(8):
                is_checked = self._p_use[i]
                axis_uses_list.append(is_checked)
                if is_checked:
                    use_mask |= (1 << i)
            send_data[0] = use_mask
            for i in range(8):
                send_data[1 + i] = self._p_dir[i]
            axis_strokes_list = []
            for i in range(8):
                text = self._p_stroke[i].replace(" mm", "").strip()
                try:
                    val_float = float(text)
                except Exception:
                    val_float = 0.0
                axis_strokes_list.append(val_float)
                val = int(val_float * 1000)
                low, high = val & 0xFFFF, (val >> 16) & 0xFFFF
                idx = 9 + (i * 2)
                send_data[idx] = low
                send_data[idx + 1] = high
            for i in range(8):
                try:
                    val = int(self._p_accel[i])
                except Exception:
                    val = 100
                send_data[25 + i] = val
            for i in range(8):
                try:
                    val = int(self._p_ppr[i])
                except Exception:
                    val = 15000
                idx = 34 + i * 2
                send_data[idx] = val & 0xFFFF
                send_data[idx + 1] = (val >> 16) & 0xFFFF
            def saved(result, error):
                if error is not None or not result:
                    self._message("오류", f"데이터 전송 중 오류가 발생했습니다.\n{error or 'write failed'}", error=True)
                    return
                self._save_axis_settings(axis_uses_list, axis_strokes_list)
                self._message("적용 완료", "시스템 파라미터가 PLC와 파일에 저장되었습니다.")
            self.plc_client.submit(
                self.plc_client.write_words, 0x09, self.plc_client.AXIS_PARAM_ADDR,
                send_data, callback=saved,
            )
        except Exception as e:
            self._message("오류", f"데이터 전송 중 오류가 발생했습니다.\n{e}", error=True)

    def _save_axis_settings(self, axis_uses_list, axis_strokes_list=None):
        try:
            path = _get_settings_path()
            settings = load_json(path) or {}
            settings["axis_uses"] = axis_uses_list
            if axis_strokes_list is not None:
                settings["axis_strokes"] = axis_strokes_list
            save_json(path, settings)
            print(f"[Settings] 축 설정 저장 완료: uses={axis_uses_list}, strokes={axis_strokes_list}")
        except Exception as e:
            print(f"[Settings] 축 설정 저장 실패: {e}")

    def _load_axis_settings(self):
        try:
            path = _get_settings_path()
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    axis_uses = settings.get("axis_uses", None)
                    if axis_uses and len(axis_uses) == 8:
                        print(f"[Settings] 축 설정 로드 완료: {axis_uses}")
                        return axis_uses
        except Exception as e:
            print(f"[Settings] 축 설정 로드 실패: {e}")
        return [True] * 8

    # ===================================================================
    # IO 이름 — page_settings 와 동일
    # ===================================================================
    def _edit_io_name(self, i, is_input):
        arr = self._in_name if is_input else self._out_name
        addr = (f"X{i if i<16 else i+16:02X}" if is_input
                else f"Y{i if i<16 else i+16:02X}")
        overlay = self._overlay()
        if overlay:
            def done(accepted, value):
                if accepted and value.strip():
                    arr[i] = value.strip()
                    self._refresh_io_row(i)
            overlay.request_text(addr, arr[i], callback=done)

    def _apply_io_names(self):
        if not IOManager:
            return
        new_inputs = list(self._in_name)
        new_outputs = list(self._out_name)
        IOManager.instance().update_names(new_inputs, new_outputs)
        for i in range(min(len(new_outputs), len(self._v_name))):
            self._v_name[i] = new_outputs[i]
        self._refresh_valve_model()
        self._save_valve_config_silent()
        try:
            path = _get_settings_path()
            settings = load_json(path) or {}
            settings["io_input_names"] = new_inputs
            save_json(path, settings)
            print("[Settings] IO 입력 이름 저장 완료")
        except Exception as e:
            print(f"[Settings] IO 입력 이름 저장 실패: {e}")
        self._message("적용 완료", "I/O 이름이 적용되었습니다.")

    def _load_io_input_names(self):
        from utils.io_manager import DEFAULT_INPUTS
        try:
            saved = []
            path = _get_settings_path()
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                saved = settings.get("io_input_names", [])
            names = list(DEFAULT_INPUTS)
            for i in range(min(len(saved), 32)):
                names[i] = saved[i]
            if IOManager:
                mgr = IOManager.instance()
                for i in range(32):
                    mgr.inputs[i] = names[i]
                    self._in_name[i] = names[i]
                mgr.sig_names_changed.emit()
            print("[Settings] IO 입력 이름 로드 완료")
        except Exception as e:
            print(f"[Settings] IO 입력 이름 로드 실패: {e}")

    def _on_manager_changed(self):
        if not IOManager:
            return
        mgr = IOManager.instance()
        for i in range(32):
            self._in_name[i] = mgr.get_input_name(i)
            self._out_name[i] = mgr.get_output_name(i)
        self._refresh_io_model()

    # ===================================================================
    # 알람 — page_settings 와 동일
    # ===================================================================
    def _alarm_next_no(self):
        from ui.overlays.alarm_overlay import USER_ALARMS
        return max(USER_ALARMS.keys(), default=0) + 1

    def _add_alarm(self):
        from ui.overlays.alarm_overlay import USER_ALARMS
        no = self._alarm_next_no()
        overlay = self._overlay()
        if overlay:
            def done(accepted, value):
                if accepted and value.strip():
                    USER_ALARMS[no] = value.strip()
                    self._refresh_alarm_model()
            overlay.request_text(f"A-{no:03d} 알람 메시지 입력", callback=done)

    def _edit_alarm(self, no):
        from ui.overlays.alarm_overlay import USER_ALARMS
        current = USER_ALARMS.get(no, "")
        overlay = self._overlay()
        if overlay:
            def done(accepted, value):
                if accepted and value.strip():
                    USER_ALARMS[no] = value.strip()
                    self._refresh_alarm_model()
            overlay.request_text(f"A-{no:03d} 알람 메시지 수정", current, callback=done)

    def _delete_alarm(self, no):
        from ui.overlays.alarm_overlay import USER_ALARMS
        overlay = self._overlay()
        if overlay:
            def done(accepted):
                if accepted:
                    USER_ALARMS.pop(no, None)
                    self._refresh_alarm_model()
            overlay.request_confirm("알람 삭제", f"A-{no:03d} 알람을 삭제하시겠습니까?",
                                    callback=done)

    def _save_alarms(self):
        from ui.overlays.alarm_overlay import save_user_alarms
        save_user_alarms()
        self._message("저장 완료", "알람 메시지가 저장되었습니다.")

    # ===================================================================
    # 인터록 — 같은 QML 씬 내 풀스크린 오버레이 (별도 윈도우 X).
    # 그룹순환/배타/필수/전체해제 로직은 page_mode.InterlockDialog 와 동일.
    # ===================================================================
    _IL_COLORS = [None, "#E74C3C", "#3498DB", "#2ECC71", "#F39C12",
                  "#9B59B6", "#1ABC9C", "#E67E22", "#E91E63"]
    _IL_DEFNAMES = [
        "제품측 취출", "런너측 취출", "주행 대기", "하강 대기", "주행도중개방",
        "복귀도중개방", "안전도어 회피", "안전도어 회피2", "낙하측 반전",
        "주행도중 반전", "취출대기 반전", "고정측 취출", "제품 형내개방",
        "런너 형내개방", "에젝터 연동", "언더컷 취출모드", "척1 사용",
        "척1 감지", "척2 사용", "척2 감지", "척3 사용", "척3 감지",
        "척4 사용", "척4 감지", "흡착1 사용", "흡착1 감지", "흡착2 사용",
        "흡착2 감지", "흡착3 사용", "흡착3 감지", "흡착4 사용", "흡착4 감지",
        "2포인트 개방", "공정감시 모드"]

    @staticmethod
    def _il_alpha(hex_color, aa):
        return "#" + aa + hex_color[1:]

    def _il_name(self, idx):
        try:
            from utils.mode_manager import ModeManager
            m = ModeManager.instance()
            if m:
                return m.get_name(idx)
        except Exception:
            pass
        return (self._IL_DEFNAMES[idx] if idx < len(self._IL_DEFNAMES)
                else f"User Mode {idx-33}")

    def _open_interlock_dialog(self):
        from ui.pages.page_mode import TOTAL_SLOTS
        try:
            with open(_get_settings_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
            g = d.get("interlock_groups", [0] * TOTAL_SLOTS)
            m = d.get("interlock_mandatory", [False] * 9)
            e = d.get("interlock_exclusive", [True] * 9)
            if len(g) < TOTAL_SLOTS:
                g += [0] * (TOTAL_SLOTS - len(g))
            if len(m) < 9:
                m += [False] * (9 - len(m))
            if len(e) < 9:
                e += [True] * (9 - len(e))
            self._il_groups, self._il_mandatory, self._il_exclusive = \
                g[:TOTAL_SLOTS], m[:9], e[:9]
        except Exception:
            self._il_groups = [0] * TOTAL_SLOTS
            self._il_mandatory = [False] * 9
            self._il_exclusive = [True] * 9
        self._il_colors = self._IL_COLORS
        self._il_max_group = len(self._IL_COLORS) - 1
        self._il_total = TOTAL_SLOTS
        self._il_build_groups()
        self._il_refresh_all()
        self._il_open = True
        self._be.changed.emit()

    # ---- 표시 계산 (page_mode.InterlockDialog 의 _refresh_* 와 동일 결과) ----
    def _il_mode_cell(self, idx):
        grp = self._il_groups[idx]
        name = self._il_name(idx)
        if grp > 0:
            tags = []
            if self._il_exclusive[grp]:
                tags.append("⊗")
            if self._il_mandatory[grp]:
                tags.append("★")
            suffix = " " + "".join(tags) if tags else ""
        else:
            suffix = ""
        if grp == 0:
            return {"mtext": f"{name}\n—", "mbg": "#0DFFFFFF",
                    "mborder": "#26FFFFFF", "mbw": 1, "mfg": "#9CA3AF"}
        c = self._il_colors[grp]
        return {"mtext": f"{name}\nG{grp}{suffix}",
                "mbg": self._il_alpha(c, "33"), "mborder": c, "mbw": 2,
                "mfg": c}

    def _il_grp_card(self, g):
        c = self._il_colors[g]
        d = {"gnum": g, "glabel": f"G{g}",
             "gcardbg": self._il_alpha(c, "22"),
             "gcardborder": self._il_alpha(c, "66"), "glabelbg": c}
        if self._il_exclusive[g]:
            d.update(extext="배타 ON ⊗", exbg=c, exborder=c, exbw=0,
                     exfg="white")
        else:
            d.update(extext="배타 OFF", exbg="#14FFFFFF", exborder="#555555",
                     exbw=1, exfg="#777777")
        if self._il_mandatory[g]:
            d.update(mntext="필수 ON ★", mnbg=c, mnborder=c, mnbw=0,
                     mnfg="white")
        else:
            d.update(mntext="필수 OFF", mnbg="#14FFFFFF", mnborder="#555555",
                     mnbw=1, mnfg="#777777")
        return d

    def _il_build_groups(self):
        self._il_grp_model.reset([self._il_grp_card(g)
                                  for g in range(1, self._il_max_group + 1)])

    def _il_refresh_group(self, g):
        self._il_grp_model.update_row(g - 1, self._il_grp_card(g))

    def _il_refresh_all(self):
        self._il_mode_model.reset(
            [self._il_mode_cell(i) for i in range(self._il_total)])

    def _il_refresh_btn(self, idx):
        self._il_mode_model.update_row(idx, self._il_mode_cell(idx))

    # ---- 로직 (page_mode.InterlockDialog 와 동일) ----
    def _il_cycle(self, idx):
        self._il_groups[idx] = (self._il_groups[idx] + 1) % (self._il_max_group + 1)
        self._il_refresh_btn(idx)

    def _il_clear(self):
        self._il_groups = [0] * self._il_total
        self._il_refresh_all()

    def _il_toggle_excl(self, g):
        self._il_exclusive[g] = not self._il_exclusive[g]
        self._il_refresh_group(g)
        self._il_refresh_all()   # 모드 버튼 suffix 갱신 (원본과 동일)

    def _il_toggle_mand(self, g):
        self._il_mandatory[g] = not self._il_mandatory[g]
        self._il_refresh_group(g)  # 원본은 mandatory 토글 시 grid 갱신 안 함

    def _il_accept(self):
        path = _get_settings_path()
        data = load_json(path) or {}
        data["interlock_groups"] = self._il_groups[:]
        data["interlock_mandatory"] = self._il_mandatory[:]
        data["interlock_exclusive"] = self._il_exclusive[:]
        save_json(path, data)
        self._il_open = False
        self._be.changed.emit()

    def _il_reject(self):
        self._il_open = False
        self._be.changed.emit()

    # ===================================================================
    # 일반/PLC/언어 — page_settings 와 동일
    # ===================================================================
    def _edit_general(self, which):
        is_ip = (which == "ip")
        cur = self._ip if is_ip else self._port
        overlay = self._overlay()
        if not overlay:
            return
        def done(accepted, value):
            if not accepted:
                return
            if is_ip:
                self._ip = value.strip()
            else:
                self._port = str(int(value))
            self._be.changed.emit()
        if is_ip:
            overlay.request_text("PLC IP", cur, callback=done)
        else:
            overlay.request_number("PLC PORT", float(cur or 0), minimum=1,
                                   maximum=65535, callback=done)

    def _on_connect_clicked(self):
        if not self.plc_client:
            return
        if self._plc_connected:
            self.plc_client.disconnect_plc()
        else:
            ip = self._ip.strip()
            port = self._port.strip()
            if not ip or not port:
                return
            self._save_plc_settings(ip, port)
            self._status_text = "● Connecting..."
            self._status_color = "orange"
            self._be.changed.emit()
            self.plc_client.connect_to_plc(ip, port)

    def _on_plc_status_changed(self, connected):
        self._plc_connected = bool(connected)
        if connected:
            self._status_text = "● Connected"
            self._status_color = "#00FF00"
            if self._cur_tab == 2:
                self._load_params()
        else:
            self._status_text = "● Disconnected"
            self._status_color = "#FF4646"
        self._be.changed.emit()

    def _save_plc_settings(self, ip, port):
        try:
            path = _get_settings_path()
            settings = load_json(path) or {}
            settings["plc_ip"] = ip
            settings["plc_port"] = port
            save_json(path, settings)
        except Exception as e:
            print(f"Settings Save Error: {e}")

    def _load_plc_settings(self):
        try:
            settings = load_json(_get_settings_path()) or {}
            self._ip = settings.get("plc_ip", "192.168.0.10")
            self._port = settings.get("plc_port", "9094")
        except Exception as e:
            print(f"[Settings] PLC 설정 로드 실패: {e}")

    def _on_exit_clicked(self):
        overlay = self._overlay()
        if overlay:
            overlay.request_confirm(
                "프로그램 종료", "정말로 프로그램을 종료하시겠습니까?",
                accept_text="종료", reject_text="취소",
                callback=lambda accepted: QApplication.instance().quit() if accepted else None,
            )

    def _set_language(self, code):
        if not LanguageManager:
            return
        LanguageManager.instance().set_language(code)
        self._lang = code
        self.update_language()

    def _set_brightness(self, pct):
        # 즉시 적용 + settings.json("screen_brightness")에 0~100 저장.
        try:
            backlight.set_percent(pct, persist=True)
            self._brightness = backlight.get_percent()
        except Exception as e:
            print(f"[Settings] 밝기 설정 실패: {e}")
        self._be.changed.emit()

    def update_language(self, lang_code=None):
        if LanguageManager:
            self._lang = LanguageManager.instance().current_lang
        self._be.changed.emit()

    def set_plc_client(self, client):
        self.plc_client = client
        if self.plc_client:
            try:
                self.plc_client.sig_connected.connect(
                    self._on_plc_status_changed, Qt.UniqueConnection)
            except (RuntimeError, TypeError):
                pass
            self._on_plc_status_changed(self.plc_client.is_connected)

    # ===================================================================
    # WiFi / Ethernet — page_settings 와 동일 (워커 재사용)
    # ===================================================================
    def _ensure_wifi(self):
        if self._wifi is None:
            try:
                from utils import wifi_manager
                self._wifi = wifi_manager
            except Exception:
                self._wifi = None
        return self._wifi

    def _wifi_btn(self, key):
        {"refreshWifi": self._refresh_wifi_status,
         "scanWifi": lambda: self._scan_wifi(False),
         "toggleWifi": self._toggle_wifi_connection,
         "refreshEth": self._refresh_eth_status,
         "ethDhcp": self._apply_eth_dhcp,
         "ethStatic": self._open_eth_static_dialog,
         "prioWifi": lambda: self._set_net_priority("wifi"),
         "prioEth": lambda: self._set_net_priority("eth")}.get(key, lambda: None)()

    def _refresh_wifi_status(self):
        w = self._ensure_wifi()
        if not w:
            return
        if not w.is_available():
            self._w.update(ssid="nmcli 없음", ip="-", signal="-", iface="-")
            self._be.changed.emit()
            return
        worker = self._wifi_status_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    return
            except RuntimeError:
                self._wifi_status_worker = None
        self._wifi_status_worker = WifiStatusWorker(w, self)
        self._wifi_status_worker.sig_done.connect(self._on_wifi_status_done)
        self._wifi_status_worker.finished.connect(
            lambda: setattr(self, "_wifi_status_worker", None))
        self._wifi_status_worker.finished.connect(
            self._wifi_status_worker.deleteLater)
        self._wifi_status_worker.start()

    def _on_wifi_status_done(self, info):
        self._w["ssid"] = info["ssid"] or "(미연결)"
        self._w["ip"] = info["ip"] or "-"
        self._w["signal"] = f"{info['signal']}%" if info["signal"] else "-"
        self._w["iface"] = info["iface"] or "-"
        connected = bool(info["ssid"])
        if connected and info["ssid"]:
            self._last_wifi_ssid = info["ssid"]
        self._w["toggle"] = "연결 해제" if connected else "연결"
        self._be.changed.emit()

    def _scan_wifi(self, silent=False):
        w = self._ensure_wifi()
        if not w or not w.is_available():
            return
        worker = self._scan_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    return
            except RuntimeError:
                self._scan_worker = None
        self._scan_worker = WifiScanWorker(w, self)
        self._scan_worker.sig_done.connect(
            lambda nets, s=silent: self._on_scan_done(nets, s))
        self._scan_worker.finished.connect(
            lambda: setattr(self, "_scan_worker", None))
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_worker.start()

    def _on_scan_done(self, networks, silent):
        self._wifi_nets = []
        self._scan_net_data = []
        if not networks:
            self._wifi_nets = ["(발견된 네트워크가 없습니다)"]
            self._scan_net_data = [None]
        else:
            for net in networks:
                ssid = net["ssid"]
                sig = net["signal"] or "0"
                lock = "🔒 " if net["security"] and net["security"] != "--" else ""
                mark = "● " if net["in_use"] else "   "
                self._wifi_nets.append(f"{mark}{lock}{ssid}   ({sig}%)")
                self._scan_net_data.append(net)
        self._refresh_wifi_model()

    def _on_wifi_item_activated(self, idx):
        data = getattr(self, "_scan_net_data", [])
        if not (0 <= idx < len(data)):
            return
        net = data[idx]
        if not net:
            return
        ssid = net["ssid"]
        secured = bool(net["security"]) and net["security"] != "--"
        password = None
        if secured:
            overlay = self._overlay()
            if overlay:
                overlay.request_text(
                    f"'{ssid}' 암호", password=True,
                    callback=lambda accepted, value: self._connect_wifi(ssid, value)
                    if accepted and value else None,
                )
            return
        self._connect_wifi(ssid, password)

    def _connect_wifi(self, ssid, password=None):
        try:
            res = self._wifi.connect(ssid, password)
        except Exception as e:
            res = {"ok": "0", "error": str(e)}
        if res.get("ok") == "1":
            self._show_wifi_msg("연결 완료", f"'{ssid}' 에 연결되었습니다.")
        else:
            self._show_wifi_msg("연결 실패", res.get("error", "알 수 없는 오류"))
        self._refresh_wifi_status()

    def _toggle_wifi_connection(self):
        w = self._ensure_wifi()
        if not w or not w.is_available():
            return
        connected = self._w["ssid"] not in ("", "-", "(미연결)", "nmcli 없음")
        if connected:
            res = w.disconnect()
            if res.get("ok") != "1":
                self._show_wifi_msg("해제 실패", res.get("error", "알 수 없는 오류"))
        else:
            ssid = self._last_wifi_ssid
            if not ssid:
                self._show_wifi_msg("재접속 불가",
                                    "마지막으로 연결됐던 SSID 정보가 없습니다.\n"
                                    "아래 목록에서 더블클릭으로 연결하세요.")
                return
            try:
                res = w.connect_saved(ssid)
            except Exception as e:
                res = {"ok": "0", "error": str(e)}
            if res.get("ok") != "1":
                self._show_wifi_msg(
                    "연결 실패",
                    f"'{ssid}' 재접속 실패: {res.get('error', '알 수 없는 오류')}")
        self._refresh_wifi_status()

    def _show_wifi_msg(self, title, message):
        self._message(title, message, error=("실패" in title or "오류" in title))

    def _auto_scan_tick(self):
        self._scan_wifi(silent=True)

    def _net_status_tick(self):
        self._refresh_wifi_status()
        self._refresh_eth_status()

    def _start_auto_scan(self):
        if not self._wifi_scan_timer.isActive():
            self._wifi_scan_timer.start()
        if not self._net_status_timer.isActive():
            self._net_status_timer.start()

    def _stop_auto_scan(self):
        if self._wifi_scan_timer.isActive():
            self._wifi_scan_timer.stop()
        if self._net_status_timer.isActive():
            self._net_status_timer.stop()

    def _refresh_eth_status(self):
        w = self._ensure_wifi()
        if not w:
            return
        worker = self._eth_status_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    return
            except RuntimeError:
                self._eth_status_worker = None
        self._eth_status_worker = EthernetStatusWorker(w, self)
        self._eth_status_worker.sig_done.connect(self._on_eth_status_done)
        self._eth_status_worker.finished.connect(
            lambda: setattr(self, "_eth_status_worker", None))
        self._eth_status_worker.finished.connect(
            self._eth_status_worker.deleteLater)
        self._eth_status_worker.start()

    def _on_eth_status_done(self, info):
        self._e["iface"] = info["iface"] or "-"
        state = info["state"] or "-"
        self._e["scolor"] = "#77FF88" if state == "connected" else "#FF7777"
        self._e["state"] = state
        self._e["ip"] = info["ip"] or "-"
        self._e["gw"] = info["gateway"] or "-"
        method_map = {"auto": "DHCP", "manual": "고정 IP"}
        self._e["method"] = method_map.get(info["method"], info["method"] or "-")
        self._e["conn"] = info["connection"] or "-"
        self._be.changed.emit()

    def _apply_eth_dhcp(self):
        w = self._ensure_wifi()
        if not w:
            return
        res = w.set_ethernet_dhcp()
        if res.get("ok") == "1":
            self._show_wifi_msg("DHCP 적용", "유선 연결을 DHCP로 변경했습니다.")
        else:
            self._show_wifi_msg("실패", res.get("error", "알 수 없는 오류"))
        self._refresh_eth_status()

    def _open_eth_static_dialog(self):
        w = self._ensure_wifi()
        if not w:
            return
        cur = w.get_ethernet_status()
        values = {"ip": cur["ip"], "prefix": "24", "gateway": cur["gateway"], "dns": "8.8.8.8"}
        fields = [("ip", "고정 IP 주소"), ("prefix", "Prefix (예: 24)"),
                  ("gateway", "Gateway"), ("dns", "DNS")]
        overlay = self._overlay()
        if not overlay:
            return
        def ask(pos):
            if pos >= len(fields):
                self._apply_eth_static(values)
                return
            key, title = fields[pos]
            overlay.request_text(
                title, values[key],
                callback=lambda accepted, value, p=pos, k=key: (
                    values.__setitem__(k, value.strip()), ask(p + 1)
                ) if accepted and value.strip() else None,
            )
        ask(0)

    def _apply_eth_static(self, values):
        w = self._ensure_wifi()
        if not w:
            return
        try:
            prefix = int(values["prefix"])
        except ValueError:
            self._show_wifi_msg("실패", "Prefix는 숫자여야 합니다.")
            return
        res = w.set_ethernet_static(values["ip"], prefix,
                                    values["gateway"], values["dns"])
        if res.get("ok") == "1":
            self._show_wifi_msg("고정 IP 적용",
                                f"{values['ip']}/{prefix} 로 설정했습니다.")
        else:
            self._show_wifi_msg("실패", res.get("error", "알 수 없는 오류"))
        self._refresh_eth_status()

    def _refresh_net_priority(self):
        w = self._ensure_wifi()
        if not w:
            return
        try:
            self._net_prio = w.get_internet_priority()
        except Exception:
            pass
        self._be.changed.emit()

    def _set_net_priority(self, prefer):
        w = self._ensure_wifi()
        if not w:
            return
        # PLC IP(일반설정에서 설정된 값)를 eth0 호스트 라우트로 고정 → 무선
        # 우선이어도 PLC 통신은 eth0 보장.
        plc_ip = (self._ip or "").strip()
        res = w.set_internet_priority(prefer, plc_ip)
        if res.get("ok") == "1":
            label = "무선(WiFi)" if prefer == "wifi" else "유선(Ethernet)"
            extra = (f"\nPLC({plc_ip})는 유선(eth0)으로 고정됩니다."
                     if prefer == "wifi" and plc_ip else "")
            self._show_wifi_msg("인터넷 우선순위",
                                f"인터넷 우선을 {label}로 설정했습니다.{extra}")
        else:
            self._show_wifi_msg("실패", res.get("error", "알 수 없는 오류"))
        self._refresh_net_priority()
        self._refresh_eth_status()

    # ===================================================================
    # 탭/표시 (page_settings 와 동일 동작)
    # ===================================================================
    _cur_tab = 0

    def _on_tab_changed(self, index):
        self._cur_tab = index
        if index == 2:
            self._load_params()
        if index == 6:
            self._refresh_wifi_status()
            self._refresh_eth_status()
            self._refresh_net_priority()
            self._scan_wifi(silent=True)
            self._start_auto_scan()
        else:
            self._stop_auto_scan()

    def showEvent(self, event):
        if not self.plc_client:
            mw = self.window()
            if hasattr(mw, 'plc_client'):
                self.set_plc_client(mw.plc_client)
        if self.plc_client:
            self._on_plc_status_changed(self.plc_client.is_connected)
        if self._cur_tab == 2:
            self._load_params()
        if self._cur_tab == 6:
            self._refresh_wifi_status()
            self._refresh_eth_status()
            self._refresh_net_priority()
            self._start_auto_scan()
        super().showEvent(event)

    def hideEvent(self, event):
        self._stop_auto_scan()
        super().hideEvent(event)
