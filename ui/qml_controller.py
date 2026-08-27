"""Non-visual application controller for the single-scene Qt Quick UI."""

from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from drivers.plc import PLCClient
from engine.qt_runtime import LocalDIORuntime, PLCSequenceRuntime
from ui.dialogs.sequence_editor_qml import SequenceEditorSession
from ui.pages.page_auto_qml import (
    PageAutoQml, default_auto_info_config, normalize_auto_info_config,
)
from ui.pages.page_data_qml import PageDataQml
from ui.pages.page_manual_qml import PageManualQml
from ui.pages.page_mode_qml import PageModeQml
from ui.pages.page_packing_qml import PagePackingQml
from ui.pages.page_position_qml import PagePositionQml
from ui.pages.page_settings_qml import PageSettingsQml
from utils.variable_store import VariableStore
from ui.pages.page_timer_qml import PageTimerQml
from ui.qml_backends import NavBackend, TopBarBackend
from ui.qml_overlay import QmlOverlayLayer
from ui.alarm_catalog import STEP_ALARM_DESCRIPTIONS, USER_ALARMS
from utils.alarm_history import record as record_alarm
from utils.json_utils import load_json, save_json
from utils.op_history import record as record_op
from utils.paths import get_recipes_dir, get_settings_path

try:
    from utils.gpio_estop import GpioEstop
except ImportError:
    GpioEstop = None

try:
    from utils.io_manager import IOManager
except ImportError:
    IOManager = None

try:
    from utils.languages import LanguageManager
except ImportError:
    LanguageManager = None


def _format_user_alarm(alarm_no):
    alarm_no = int(alarm_no)
    if alarm_no <= 0:
        return ""
    message = USER_ALARMS.get(alarm_no, f"사용자 알람 #{alarm_no}")
    return f"A-{alarm_no:03d}: {message}"

try:
    from utils.mode_manager import ModeManager
except ImportError:
    ModeManager = None


class PendantController(QObject):
    """Owns application state; it never creates a QWidget or render surface."""

    ready = Signal()

    def __init__(self, plc_client=None, parent=None):
        super().__init__(parent)
        self.plc_client = plc_client or PLCClient()
        self.settings_file = get_settings_path()
        self.recipes_dir = get_recipes_dir()
        settings = load_json(self.settings_file) or {}
        self.control_backend = settings.get("control_backend", "plc")

        self.master_sequence_data = {"Main": []}
        self.master_position_points = {}
        self.master_timer_library = {}
        self.master_mode_data = [False] * 40
        self.master_view_order = []
        self.master_speed_state = {"speed_level": 10}
        self.master_packing_config = {}
        self.master_auto_info_config = default_auto_info_config()
        self.variable_store = VariableStore.instance()
        self.current_recipe_name = None
        loaded_name = self._load_last_recipe(settings)
        self._apply_point_visibility_from_settings()
        self._ensure_default_recipe()

        self.top_backend = TopBarBackend(self)
        self.top_bar = self.top_backend
        self.top_backend.set_connected(self.plc_client.is_connected)
        self.top_backend.set_recipe(loaded_name)
        self.top_backend.jogRequested.connect(self._open_jog_overlay)
        self.top_backend.alarmRequested.connect(self._show_alarm_overlay)
        self.plc_client.sig_connected.connect(self.top_backend.set_connected)
        self.plc_client.sig_connected.connect(self._on_plc_connected)
        self.plc_client.sig_monitor_data.connect(self.top_backend.update_monitor)

        self.qml_overlay = QmlOverlayLayer(self)
        self.alarm_overlay = self.qml_overlay
        self.sequence_editor = SequenceEditorSession(self, overlay=self.qml_overlay)

        self.local_runtime = self._build_runtime(settings)
        if self.local_runtime is not None:
            self.local_runtime.sig_connected.connect(self.top_backend.set_connected)
            self.local_runtime.sig_monitor_data.connect(self.top_backend.update_monitor)
            self.local_runtime.sig_error.connect(
                lambda msg: print(f"[Pendant runtime] {msg}")
            )

        self.page_keys = [
            "manual", "auto", "mode", "position",
            "timer", "packing", "data", "settings",
        ]
        self._nav_text_keys = [
            "nav_manual", "nav_auto", "nav_mode", "nav_pos",
            "nav_timer", "nav_packing", "nav_data", "nav_setting",
        ]
        labels = self._translated_nav_labels()
        self.nav_backend = NavBackend(self.page_keys, labels, self)
        self.bottom_bar = self.nav_backend
        self.nav_backend.selected.connect(self.goto_page)

        self.pages = self._build_pages()
        self.pages["settings"].set_plc_client(self.plc_client)
        self.pages["settings"].sig_axis_config_changed.connect(
            self.pages["auto"]._refresh_axis_visibility)
        self.pages["data"].sig_file_loaded.connect(self._on_recipe_loaded)
        self.pages["position"].sig_sequence_changed.connect(self._on_sequence_updated)
        self.sequence_editor.timerLibraryChanged.connect(
            self.pages["timer"].refresh_grid)
        self.sequence_editor.variableLibraryChanged.connect(self._auto_save_data)
        self.pages["timer"].sig_timer_changed.connect(self._auto_save_data)
        self.pages["auto"].sig_speed_changed.connect(self._auto_save_data)
        self.pages["auto"].sig_info_config_changed.connect(self._auto_save_data)
        self.pages["packing"].sig_packing_changed.connect(self._auto_save_data)
        if loaded_name != "No Data":
            self.pages["data"].set_current_filename(loaded_name)

        self._current_page = -1
        self._switch_page(0)

        self.current_error_code = None
        self._alarm_resetting = False
        self._user_alarm_showing = False
        self._jog_dialog = None
        self._prev_op_status = 0
        self._user_alarm_no = 0
        self._step_alarm_id = 0
        self.alarm_overlay.sig_reset_pressed.connect(self._on_alarm_reset_pressed)
        self.alarm_overlay.sig_reset_released.connect(self._on_alarm_reset_released)
        if self.local_runtime and hasattr(self.local_runtime, "sig_timeout_request"):
            self.local_runtime.sig_timeout_request.connect(self._on_pendant_timeout)
            self.local_runtime.sig_nonblocking_alarm.connect(self._on_pendant_alarm_go)
        self.plc_client.sig_monitor_data.connect(self._check_alarm_status)

        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.setInterval(60000)
        self.auto_save_timer.timeout.connect(self._auto_save_data)
        self.auto_save_timer.start()

        if LanguageManager:
            LanguageManager.instance().sig_lang_changed.connect(self.update_language)
        if IOManager:
            IOManager.instance().sig_names_changed.connect(
                self._save_io_names_to_settings
            )
        if ModeManager:
            ModeManager.instance().sig_names_changed.connect(self._auto_save_data)

        self._gpio_estop = None
        if GpioEstop:
            self._gpio_estop = GpioEstop(self)
            self._gpio_estop.sig_estop.connect(self._on_gpio_estop)
            self._gpio_estop.start()

        QTimer.singleShot(500, self._try_auto_connect)
        QTimer.singleShot(0, self.ready.emit)

    def _load_last_recipe(self, settings):
        loaded_name = "No Data"
        io_data = settings.get("io_names")
        if io_data and IOManager:
            IOManager.instance().load_from_dict(io_data)
        last_recipe = settings.get("last_recipe")
        if not last_recipe:
            self.variable_store.load_from_dict({}, self.master_sequence_data)
            return loaded_name
        recipe_path = os.path.join(self.recipes_dir, f"{last_recipe}.json")
        if not os.path.exists(recipe_path):
            self.variable_store.load_from_dict({}, self.master_sequence_data)
            return loaded_name
        try:
            with open(recipe_path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            if isinstance(data, list):
                sequences = {"Main": data}
            else:
                raw = data.get("sequence", [])
                sequences = {"Main": raw} if isinstance(raw, list) else dict(raw)
            self.master_sequence_data.update(sequences)
            self.master_sequence_data.setdefault("Main", [])
            if isinstance(data, dict):
                self.master_position_points.update(data.get("position_points", {}))
                self.master_timer_library.update(data.get("timer_library", {}))
                mode = list(data.get("mode", []))
                self.master_mode_data[:len(mode)] = mode[:40]
                self.master_view_order.extend(data.get("view_order", []))
                self.master_speed_state["speed_level"] = max(
                    1, min(10, int(data.get("speed_level", 10)))
                )
                packing = data.get("packing_config", {})
                if isinstance(packing, dict):
                    self.master_packing_config.update(packing)
                self.master_auto_info_config[:] = normalize_auto_info_config(
                    data.get("auto_info_config"),
                )
                user_modes = data.get("user_modes")
                if user_modes and ModeManager:
                    ModeManager.instance().load_from_dict(user_modes)
                self.variable_store.load_from_dict(
                    data.get("variable_library", {}), self.master_sequence_data,
                )
            else:
                self.variable_store.load_from_dict({}, self.master_sequence_data)
            self.current_recipe_name = last_recipe
            print(f"[Init] Auto-loaded recipe: {last_recipe}")
            return last_recipe
        except Exception as exc:
            print(f"[Init] Load error: {exc}")
            return loaded_name

    def _ensure_default_recipe(self):
        if self.master_sequence_data.get("Main"):
            return
        self.master_sequence_data["Main"] = [{
            "type": "POS", "name": "원점 복귀 (Default)",
            "point_name": "Home", "coords": [0.0] * 8,
            "speeds": [100] * 8, "axes": [True] * 8,
        }]
        self.master_position_points.setdefault("Home", {"coords": [0.0] * 8})

    def _build_runtime(self, settings):
        if self.control_backend == "ezi_io":
            return LocalDIORuntime(
                self.master_sequence_data,
                settings.get("ezi_io_ip", "192.168.0.5"), self,
                position_points=self.master_position_points,
                variable_store=self.variable_store,
                alarm_provider=lambda: self.alarm_overlay.has_any_alarm(),
            )
        if self.control_backend == "plc":
            return PLCSequenceRuntime(
                self.master_sequence_data, self.plc_client, self,
                position_points=self.master_position_points,
                mode_provider=lambda index: (
                    0 <= index < len(self.master_mode_data)
                    and bool(self.master_mode_data[index])
                ),
                packing_config=self.master_packing_config,
                variable_store=self.variable_store,
                alarm_provider=lambda: self.alarm_overlay.has_any_alarm(),
            )
        return None

    def _build_pages(self):
        overlay = self.qml_overlay
        return {
            "manual": PageManualQml(self.plc_client, overlay),
            "auto": PageAutoQml(
                self.plc_client, self.master_speed_state,
                self.local_runtime, overlay,
                info_config=self.master_auto_info_config,
                variable_store=self.variable_store,
            ),
            "mode": PageModeQml(
                self.master_mode_data, self.plc_client, overlay,
            ),
            "position": PagePositionQml(
                sequence_data=self.master_sequence_data,
                view_order_data=self.master_view_order,
                position_points=self.master_position_points,
                mode_data=self.master_mode_data,
                timer_library=self.master_timer_library,
                plc_client=self.plc_client,
                local_runtime=self.local_runtime,
                overlay=overlay,
                sequence_editor=self.sequence_editor,
            ),
            "timer": PageTimerQml(
                self.master_sequence_data, self.master_timer_library,
                self.plc_client, self.local_runtime, overlay,
            ),
            "packing": PagePackingQml(
                self.master_position_points, self.master_sequence_data,
                self.plc_client, self.master_packing_config, overlay,
            ),
            "data": PageDataQml(
                self.master_sequence_data, self.master_position_points,
                self.master_timer_library, self.master_mode_data,
                self.master_view_order, self.master_speed_state,
                self.master_packing_config, overlay,
                variable_store=self.variable_store,
                auto_info_config=self.master_auto_info_config,
            ),
            "settings": PageSettingsQml(overlay),
        }

    def context_properties(self):
        manual = self.pages["manual"]
        auto = self.pages["auto"]
        mode = self.pages["mode"]
        position = self.pages["position"]
        timer = self.pages["timer"]
        packing = self.pages["packing"]
        data = self.pages["data"]
        settings = self.pages["settings"]
        return {
            "appBackend": self,
            "topBackend": self.top_backend,
            "navBackend": self.nav_backend,
            "overlayBackend": self.qml_overlay.backend,
            "sequenceSession": self.sequence_editor,
            "manualAxisModel": manual._axis,
            "manualIoInModel": manual._io_in,
            "manualIoOutModel": manual._io_out,
            "manualValveModel": manual._valve_m,
            "manualIoBackend": manual._io_be,
            "manualValveBackend": manual._valve_be,
            "autoAxisModel": auto._axis,
            "autoIoInModel": auto._io_in,
            "autoIoOutModel": auto._io_out,
            "autoIoBackend": auto._io_be,
            "autoPageBackend": auto._be,
            "modePageModel": mode._model,
            "modeBackend": mode._backend,
            "positionAxisModel": position._axis,
            "positionPreviewModel": position._prev,
            "positionValveModel": position._valve_m,
            "positionValveBackend": position._valve_be,
            "positionBackend": position._be,
            "timerPageModel": timer._model,
            "timerPageBackend": timer._be,
            "packingPageBackend": packing._backend,
            "dataFileModel": data._file_model,
            "dataPreviewModel": data._prev_model,
            "dataPageBackend": data._be,
            "settingsIoModel": settings._io_model,
            "settingsParamModel": settings._param_model,
            "settingsValveModel": settings._valve_model,
            "settingsAlarmModel": settings._alarm_model,
            "settingsWifiModel": settings._wifi_model,
            "settingsIlModeModel": settings._il_mode_model,
            "settingsIlGroupModel": settings._il_grp_model,
            "settingsPageBackend": settings._be,
        }

    def _translated_nav_labels(self):
        if not LanguageManager:
            return list(self._nav_text_keys)
        lm = LanguageManager.instance()
        return [lm.get_text(key) for key in self._nav_text_keys]

    @Slot(str, int)
    def goto_page(self, key, index):
        if key == "settings":
            if self._current_page == index:
                return
            self._request_settings_password(index)
            return
        self._switch_page(index)

    def _switch_page(self, index):
        if not 0 <= int(index) < len(self.page_keys):
            return
        index = int(index)
        if self._current_page == index:
            return
        if 0 <= self._current_page < len(self.page_keys):
            page = self.pages[self.page_keys[self._current_page]]
            if hasattr(page, "deactivate"):
                page.deactivate()
        self._current_page = index
        self.nav_backend.set_current(index)
        page = self.pages[self.page_keys[index]]
        if hasattr(page, "activate"):
            page.activate()

    def _request_settings_password(self, index):
        def finished(accepted, value):
            if not accepted:
                return
            if int(value) == 2026:
                self._switch_page(index)
            else:
                self.qml_overlay.show_message(
                    "비밀번호 오류", "비밀번호가 올바르지 않습니다.", error=True,
                )
        self.qml_overlay.request_number(
            "설정 비밀번호를 입력하세요", 0, minimum=0,
            maximum=999999, password=True, callback=finished,
        )

    @Slot(str)
    def update_language(self, lang_code=""):
        self.nav_backend.set_labels(self._translated_nav_labels())
        for page in self.pages.values():
            if hasattr(page, "update_language"):
                page.update_language(lang_code)

    def _try_auto_connect(self):
        if self.control_backend == "ezi_io" or self.plc_client.is_connected:
            return
        settings = load_json(self.settings_file) or {}
        ip = settings.get("plc_ip", "192.168.0.10")
        port = int(settings.get("plc_port", 8501))
        print(f"[Auto Connect] Connecting to {ip}:{port}...")
        self.plc_client.connect_to_plc(ip, port)

    def _on_plc_connected(self, connected):
        if connected:
            self.alarm_overlay.hide_comm_error()
            QTimer.singleShot(200, self._send_mode_to_plc)
            self._prev_comm_err_logged = False
            return
        if getattr(self.plc_client, "_manual_disconnect", False):
            self.alarm_overlay.hide_comm_error()
            self._prev_comm_err_logged = False
        else:
            self.alarm_overlay.show_comm_error()
            if not getattr(self, "_prev_comm_err_logged", False):
                record_alarm("COMM", 0, "PLC 통신 끊김")
                self._prev_comm_err_logged = True

    def _send_mode_to_plc(self):
        if not self.plc_client.is_connected:
            return
        self.plc_client.submit(
            self.plc_client.send_speed_override,
            self.master_speed_state.get("speed_level", 10),
        )

    def _open_jog_overlay(self):
        if self.top_backend.op_status in (1, 2):
            return
        self._jog_dialog = self.qml_overlay
        self.qml_overlay.show_jog()

    def _show_alarm_overlay(self):
        if not self.alarm_overlay.has_any_alarm():
            self.qml_overlay.show_history()

    def _on_recipe_loaded(self, filename):
        self.current_recipe_name = filename
        self.top_backend.set_recipe(filename)
        record_op("RECIPE", f"레시피 로드: {filename}")
        self._apply_point_visibility_from_settings()
        self.pages["mode"].refresh_ui()
        self.pages["position"]._refresh_ui()
        self.pages["timer"].refresh_grid()
        self.pages["auto"].refresh_speed_from_state()
        self.pages["auto"].refresh_info_config()
        self.pages["packing"].refresh_ui()
        data = load_json(self.settings_file) or {}
        data["last_recipe"] = filename
        save_json(self.settings_file, data)

    def _on_sequence_updated(self):
        self.pages["timer"].refresh_grid()
        self.pages["packing"].refresh_ui()
        self._save_point_visibility_to_settings()
        self._auto_save_data()

    def _auto_save_data(self, *_args):
        if hasattr(self, "pages"):
            self.pages["data"].auto_save()

    def _apply_point_visibility_from_settings(self):
        try:
            visibility = (load_json(self.settings_file) or {}).get(
                "point_visibility", {}
            )
            for name, mode in visibility.items():
                if name in self.master_position_points:
                    self.master_position_points[name]["visible_mode"] = mode
        except Exception as exc:
            print(f"[Main] point_visibility load error: {exc}")

    def _save_point_visibility_to_settings(self):
        data = load_json(self.settings_file) or {}
        data["point_visibility"] = {
            name: point["visible_mode"]
            for name, point in self.master_position_points.items()
            if "visible_mode" in point
        }
        save_json(self.settings_file, data)

    def _save_io_names_to_settings(self):
        data = load_json(self.settings_file) or {}
        data["io_names"] = IOManager.instance().to_dict() if IOManager else {}
        save_json(self.settings_file, data)

    def _on_gpio_estop(self, active):
        self._gpio_estop_active = bool(active)
        if self.plc_client.is_connected:
            self.plc_client.submit(
                self.plc_client.send_axis_stop, bool(active), priority=-100,
            )
        if active or getattr(self, "_plc_estop_active", False):
            self.alarm_overlay.show_estop()
        else:
            self.alarm_overlay.hide_estop()

    def _on_alarm_reset_pressed(self):
        self._alarm_resetting = True
        if self.local_runtime and hasattr(self.local_runtime, "reset"):
            self.local_runtime.reset()
        record_op("ALARM_RESET", "알람 리셋 버튼")

    def _on_alarm_reset_released(self):
        if self._user_alarm_showing:
            self._user_alarm_showing = False
            self._user_alarm_no = 0
            self.alarm_overlay.hide_user_alarm()
        QTimer.singleShot(500, self._clear_alarm_reset_flag)

    def _clear_alarm_reset_flag(self):
        self._alarm_resetting = False

    def _on_pendant_timeout(self, request):
        queue = getattr(self, "_pending_timeout_requests", None)
        if queue is None:
            self._pending_timeout_requests = []
            self._active_timeout_request = None
            queue = self._pending_timeout_requests
        queue.append(request)
        self._show_next_pendant_timeout()

    def _show_next_pendant_timeout(self):
        if (getattr(self, "_active_timeout_request", None) is not None
                or not getattr(self, "_pending_timeout_requests", [])):
            return
        request = self._pending_timeout_requests.pop(0)
        self._active_timeout_request = request
        step = request.step
        alarm_no = int(step.get("timeout_alarm_no", 0))
        name = step.get("name", f"입력 {step.get('port', 0)}")
        message = (
            f"'{name}' 입력 대기시간이 초과되었습니다.\n"
            "이 프로그램만 현재 IN 스텝에서 대기 중이며,\n"
            "다른 병렬 프로그램과 Monitor는 계속 실행됩니다."
        )
        if alarm_no:
            message += f"\n{_format_user_alarm(alarm_no)}"
        record_alarm("USER", alarm_no, message)
        self.qml_overlay.request_confirm(
            "입력 타임아웃 · 진행여부 선택", message,
            accept_text="리셋", reject_text="정지",
            callback=lambda reset: self._finish_pendant_timeout(request, reset),
        )

    def _finish_pendant_timeout(self, request, reset):
        if getattr(self, "_active_timeout_request", None) is request:
            self._active_timeout_request = None
        request.resolve(bool(reset))
        if not reset:
            for pending in getattr(self, "_pending_timeout_requests", []):
                pending.resolve(False)
            self._pending_timeout_requests = []
            return
        QTimer.singleShot(0, self._show_next_pendant_timeout)

    def _on_pendant_alarm_go(self, alarm_no, name):
        message = f"'{name}' 입력 타임아웃 후 다음 스텝을 진행합니다."
        if alarm_no:
            message += f"\n{_format_user_alarm(alarm_no)}"
        record_alarm("USER", int(alarm_no), message)
        # 알람 후 진행도 단순 오류 메시지가 아니라 실제 사용자 알람으로
        # 등록해야 Monitor의 JMP(알람발생)와 상단 알람 상태가 일치한다.
        self._user_alarm_showing = True
        self._user_alarm_no = int(alarm_no)
        self.alarm_overlay.show_user_alarm(int(alarm_no))

    def _check_alarm_status(self, data):
        op_status = int(data.get("op_status", self._prev_op_status))
        prev_op = self._prev_op_status
        if op_status in (1, 2) and self._jog_dialog is not None:
            self._jog_dialog.close_overlay()

        axis_alarms = list(data.get("axis_alarms", []))
        error_codes = list(data.get("axis_error_codes", [0] * 8))
        estop = self._plc_estop_active = 9 in axis_alarms
        combined = estop or getattr(self, "_gpio_estop_active", False)
        if combined:
            self.alarm_overlay.show_estop()
        else:
            self.alarm_overlay.hide_estop()
        if combined and not getattr(self, "_prev_estop_logged", False):
            record_alarm("ESTOP", 0, "비상정지 발생")
        self._prev_estop_logged = combined

        axis_only = [axis for axis in axis_alarms if axis != 9]
        if axis_only:
            key = tuple(axis_only) + tuple(error_codes)
            if key != self.current_error_code:
                self.current_error_code = key
                self.alarm_overlay.show_error(axis_only, error_codes)
                record_alarm("AXIS", error_codes[axis_only[0] - 1], "축 서보 알람")
        else:
            self.current_error_code = None
            self.alarm_overlay.hide_axis_alarm()

        if self._user_alarm_showing and op_status in (1, 2) and prev_op == 0:
            self._user_alarm_showing = False
            self._user_alarm_no = 0
            self.alarm_overlay.hide_user_alarm()

        step_alarm = int(data.get("step_alarm_id", 0))
        if step_alarm and step_alarm != self._step_alarm_id:
            self._step_alarm_id = step_alarm
            self.alarm_overlay.show_step_alarm(step_alarm)
            record_alarm(
                "STEP", step_alarm,
                STEP_ALARM_DESCRIPTIONS.get(step_alarm, "정의되지 않은 에러"),
            )
        elif not step_alarm and self._step_alarm_id:
            self._step_alarm_id = 0
            self.alarm_overlay.hide_step_alarm()
        self._prev_op_status = op_status

    @Slot()
    def shutdown(self):
        self.auto_save_timer.stop()
        for page in self.pages.values():
            if hasattr(page, "deactivate"):
                page.deactivate()
        if self.local_runtime:
            self.local_runtime.close()
        if self._gpio_estop:
            self._gpio_estop.stop()
        self.plc_client.disconnect_plc()
