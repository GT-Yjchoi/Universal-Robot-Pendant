import json
import os
import sys
from datetime import datetime
from utils.paths import get_settings_path, get_recipes_dir
from utils.json_utils import load_json, save_json
from engine.qt_runtime import LocalDIORuntime, PLCSequenceRuntime
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget

from ui.qml_chrome import QmlTopBar, QmlBottomBar
from ui.qml_overlay import QmlOverlayLayer

# 페이지들 임포트
from ui.pages.page_mode_qml import PageModeQml
from ui.pages.page_position_qml import PagePositionQml
from ui.pages.page_timer_qml import PageTimerQml
from ui.pages.page_packing_qml import PagePackingQml
from ui.pages.page_data_qml import PageDataQml
from ui.pages.page_manual_qml import PageManualQml
from ui.pages.page_auto_qml import PageAutoQml
from ui.pages.page_settings_qml import PageSettingsQml

# ★ [추가] 알람 오버레이 임포트
from ui.overlays.alarm_overlay import STEP_ALARM_DESCRIPTIONS, USER_ALARMS
from utils.alarm_history import record as record_alarm
from utils.op_history import record as record_op

# 유틸리티 임포트
from drivers.plc import PLCClient

try:
    from utils.gpio_estop import GpioEstop
except ImportError:
    GpioEstop = None 

try:
    from utils.languages import LanguageManager
except ImportError:
    LanguageManager = None

try:
    from utils.io_manager import IOManager
except ImportError:
    IOManager = None

try:
    from utils.mode_manager import ModeManager
except ImportError:
    ModeManager = None


# ============================================================
# 사용자 알람 테이블 (w_UserAlarm 코드 → 제목, 메시지)
# PLC에서 w_UserAlarm(DT159) 에 아래 코드를 넣으면 해당 알람이 표시됩니다.
# 키: 알람 코드 (WORD, 1~65535)
# 값: (제목, 메시지) 튜플
# ============================================================


class MainWindow(QWidget):
    def __init__(self, plc_client=None):
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle("HMI Program - Servo Control System")
        
        # 전체 화면 모드 (main.py에서 showFullScreen() 호출)


        # [PLC 클라이언트 설정]
        if plc_client:
            self.plc_client = plc_client
        else:
            self.plc_client = PLCClient() 

        self.settings_file = get_settings_path()
        _control_settings = load_json(self.settings_file) or {}
        self.control_backend = _control_settings.get("control_backend", "plc")
        self.local_runtime = None
        self.recipes_dir = get_recipes_dir()

        # 메인 레이아웃
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 10)
        root.setSpacing(12)

        # ===== 1. Top Bar =====
        self.top_bar = QmlTopBar()
        root.addWidget(self.top_bar)

        # PLC 통신 상태를 TopBar와 연결
        self.plc_client.sig_connected.connect(self.top_bar.set_comm_status)
        self.plc_client.sig_connected.connect(self._on_plc_connected)
        self.top_bar.set_comm_status(self.plc_client.is_connected)
        
        # PLC 모니터링 데이터 연결 (TopBar 갱신용)
        self.plc_client.sig_monitor_data.connect(self.top_bar._on_monitor_data)
        
        # TopBar의 JOG 버튼 클릭 시 오버레이 실행 연결
        self.top_bar.sig_jog_clicked.connect(self._open_jog_overlay)

        # TopBar의 알람 텍스트 클릭 시 오버레이 재표시
        self.top_bar.sig_alarm_clicked.connect(self._show_alarm_overlay)

        # ===== 2. Shared Data =====
        self.master_sequence_data = {"Main": []}
        self.master_position_points = {}
        self.master_timer_library = {}
        self.master_mode_data = [False] * 40
        self.master_view_order = []
        self.master_speed_state = {"speed_level": 10}
        self.master_packing_config = {}

        self.current_recipe_name = None

        # [자동 로드]
        loaded_name = "No Data"
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    last_recipe = settings.get("last_recipe")

                    # IO 이름은 settings.json에서 로드 (레시피 무관)
                    io_data = settings.get("io_names")
                    if io_data and IOManager:
                        IOManager.instance().load_from_dict(io_data)

                    if last_recipe:
                        recipe_path = os.path.join(self.recipes_dir, f"{last_recipe}.json")
                        if os.path.exists(recipe_path):
                            with open(recipe_path, 'r', encoding='utf-8') as rf:
                                data = json.load(rf)
                                
                                seq_raw = {}
                                if isinstance(data, list):
                                    seq_raw = {"Main": data}
                                elif isinstance(data, dict):
                                    temp_seq = data.get("sequence", [])
                                    if isinstance(temp_seq, list):
                                        seq_raw = {"Main": temp_seq}
                                    elif isinstance(temp_seq, dict):
                                        seq_raw = temp_seq
                                
                                self.master_sequence_data.clear()
                                self.master_sequence_data.update(seq_raw)
                                if "Main" not in self.master_sequence_data:
                                    self.master_sequence_data["Main"] = []

                                if isinstance(data, dict):
                                    pp = data.get("position_points", {})
                                    mod = data.get("mode", [])
                                    vo = data.get("view_order", [])
                                    tl = data.get("timer_library", {})

                                    self.master_position_points.update(pp)
                                    self.master_timer_library.update(tl)
                                    self.master_mode_data[:len(mod)] = mod
                                    self.master_view_order.extend(vo)

                                    try:
                                        self.master_speed_state["speed_level"] = max(1, min(10, int(data.get("speed_level", 10))))
                                    except (TypeError, ValueError):
                                        self.master_speed_state["speed_level"] = 10

                                    pc = data.get("packing_config", {})
                                    if isinstance(pc, dict):
                                        self.master_packing_config.update(pc)

                                    user_modes = data.get("user_modes")
                                    if user_modes and ModeManager:
                                        ModeManager.instance().load_from_dict(user_modes)
                                            
                                    loaded_name = last_recipe
                                    self.current_recipe_name = last_recipe
                                    print(f"[Init] Auto-loaded recipe: {last_recipe}")
            except Exception as e:
                print(f"[Init] Load error: {e}")

        # settings.json의 point_visibility로 레시피 visible_mode 오버라이드
        self._apply_point_visibility_from_settings()

        if not self.master_sequence_data["Main"]:
             self.master_sequence_data["Main"].append(
                 {"type": "POS", "name": "원점 복귀 (Default)", "point_name": "Home", "coords": [0.0]*8, "speeds": [100]*8, "axes": [True]*8}
             )
             if "Home" not in self.master_position_points:
                 self.master_position_points["Home"] = {"coords": [0.0]*8}

        self.top_bar.set_mold_data(loaded_name)

        # ===== 3. Pages =====
        if self.control_backend == "ezi_io":
            self.local_runtime = LocalDIORuntime(
                self.master_sequence_data,
                _control_settings.get("ezi_io_ip", "192.168.0.5"),
                self,
                position_points=self.master_position_points,
            )
            self.local_runtime.sig_connected.connect(self.top_bar.set_comm_status)
            self.local_runtime.sig_monitor_data.connect(self.top_bar._on_monitor_data)
            self.local_runtime.sig_error.connect(lambda msg: print(f"[Local DIO] {msg}"))
        elif self.control_backend == "plc":
            self.local_runtime = PLCSequenceRuntime(
                self.master_sequence_data, self.plc_client, self,
                position_points=self.master_position_points,
                mode_provider=lambda index: (
                    0 <= index < len(self.master_mode_data)
                    and bool(self.master_mode_data[index])
                ),
                packing_config=self.master_packing_config,
            )
            self.local_runtime.sig_connected.connect(self.top_bar.set_comm_status)
            self.local_runtime.sig_monitor_data.connect(self.top_bar._on_monitor_data)
            self.local_runtime.sig_error.connect(lambda msg: print(f"[Pendant Executor] {msg}"))

        self.stack = QStackedWidget()
        self.stack.setMinimumHeight(0)
        root.addWidget(self.stack, 1)

        self.pages = {}
        self.page_keys = ["manual", "auto", "mode", "position", "timer", "packing", "data", "settings"]

        self.pages["manual"] = PageManualQml(plc_client=self.plc_client)
        self.pages["auto"] = PageAutoQml(
            plc_client=self.plc_client,
            speed_state=self.master_speed_state,
            local_runtime=self.local_runtime,
        )
        
        self.pages["mode"] = PageModeQml(mode_data=self.master_mode_data, plc_client=self.plc_client)
        
        self.pages["position"] = PagePositionQml(
            sequence_data=self.master_sequence_data,
            view_order_data=self.master_view_order,
            position_points=self.master_position_points,
            mode_data=self.master_mode_data,
            timer_library=self.master_timer_library,
            plc_client=self.plc_client,
            local_runtime=self.local_runtime,
        )

        self.pages["timer"] = PageTimerQml(
            sequence_data=self.master_sequence_data,
            timer_library=self.master_timer_library,
            plc_client=self.plc_client,
            local_runtime=self.local_runtime,
        )

        self.pages["data"] = PageDataQml(
            sequence_data=self.master_sequence_data,
            position_points=self.master_position_points,
            timer_library=self.master_timer_library,
            mode_data=self.master_mode_data,
            view_order_data=self.master_view_order,
            speed_state=self.master_speed_state,
            packing_config=self.master_packing_config
        )

        self.pages["packing"] = PagePackingQml(
            position_points=self.master_position_points,
            sequence_data=self.master_sequence_data,
            plc_client=self.plc_client,
            packing_config=self.master_packing_config,
        )
        self.pages["settings"] = PageSettingsQml()

        self.pages["data"].sig_file_loaded.connect(self._on_recipe_loaded)
        self.pages["position"].sig_sequence_changed.connect(self._on_sequence_updated)
        self.pages["timer"].sig_timer_changed.connect(self._auto_save_data)
        self.pages["auto"].sig_speed_changed.connect(self._auto_save_data)
        self.pages["packing"].sig_packing_changed.connect(self._auto_save_data)
        self.pages["packing"].sig_packing_changed.connect(self._send_packing_config_to_plc)

        for key in self.page_keys:
            self.stack.addWidget(self.pages[key])

        if loaded_name != "No Data":
            self.pages["data"].set_current_filename(loaded_name)

        # ===== 4. QML Bottom Bar =====
        self._nav_text_keys = ["nav_manual", "nav_auto", "nav_mode", "nav_pos",
                               "nav_timer", "nav_packing", "nav_data", "nav_setting"]
        labels = [LanguageManager.instance().get_text(k) for k in self._nav_text_keys] if LanguageManager else list(self._nav_text_keys)
        self.bottom_bar = QmlBottomBar(self.page_keys, labels, self)
        self.bottom_bar.sig_selected.connect(self.goto_page)
        root.addWidget(self.bottom_bar)
        self.goto_page("manual", 0)

        # Shared QML overlay. Popups stay in the Qt Quick scene and never enter
        # a nested QWidget event loop.
        self.qml_overlay = QmlOverlayLayer(self)

        # =========================================================
        # ★ [추가] 5. Alarm Overlay (항상 최상단)
        # =========================================================
        self.current_error_code = None
        self._alarm_resetting = False
        self._user_alarm_showing = False
        self._jog_dialog = None
        self._prev_op_status = 0
        self._user_alarm_no = 0
        self._step_alarm_id = 0
        self.alarm_overlay = self.qml_overlay
        self.alarm_overlay.resize(self.size())

        # 리셋 버튼 신호 연결 (모멘터리: 누를때 1, 뗄때 0)
        self.alarm_overlay.sig_reset_pressed.connect(self._on_alarm_reset_pressed)
        self.alarm_overlay.sig_reset_released.connect(self._on_alarm_reset_released)
        if self.local_runtime and hasattr(self.local_runtime, "sig_timeout_request"):
            self.local_runtime.sig_timeout_request.connect(self._on_pendant_timeout)
            self.local_runtime.sig_nonblocking_alarm.connect(self._on_pendant_alarm_go)
        
        # PLC 데이터 감시 연결 (알람 체크용)
        if self.plc_client:
            self.plc_client.sig_monitor_data.connect(self._check_alarm_status)
        # =========================================================

        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self._auto_save_data)
        self.auto_save_timer.start(60000) 

        if LanguageManager:
            LanguageManager.instance().sig_lang_changed.connect(self.update_language)

        if IOManager:
            IOManager.instance().sig_names_changed.connect(self._save_io_names_to_settings)
        if ModeManager:
            ModeManager.instance().sig_names_changed.connect(self._auto_save_data)

        # GPIO 비상정지 모니터
        self._gpio_estop = None
        if GpioEstop:
            self._gpio_estop = GpioEstop(self)
            self._gpio_estop.sig_estop.connect(self._on_gpio_estop)
            self._gpio_estop.start()

        QTimer.singleShot(500, self._try_auto_connect)

    def _on_gpio_estop(self, active):
        """GPIO22 비상정지 신호 → DT213 전송 + 알람 팝업"""
        self._gpio_estop_active = active
        if self.plc_client and self.plc_client.is_connected:
            self.plc_client.send_soft_estop(active)
        # GPIO 또는 DT142 bit8(=axis 9) 중 하나라도 활성이면 estop 알람 유지
        if active or getattr(self, '_plc_estop_active', False):
            self.alarm_overlay.show_estop()
        else:
            self.alarm_overlay.hide_estop()

    def closeEvent(self, event):
        """앱 종료 시 GPIO 정리"""
        if self.local_runtime:
            self.local_runtime.close()
        if self._gpio_estop:
            self._gpio_estop.stop()
        super().closeEvent(event)

    def _try_auto_connect(self):
        """설정 파일에서 IP/Port를 읽어와 자동 연결 시도"""
        if self.control_backend == "ezi_io":
            return
        if self.plc_client.is_connected:
            return

        target_ip = "192.168.0.10"
        target_port = 8501

        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    target_ip = settings.get("plc_ip", target_ip)
                    target_port = int(settings.get("plc_port", target_port))
            except Exception as e:
                print(f"[AutoConnect] Settings read error: {e}")

        print(f"[Auto Connect] Connecting to {target_ip}:{target_port}...")
        self.plc_client.connect_to_plc(target_ip, target_port)

    def _on_plc_connected(self, connected: bool):
        """PLC 연결/해제 시 처리. 수동 끊기일 때는 통신 에러 팝업 띄우지 않음."""
        if connected:
            self.alarm_overlay.hide_comm_error()
            QTimer.singleShot(200, self._send_mode_to_plc)
            self._prev_comm_err_logged = False
        else:
            manual = getattr(self.plc_client, "_manual_disconnect", False)
            if manual:
                # 사용자가 직접 연결 해제 — 팝업/로그 억제
                self.alarm_overlay.hide_comm_error()
                self._prev_comm_err_logged = False
            else:
                self.alarm_overlay.show_comm_error()
                # [NEW] 통신 오류 발생 이력 기록 (전이 시에만)
                if not getattr(self, '_prev_comm_err_logged', False):
                    record_alarm("COMM", 0, "PLC 통신 끊김")
                    self._prev_comm_err_logged = True

    def _send_mode_to_plc(self):
        """PLC 연결 후 현재 로딩된 레시피 전체를 PLC 에 동기화.
        - 빠른 항목 (mode/speed/packing config) 은 즉시 송신
        - 무거운 항목 (포인트 60개 + 시퀀스 40 슬롯) 은 **백그라운드 스레드**로 송신
          → UI 블로킹 방지"""
        if not self.plc_client or not self.plc_client.is_connected:
            return
        # 즉시 전송: 수 Words 단위라 빠름
        self.plc_client.submit(self.plc_client.send_mode_settings, list(self.master_mode_data))
        self.plc_client.submit(
            self.plc_client.send_speed_override,
            self.master_speed_state.get("speed_level", 10),
        )
        self.plc_client.submit(
            self.plc_client.send_packing_config, dict(self.master_packing_config)
        )
        print(f"[Sync] PLC 연결 후 모드/전체속도/패킹설정 전송 완료")

        # 시퀀스와 분기 데이터는 팬던트에서 실행한다. PLC에는 전체 레시피를
        # 전송하지 않으며 물리 명령 메일박스만 사용한다.

    def _send_packing_config_to_plc(self):
        """패킹 설정 변경 시 PLC 로 전송 (sig_packing_changed 슬롯)"""
        if not self.plc_client or not self.plc_client.is_connected:
            return
        self.plc_client.submit(
            self.plc_client.send_packing_config, dict(self.master_packing_config)
        )

    # 조그 오버레이 실행 함수
    def _open_jog_overlay(self):
        if self.top_bar.op_status in (1, 2):
            return  # 자동운전 / 확인운전 중에는 JOG 차단
        self._jog_dialog = self.qml_overlay
        self.qml_overlay.show_jog()

    def goto_page(self, key: str, index: int):
        if key == "settings":
            if self.stack.currentIndex() == index:
                return
            self._request_settings_password(index)
            return
        self._switch_page(index)

    def _switch_page(self, index):
        if not 0 <= index < self.stack.count():
            return
        self.stack.setCurrentIndex(index)
        self.bottom_bar.set_current(index)
        page = self.stack.widget(index)
        view = getattr(page, "_view", None)
        root = view.rootObject() if view is not None else None
        if root is None:
            return
        if getattr(self, "_page_animation", None) is not None:
            self._page_animation.stop()
        previous_root = getattr(self, "_animated_page_root", None)
        if previous_root is not None:
            previous_root.setProperty("opacity", 1.0)
        root.setProperty("opacity", 0.0)
        animation = QPropertyAnimation(root, b"opacity", self)
        animation.setDuration(140)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        self._page_animation = animation
        self._animated_page_root = root
        animation.finished.connect(lambda r=root: r.setProperty("opacity", 1.0))
        animation.start()

    def _request_settings_password(self, index: int):
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
            "설정 비밀번호를 입력하세요", 0, minimum=0, maximum=999999,
            password=True, callback=finished,
        )

    def update_language(self, lang_code):
        if not LanguageManager: return
        lm = LanguageManager.instance()
        self.bottom_bar.set_labels([lm.get_text(k) for k in self._nav_text_keys])
                
        for page in self.pages.values():
            if hasattr(page, "update_language"):
                page.update_language(lang_code)

    def _on_recipe_loaded(self, filename):
        self.current_recipe_name = filename
        self.top_bar.set_mold_data(filename)
        record_op("RECIPE", f"레시피 로드: {filename}")

        # 새 레시피 로드 후 settings.json의 point_visibility 오버라이드 적용
        self._apply_point_visibility_from_settings()

        if "mode" in self.pages:
            self.pages["mode"].refresh_ui()
        if "position" in self.pages:
            self.pages["position"]._refresh_ui()
        if "timer" in self.pages:
            self.pages["timer"].refresh_grid()
        if "auto" in self.pages:
            self.pages["auto"].refresh_speed_from_state()
        if "packing" in self.pages:
            self.pages["packing"].refresh_ui()

        if self.plc_client and self.plc_client.is_connected:
            self.plc_client.submit(
                self.plc_client.send_mode_settings, list(self.master_mode_data)
            )
            self.plc_client.submit(
                self.plc_client.send_packing_config, dict(self.master_packing_config)
            )
            print(f"[Mode] 레시피 '{filename}' 모드/패킹설정 전송")
        
        try:
            data = load_json(self.settings_file) or {}
            data["last_recipe"] = filename
            save_json(self.settings_file, data)
        except Exception as e:
            print(f"[Main] Save settings error: {e}")

    def _on_sequence_updated(self):
        if "timer" in self.pages:
            self.pages["timer"].refresh_grid()
        if "packing" in self.pages:
            self.pages["packing"].refresh_ui()
        self._save_point_visibility_to_settings()
        self._auto_save_data()

    def _auto_save_data(self):
        if "data" in self.pages:
            self.pages["data"].auto_save()

    def _apply_point_visibility_from_settings(self):
        """settings.json의 point_visibility를 master_position_points에 적용 (settings 우선)"""
        try:
            data = load_json(self.settings_file) or {}
            pv = data.get("point_visibility", {})
            for pt_name, vm in pv.items():
                if pt_name in self.master_position_points:
                    self.master_position_points[pt_name]["visible_mode"] = vm
        except Exception as e:
            print(f"[Main] point_visibility load error: {e}")

    def _save_point_visibility_to_settings(self):
        """master_position_points의 visible_mode를 settings.json에 저장"""
        try:
            data = load_json(self.settings_file) or {}
            data["point_visibility"] = {
                name: pt["visible_mode"]
                for name, pt in self.master_position_points.items()
                if "visible_mode" in pt
            }
            save_json(self.settings_file, data)
        except Exception as e:
            print(f"[Main] point_visibility save error: {e}")

    def _save_io_names_to_settings(self):
        try:
            data = load_json(self.settings_file) or {}
            data["io_names"] = IOManager.instance().to_dict() if IOManager else {}
            save_json(self.settings_file, data)
        except Exception as e:
            print(f"[Main] IO names save error: {e}")

    # ★ [추가] 창 크기 변경 이벤트 (오버레이 크기 동기화)
    def resizeEvent(self, event):
        if hasattr(self, 'alarm_overlay'):
            self.alarm_overlay.resize(self.size())
        if hasattr(self, 'qml_overlay'):
            self.qml_overlay.resize(self.size())
        super().resizeEvent(event)

    def _show_alarm_overlay(self):
        """TopBar 알람 텍스트 클릭 시:
        - 현재 알람 있음 → 기존 알람 오버레이 재표시
        - 현재 알람 없음 → 최근 30일 알람 이력 팝업 표시
        """
        if self.alarm_overlay.has_any_alarm():
            self.alarm_overlay.show()
            self.alarm_overlay.raise_()
        else:
            self.qml_overlay.show_history()

    def _on_alarm_reset_pressed(self):
        self._alarm_resetting = True
        self.plc_client.submit(
            self.plc_client.write_words, 0x09, self.plc_client.ADDR_ALARM_RESET, [1]
        )
        record_op("ALARM_RESET", "알람 리셋 버튼")

    def _on_alarm_reset_released(self):
        self.plc_client.submit(
            self.plc_client.write_words, 0x09, self.plc_client.ADDR_ALARM_RESET, [0]
        )
        # 사용자 알람(DT159) 클리어 및 즉시 숨김
        if getattr(self, '_user_alarm_showing', False):
            self.plc_client.submit(
                self.plc_client.write_words, 0x09, self.plc_client.ADDR_USER_ALARM, [0]
            )
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
            message += f"\n알람 A-{alarm_no:03d}"
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
            message += f"\n알람 A-{alarm_no:03d}"
        record_alarm("USER", int(alarm_no), message)
        self.qml_overlay.show_message("입력 타임아웃", message, error=True)

    # ★ [추가] 알람 상태 감시 함수
    def _check_alarm_status(self, data):
        op_status = data.get('op_status', 0)
        prev_op = getattr(self, '_prev_op_status', 0)

        # 자동/확인운전 시작 시 JOG 팝업 강제 종료
        if op_status in (1, 2):
            if getattr(self, '_jog_dialog', None) is not None:
                self._jog_dialog.close_overlay()

        # DT142: 축 알람 비트맵 (비트0~7=1~8축, 비트8=비상정지)
        axis_alarms = data.get('axis_alarms', [])
        axis_error_codes = data.get('axis_error_codes', [0] * 8)

        # E-STOP: DT142 bit8 또는 GPIO 중 하나라도 활성이면 유지
        estop_active = self._plc_estop_active = 9 in axis_alarms
        estop_combined = estop_active or getattr(self, '_gpio_estop_active', False)
        if estop_combined:
            self.alarm_overlay.show_estop()
        else:
            self.alarm_overlay.hide_estop()
        # [NEW] 이력 기록 - 발생 전이(False→True)만
        if estop_combined and not getattr(self, '_prev_estop_logged', False):
            record_alarm("ESTOP", 0, "비상정지 발생")
        self._prev_estop_logged = estop_combined

        # 축 알람 (9번=비상정지 제외)
        axis_only = [a for a in axis_alarms if a != 9]
        if axis_only:
            key = tuple(axis_only) + tuple(axis_error_codes)
            if self.current_error_code != key:
                self.current_error_code = key
                self.alarm_overlay.show_error(axis_only, axis_error_codes)
                # [NEW] 이력 기록 - 축별 에러코드와 함께
                axes_txt = ", ".join(f"{a}축" for a in axis_only)
                codes_txt = ", ".join(
                    f"{a}축 E-{axis_error_codes[a-1]:04X}"
                    for a in axis_only if axis_error_codes[a-1] > 0
                )
                msg = f"{axes_txt} 서보 알람" + (f" ({codes_txt})" if codes_txt else "")
                record_alarm("AXIS", axis_error_codes[axis_only[0]-1] if axis_error_codes else 0, msg)
        else:
            self.alarm_overlay.hide_axis_alarm()
            self.current_error_code = None

        # DT159: 사용자 알람 (w_UserAlarm, IN 스텝 P3=1/2 발동, 1000+ = 알람+진행)
        user_alarm = data.get('user_alarm', 0)
        if user_alarm > 0 and not self._user_alarm_showing:
            alarm_go = user_alarm >= 1000
            alarm_no = user_alarm - 1000 if alarm_go else user_alarm
            print(f"[Main] 사용자 알람 (alarm_no={alarm_no}, alarm_go={alarm_go})")
            self._user_alarm_showing = True
            self._user_alarm_no = alarm_no
            # 즉시 DT159 클리어 (핸드셰이크) → 재트리거 방지
            self.plc_client.submit(
                self.plc_client.write_words, 0x09, self.plc_client.ADDR_USER_ALARM, [0]
            )
            self.alarm_overlay.show_user_alarm(alarm_no)
            # [NEW] 이력 기록
            msg = USER_ALARMS.get(alarm_no, f"사용자 알람 #{alarm_no}")
            record_alarm("USER", alarm_no, f"A-{alarm_no:03d}: {msg}" + (" (진행)" if alarm_go else " (정지)"))

        # 사용자 알람 자동 해제: 정지 상태에서 운전 재개 시 (0 → 1/2 전이)
        if self._user_alarm_showing and op_status in (1, 2) and prev_op == 0:
            self._user_alarm_showing = False
            self._user_alarm_no = 0
            self.alarm_overlay.hide_user_alarm()

        # DT160: 스텝 알람 (i_StepAlarmID, FB 엔진 스텝 진행 에러)
        step_alarm_id = data.get('step_alarm_id', 0)
        if step_alarm_id > 0:
            if self._step_alarm_id != step_alarm_id:
                self._step_alarm_id = step_alarm_id
                print(f"[Main] 스텝 알람 (i_StepAlarmID={step_alarm_id})")
                self.alarm_overlay.show_step_alarm(step_alarm_id)
                # [NEW] 이력 기록
                desc = STEP_ALARM_DESCRIPTIONS.get(step_alarm_id, f"정의되지 않은 에러")
                record_alarm("STEP", step_alarm_id, f"E-{step_alarm_id:02d}: {desc}")
        else:
            if self._step_alarm_id != 0:
                self._step_alarm_id = 0
                self.alarm_overlay.hide_step_alarm()

        self._prev_op_status = op_status

