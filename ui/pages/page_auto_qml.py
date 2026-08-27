"""
자동운전 페이지 QML(GPU) — PageAuto drop-in.
UI/스크롤만 QML. 로직(속도·운전모드·확인창·monitor)은 PageAuto 와 동일.
확인/메시지 입력은 애플리케이션 공통 QML 오버레이를 사용한다.
"""
import os

from PySide6.QtCore import (Qt, QObject, Signal, Slot, Property, QTimer)

from ui.pages.page_manual_qml import AxisModel, IoModel, IoBackend
from utils.variable_store import VariableStore

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

_DEFAULT_INFO_CONFIG = (
    ("생산/취출횟수", "회"),
    ("목표횟수", "회"),
    ("취출 싸이클시간", "초"),
    ("성형 싸이클시간", "초"),
)


def default_auto_info_config():
    return [
        {"name": name, "data_id": -1, "plc_source": index}
        for index, (name, _unit) in enumerate(_DEFAULT_INFO_CONFIG)
    ]


def normalize_auto_info_config(raw):
    if raw is None or not isinstance(raw, list):
        return default_auto_info_config()
    rows = raw[:6]
    result = []
    for index, item in enumerate(rows):
        item = item if isinstance(item, dict) else {}
        default_name = (_DEFAULT_INFO_CONFIG[index][0] if index < 4
                        else f"운전정보 {index + 1}")
        name = str(item.get("name", default_name)).strip() or default_name
        try:
            data_id = int(item.get("data_id", -1))
        except (TypeError, ValueError):
            data_id = -1
        try:
            plc_source = int(item.get("plc_source", index if index < 4 else -1))
        except (TypeError, ValueError):
            plc_source = -1
        result.append({
            "name": name,
            "data_id": data_id if data_id >= 0 else -1,
            "plc_source": plc_source if 0 <= plc_source < 4 else -1,
        })
    return result


def _axis_config_masks(settings):
    """Return (visible-axis mask, axes that require homing)."""
    uses = settings.get("axis_uses", [True] * 8)
    if not isinstance(uses, list) or len(uses) != 8:
        uses = [True] * 8
    encoders = settings.get("axis_encoder_types", ["incremental"] * 8)
    if not isinstance(encoders, list) or len(encoders) != 8:
        encoders = ["incremental"] * 8

    use_mask = 0
    home_mask = 0
    for i in range(8):
        if not bool(uses[i]):
            continue
        use_mask |= 1 << i
        if str(encoders[i]).lower() != "absolute":
            home_mask |= 1 << i
    return use_mask, home_mask


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
        start = {
            "bg": "#27AE60", "fg": "white",
            "bd": "white" if crs == 1 else "#1E8449",
            "bw": 2 if crs == 1 else 1,
        }
        pause = ({
            "bg": "#E67E22", "fg": "white",
            "bd": "white" if crs == 2 else "#A04000",
            "bw": 2 if crs == 2 else 1,
        } if crs in (1, 2) else {
            "bg": "#34495E", "fg": "#BBBBBB", "bd": "#555555", "bw": 1,
        })
        return [start, pause]

    def _info_title(self):
        lm = LanguageManager.instance() if LanguageManager else None
        return lm.get_text("info_title") if lm else "생산 정보"

    def _info_rows(self):
        defaults = self._p._info
        rows = []
        store = self._p.variable_store
        existing_ids = set(store.data_ids())
        for index, config in enumerate(self._p.info_config):
            data_id = int(config.get("data_id", -1))
            if data_id >= 0 and data_id in existing_ids:
                value_text = str(store.get_data(data_id))
                source = store.data_name(data_id)
            else:
                plc_source = int(config.get("plc_source", -1))
                if 0 <= plc_source < 4:
                    value = defaults[plc_source]
                    unit = _DEFAULT_INFO_CONFIG[plc_source][1]
                    value_text = (f"{float(value):.1f} {unit}" if plc_source >= 2
                                  else f"{int(value)} {unit}")
                    source = "PLC 기본값"
                else:
                    value_text = "-"
                    source = "데이터 미선택"
            rows.append({
                "name": str(config.get("name", f"운전정보 {index + 1}")),
                "val": value_text,
                "source": source,
            })
        return rows

    def _editing_name(self):
        index = self._p._editing_info_index
        return (str(self._p.info_config[index].get("name", ""))
                if 0 <= index < len(self._p.info_config) else "")

    def _editing_data_id(self):
        index = self._p._editing_info_index
        return (int(self._p.info_config[index].get("data_id", -1))
                if 0 <= index < len(self._p.info_config) else -1)

    def _editing_has_plc_default(self):
        index = self._p._editing_info_index
        return bool(
            0 <= index < len(self._p.info_config)
            and 0 <= int(self._p.info_config[index].get("plc_source", -1)) < 4
        )

    def _data_cards(self):
        store = self._p.variable_store
        cards = []
        for item in store.data_definitions():
            item_id = int(item["id"])
            cards.append({
                "id": item_id,
                "name": str(item["name"]),
                "value": str(store.get_data(item_id)),
                "source": (f"DT{512 + item_id * 2}~{513 + item_id * 2}"
                           if item.get("plc_publish", False) else "팬던트 내부"),
            })
        return cards

    def _home_text(self):
        return "원점복귀완료" if self._p._home_done else "원점복귀"

    def _home_done_v(self):
        return self._p._home_done

    def _home_blocked(self):
        # 자동운전/확인운전 중에는 원점복귀 차단(자동·확인 버튼과 동일 가드)
        return self._p.current_mode in (1, 2)

    def _home_visible(self):
        return bool(self._p._home_required_mask)

    speedLevel = Property(int, _speed, notify=changed)
    speedColor = Property(str, _speed_color, notify=changed)
    btnStates = Property(list, _btn_states, notify=changed)
    subVisible = Property(bool, _sub_visible, notify=changed)
    subStates = Property(list, _sub_states, notify=changed)
    infoTitle = Property(str, _info_title, notify=changed)
    infoRows = Property(list, _info_rows, notify=changed)
    infoCount = Property(int, lambda s: len(s._p.info_config), notify=changed)
    canAddInfo = Property(bool, lambda s: len(s._p.info_config) < 6, notify=changed)
    editingInfoName = Property(str, _editing_name, notify=changed)
    editingInfoDataId = Property(int, _editing_data_id, notify=changed)
    editingInfoHasPlcDefault = Property(bool, _editing_has_plc_default, notify=changed)
    infoDataCards = Property(list, _data_cards, notify=changed)
    homeText = Property(str, _home_text, notify=changed)
    homeDone = Property(bool, _home_done_v, notify=changed)
    homeBlocked = Property(bool, _home_blocked, notify=changed)
    homeVisible = Property(bool, _home_visible, notify=changed)

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

    @Slot(int)
    def beginInfoEdit(self, index):
        if not self._p.info_config:
            return
        self._p._editing_info_index = max(
            0, min(len(self._p.info_config) - 1, int(index)),
        )
        self.changed.emit()

    @Slot(result=bool)
    def addInfo(self):
        return self._p._add_info_row()

    @Slot()
    def deleteInfo(self):
        self._p._delete_info_row()

    @Slot()
    def renameInfo(self):
        self._p._rename_info_row()

    @Slot(int)
    def selectInfoData(self, item_id):
        self._p._set_info_data(int(item_id))

    @Slot()
    def clearInfoData(self):
        self._p._set_info_data(-1)


class PageAutoQml(QObject):
    sig_speed_changed = Signal(int)
    sig_info_config_changed = Signal()

    def __init__(self, plc_client=None, speed_state=None, local_runtime=None,
                 overlay=None, info_config=None, variable_store=None):
        super().__init__()
        self.plc_client = plc_client
        self.local_runtime = local_runtime
        self.qml_overlay = overlay
        self._active = False
        self.current_mode = 0
        self._prev_op_status = 0
        self._check_run_state = 0
        self._info = (0, 0, 0.0, 0.0)
        self.info_config = info_config if info_config is not None else default_auto_info_config()
        self.info_config[:] = normalize_auto_info_config(self.info_config)
        self.variable_store = variable_store or VariableStore.instance()
        self._editing_info_index = 0
        self._axis_home_bits = 0
        self._axis_use_mask = 0xFF
        self._home_required_mask = 0xFF
        self._home_done = False
        self.speed_state = speed_state if speed_state is not None else {"speed_level": 10}
        self.speed_level = int(self.speed_state.get("speed_level", 10))

        self._axis = AxisModel(self)
        mgr = IOManager.instance() if IOManager else None
        self._io_in = IoModel(
            [mgr.display_label(True, i) for i in range(mgr.point_count(True))]
            if mgr else [f"X{v:02X}" for v in range(0x00, 0x20)], self,
        )
        self._io_out = IoModel(
            [mgr.display_label(False, i) for i in range(mgr.point_count(False))]
            if mgr else [f"Y{v:02X}" for v in range(0x00, 0x20)], self,
        )
        self._io_be = IoBackend(self)
        self._be = AutoBackend(self)

        self._apply_io_names()

        if self.plc_client:
            # PLCSequenceRuntime already merges raw PLC monitoring with the
            # pendant executor state.  Listening to both streams here made
            # START/PAUSE render alternately from two different authorities.
            if not self.local_runtime:
                self.plc_client.sig_monitor_data.connect(self._on_monitor_data)
            self.plc_client.sig_connected.connect(self._refresh_axis_visibility)
        if self.local_runtime:
            self.local_runtime.sig_monitor_data.connect(self._on_monitor_data)
        if IOManager:
            IOManager.instance().sig_names_changed.connect(self._apply_io_names)
        if LanguageManager:
            LanguageManager.instance().sig_lang_changed.connect(self.update_language)
        self.variable_store.valuesChanged.connect(self._on_variable_values)
        self.variable_store.definitionsChanged.connect(self._on_variable_definitions)
        self._refresh_axis_visibility()

    def _on_variable_values(self):
        if self._active:
            self._be.changed.emit()

    def _on_variable_definitions(self):
        self._be.changed.emit()

    def _rename_info_row(self):
        if self.qml_overlay is None or not self.info_config:
            return
        index = self._editing_info_index
        current = str(self.info_config[index].get("name", ""))

        def renamed(accepted, value):
            name = str(value).strip() if accepted else ""
            if not name:
                return
            self.info_config[index]["name"] = name
            self._be.changed.emit()
            self.sig_info_config_changed.emit()

        self.qml_overlay.request_text("운전정보 명칭 변경", current, callback=renamed)

    def _set_info_data(self, item_id):
        if not self.info_config:
            return
        index = self._editing_info_index
        item_id = int(item_id)
        if item_id >= 0 and item_id not in self.variable_store.data_ids():
            return
        self.info_config[index]["data_id"] = item_id
        self._be.changed.emit()
        self.sig_info_config_changed.emit()

    def _add_info_row(self):
        if len(self.info_config) >= 6:
            if self.qml_overlay:
                self.qml_overlay.show_message(
                    "운전정보 추가", "운전정보는 최대 6개까지 추가할 수 있습니다.",
                )
            return False
        self.info_config.append({
            "name": f"운전정보 {len(self.info_config) + 1}",
            "data_id": -1,
            "plc_source": -1,
        })
        self._editing_info_index = len(self.info_config) - 1
        self._be.changed.emit()
        self.sig_info_config_changed.emit()
        return True

    def _delete_info_row(self):
        if self.qml_overlay is None or not self.info_config:
            return
        index = self._editing_info_index
        name = str(self.info_config[index].get("name", "운전정보"))

        def confirmed(accepted):
            if not accepted:
                return
            self.info_config.pop(index)
            self._editing_info_index = min(index, len(self.info_config) - 1)
            self._be.changed.emit()
            self.sig_info_config_changed.emit()

        self.qml_overlay.request_confirm(
            "운전정보 삭제", f"'{name}' 항목을 삭제하시겠습니까?", callback=confirmed,
        )

    def refresh_info_config(self):
        self.info_config[:] = normalize_auto_info_config(self.info_config)
        self._be.changed.emit()

    def _apply_io_names(self):
        if not IOManager:
            return
        mgr = IOManager.instance()
        self._io_in.reset_labels([
            mgr.display_label(True, i) for i in range(mgr.point_count(True))
        ])
        self._io_out.reset_labels([
            mgr.display_label(False, i) for i in range(mgr.point_count(False))
        ])

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
            self.plc_client.submit(self.plc_client.send_speed_override, self.speed_level)
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
            self.plc_client.submit(self.plc_client.send_speed_override, self.speed_level)

    def _send_mode(self, mode):
        if self.local_runtime:
            self.local_runtime.start_mode(mode)
            return
        if self.plc_client:
            self.plc_client.submit(
                self.plc_client.send_control_command, mode, priority=0,
            )

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
                if hasattr(self.local_runtime, "start_check"):
                    self.local_runtime.start_check()
                else:
                    self.local_runtime.resume()
            else:
                self.local_runtime.pause()
            return
        if self.plc_client:
            self.plc_client.submit(
                self.plc_client.send_check_run_command, state, priority=0,
            )

    def _show_home_required(self):
        self.qml_overlay.show_message("원점복귀 필요", "원점복귀를 먼저 완료해주세요.")

    def _can_start_run(self):
        if self.current_mode in (1, 2):
            return False
        if self._home_required_mask and not self._home_done:
            self._show_home_required()
            return False
        if self.local_runtime:
            return self.local_runtime.is_connected
        return bool(self.plc_client and self.plc_client.is_connected)

    def _on_auto_clicked(self):
        if not self._can_start_run():
            return
        def accepted(ok):
            if not ok: return
            self._send_mode(1)
            try:
                from utils.op_history import record as op_record
                op_record("RUN", "자동 운전 시작")
            except Exception:
                pass
        self.qml_overlay.request_confirm("자동 운전", "자동 운전을 시작하시겠습니까?", callback=accepted)

    def _on_check_clicked(self):
        if not self._can_start_run():
            return
        def accepted(ok):
            if not ok: return
            self._send_mode(2)
            try:
                from utils.op_history import record as op_record
                op_record("RUN", "확인 운전 모드 선택")
            except Exception:
                pass
        self.qml_overlay.request_confirm(
            "확인 운전", "확인 운전 모드로 전환하시겠습니까?\nSTART를 눌러야 동작을 시작합니다.",
            callback=accepted,
        )

    def _on_home_clicked(self):
        # 원점복귀는 DT300 명령 메일박스(command=11)로만 전달한다.
        # 자동운전/확인운전 중에는 차단(자동·확인 버튼과 동일 가드).
        if self.current_mode in (1, 2):
            return
        if not self.plc_client or not self.plc_client.is_connected:
            return
        def accepted(ok):
            if not ok: return
            try:
                if self.local_runtime and hasattr(self.local_runtime, "home"):
                    self.local_runtime.home()
                else:
                    raise RuntimeError("원점복귀 명령 백엔드가 없습니다.")
            except Exception as e:
                print(f"[Auto] 원점복귀 명령 실패: {e}")
                return
            self._home_done = False
            self._be.changed.emit()
            try:
                from utils.op_history import record as op_record
                op_record("RUN", "원점복귀 명령(메일박스 command=11)")
            except Exception:
                pass
        self.qml_overlay.request_confirm("원점복귀", "원점복귀를 하시겠습니까?", callback=accepted)

    def _on_monitor_data(self, data):
        if 'axis_home_bits' in data:
            self._axis_home_bits = int(data['axis_home_bits']) & 0xFF
            home_done = not self._home_required_mask or (
                self._axis_home_bits & self._home_required_mask
            ) == self._home_required_mask
        else:
            home_done = bool(data.get('home_done', self._home_done))
        if home_done != self._home_done:
            self._home_done = home_done
        mode = data.get('op_status', self.current_mode)
        if self._prev_op_status == 2 and mode == 0:
            self._send_check_state(0)
        self._prev_op_status = mode

        if not self._active:
            return
        if 'inputs' in data:
            self._io_in.update_from_words(data['inputs'])
        if 'outputs' in data:
            self._io_out.update_from_words(data['outputs'])
        if 'axis_pos' in data:
            self._axis.set_values(data['axis_pos'])

        self.current_mode = mode
        self._check_run_state = data.get('check_run_status', 0)
        self._info = (
            data.get('production_count', data.get('stack_count', data.get('total_count', 0))),
            data.get('target_count', data.get('setting_count', 0)),
            data.get('takeout_cycle_time', data.get('takeout_time', 0.0)),
            data.get('molding_cycle_time', data.get('mold_time', 0.0)),
        )
        self._be.changed.emit()

    def _refresh_axis_visibility(self):
        try:
            from utils.paths import get_settings_path
            from utils.json_utils import load_json
            settings = load_json(get_settings_path()) or {}
            mask, home_mask = _axis_config_masks(settings)
            self._axis_use_mask = mask
            self._home_required_mask = home_mask
            self._axis.set_visibility(mask)
            home_done = not self._home_required_mask or (
                self._axis_home_bits & self._home_required_mask
            ) == self._home_required_mask
            if home_done != self._home_done:
                self._home_done = home_done
            self._be.changed.emit()
        except Exception as e:
            print(f"Axis Config Load Error: {e}")

    def activate(self):
        self._active = True
        QTimer.singleShot(0, self._refresh_axis_visibility)

    def deactivate(self):
        self._active = False

    def update_language(self, lang_code=None):
        self._io_be.refresh_titles()
        self._apply_io_names()
        self._be.changed.emit()
