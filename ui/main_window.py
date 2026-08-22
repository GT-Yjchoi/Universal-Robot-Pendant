import copy
import json
import os
import sys
import threading
from datetime import datetime
from utils.paths import get_settings_path, get_recipes_dir
from utils.json_utils import load_json, save_json
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, 
    QStackedWidget, QSizePolicy
)

from widgets.nav_button import NavButton
from ui.top_bar import TopBar

# 페이지들 임포트
from ui.pages.page_mode_qml import PageModeQml
from ui.pages.page_position_qml import PagePositionQml
from ui.pages.page_timer_qml import PageTimerQml
from ui.pages.page_packing import PagePacking
from ui.pages.page_data_qml import PageDataQml
from ui.dialogs.sequence_editor_dialog import MONITOR_SEQ_KEY, normalize_all_sequences
from ui.pages.page_manual_qml import PageManualQml
from ui.pages.page_auto_qml import PageAutoQml
from ui.pages.page_settings_qml import PageSettingsQml

# [조그 오버레이 임포트]
from ui.dialogs.jog_control_dialog import JogControlDialog

# ★ [추가] 알람 오버레이 임포트
from ui.overlays.alarm_overlay import AlarmOverlay, STEP_ALARM_DESCRIPTIONS, USER_ALARMS
from ui.overlays.alarm_history_overlay import AlarmHistoryOverlay
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
        self.recipes_dir = get_recipes_dir()

        # 메인 레이아웃
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 10)
        root.setSpacing(12)

        # ===== 1. Top Bar =====
        self.top_bar = TopBar()
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
        self.stack = QStackedWidget()
        self.stack.setMinimumHeight(0)
        root.addWidget(self.stack, 1)

        self.pages = {}
        self.page_keys = ["manual", "auto", "mode", "position", "timer", "packing", "data", "settings"]

        self.pages["manual"] = PageManualQml(plc_client=self.plc_client)
        self.pages["auto"] = PageAutoQml(plc_client=self.plc_client, speed_state=self.master_speed_state)
        
        self.pages["mode"] = PageModeQml(mode_data=self.master_mode_data, plc_client=self.plc_client)
        
        self.pages["position"] = PagePositionQml(
            sequence_data=self.master_sequence_data,
            view_order_data=self.master_view_order,
            position_points=self.master_position_points,
            mode_data=self.master_mode_data,
            timer_library=self.master_timer_library,
            plc_client=self.plc_client
        )

        self.pages["timer"] = PageTimerQml(
            sequence_data=self.master_sequence_data,
            timer_library=self.master_timer_library,
            plc_client=self.plc_client
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

        self.pages["packing"] = PagePacking(
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

        # ===== 4. Bottom Bar =====
        bottom = QFrame()
        bottom.setObjectName("BottomBar")
        bottom.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bottom.setMinimumHeight(70)
        
        b_lay = QHBoxLayout(bottom)
        b_lay.setContentsMargins(14, 4, 14, 4)
        b_lay.setSpacing(10)

        self.nav_buttons = {}

        def add_nav(page_key: str, text_key: str, index: int):
            initial_text = text_key
            if LanguageManager:
                initial_text = LanguageManager.instance().get_text(text_key)
                
            btn = NavButton(initial_text)
            btn.clicked.connect(lambda: self.goto_page(page_key, index))
            btn.setProperty("text_key", text_key)
            
            self.nav_buttons[page_key] = btn
            b_lay.addWidget(btn)

        add_nav("manual",   "nav_manual", 0)
        add_nav("auto",     "nav_auto",   1)
        add_nav("mode",     "nav_mode",   2)
        add_nav("position", "nav_pos",    3)
        add_nav("timer",    "nav_timer",  4)
        add_nav("packing",  "nav_packing",5)
        add_nav("data",     "nav_data",   6)
        add_nav("settings", "nav_setting",7)

        root.addWidget(bottom)
        self.goto_page("manual", 0)

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
        self.alarm_overlay = AlarmOverlay(self) # MainWindow(self)가 부모
        self.alarm_overlay.resize(self.size()) # 초기 크기 맞춤

        # 리셋 버튼 신호 연결 (모멘터리: 누를때 1, 뗄때 0)
        self.alarm_overlay.sig_reset_pressed.connect(self._on_alarm_reset_pressed)
        self.alarm_overlay.sig_reset_released.connect(self._on_alarm_reset_released)
        
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
        if self._gpio_estop:
            self._gpio_estop.stop()
        super().closeEvent(event)

    def _try_auto_connect(self):
        """설정 파일에서 IP/Port를 읽어와 자동 연결 시도"""
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
        self.plc_client.send_mode_settings(self.master_mode_data)
        self.plc_client.send_speed_override(self.master_speed_state.get("speed_level", 10))
        self.plc_client.send_packing_config(self.master_packing_config)
        print(f"[Sync] PLC 연결 후 모드/전체속도/패킹설정 전송 완료")

        # 무거운 항목: 백그라운드에서 전송 (수초 소요)
        threading.Thread(target=self._send_full_recipe_to_plc, daemon=True).start()

    def _send_packing_config_to_plc(self):
        """패킹 설정 변경 시 PLC 로 전송 (sig_packing_changed 슬롯)"""
        if not self.plc_client or not self.plc_client.is_connected:
            return
        self.plc_client.send_packing_config(self.master_packing_config)

    def _send_full_recipe_to_plc(self):
        """포인트 테이블 + 시퀀스 40슬롯 전체를 PLC 로 송신 (백그라운드 스레드 호출).
        sequence_editor_dialog._send_all_sequences_to_plc 와 동일한 인코딩 규칙."""
        if not self.plc_client or not self.plc_client.is_connected:
            return
        try:
            points = self.master_position_points
            sequences = self.master_sequence_data

            # ★ 옛/누락 필드 보정 (편집기에서 미클릭 스텝도 정확히 송신되도록)
            timer_lib = getattr(self, "master_timer_library", None)
            normalize_all_sequences(sequences, timer_lib)

            sorted_p_names = sorted(points.keys())
            point_map = {name: i for i, name in enumerate(sorted_p_names)}

            seq_map = {"Main": 0, MONITOR_SEQ_KEY: 39}
            reserved = set(seq_map.keys())
            sub = sorted([k for k in sequences.keys() if k not in reserved])
            for i, k in enumerate(sub):
                seq_map[k] = i + 1

            ok_seq = True
            for seq_name, slot_id in seq_map.items():
                raw_steps = sequences.get(seq_name, [])
                if not isinstance(raw_steps, list):
                    continue

                # COMMENT 제외 인덱스 재매핑 (JMP target 재계산용)
                plc_idx_map = {}
                plc_idx = 0
                for orig_idx, step in enumerate(raw_steps):
                    if step.get("type") != "COMMENT":
                        plc_idx_map[orig_idx] = plc_idx
                        plc_idx += 1

                plc_steps = []
                for orig_idx, step in enumerate(raw_steps):
                    if step.get("type") == "COMMENT":
                        continue
                    s_data = copy.deepcopy(step)
                    if s_data.get("type") == "POS":
                        s_data["point_index"] = point_map.get(s_data.get("point_name"), 0)
                    elif s_data.get("type") == "CALL":
                        s_data["sequence_id"] = seq_map.get(s_data.get("target_seq"), 0)
                    elif s_data.get("type") == "JMP":
                        s_data["target_step"] = plc_idx_map.get(s_data.get("target_idx", 0), 0)
                    plc_steps.append(s_data)

                if not self.plc_client.send_sequence_to_slot(slot_id, plc_steps):
                    ok_seq = False

            ok_pts = self.plc_client.send_all_points(points, sorted_p_names)

            if ok_seq and ok_pts:
                print("[Sync] 포인트·시퀀스 전체 재전송 완료")
            else:
                print(f"[Sync] ⚠ 일부 전송 실패 (seq_ok={ok_seq}, pts_ok={ok_pts})")
        except Exception as e:
            print(f"[Sync] 전체 레시피 전송 중 예외: {e}")

    # 조그 오버레이 실행 함수
    def _open_jog_overlay(self):
        if self.top_bar.op_status in (1, 2):
            return  # 자동운전 / 확인운전 중에는 JOG 차단
        page_manual = self.pages.get("manual")
        self._jog_dialog = JogControlDialog(plc_client=self.plc_client, page_manual=page_manual, parent=self)
        self._jog_dialog.exec()
        self._jog_dialog = None

    def goto_page(self, key: str, index: int):
        if key == "settings":
            if self.stack.currentIndex() == index:
                return
            self._request_settings_password(index)
            return
        self.stack.setCurrentIndex(index)
        for k, btn in self.nav_buttons.items():
            btn.set_active(k == key)

    def _request_settings_password(self, index: int):
        try:
            from ui.dialogs.sequence_utils import NumericKeypad, DarkMessageDialog
            dlg = NumericKeypad("설정 비밀번호를 입력하세요", decimals=0, parent=self, password_mode=True)
            if dlg.exec() == 1:
                val = int(dlg.get_value())
                if val == 2026:
                    self.stack.setCurrentIndex(index)
                    for k, btn in self.nav_buttons.items():
                        btn.set_active(k == "settings")
                else:
                    err_dlg = DarkMessageDialog("비밀번호 오류", "비밀번호가 올바르지 않습니다.", is_error=True, parent=self)
                    err_dlg.exec()
        except Exception as e:
            print(f"[Settings] Password dialog error: {e}")

    def update_language(self, lang_code):
        if not LanguageManager: return
        lm = LanguageManager.instance()
        for key, btn in self.nav_buttons.items():
            text_key = btn.property("text_key")
            if text_key:
                btn.setText(lm.get_text(text_key))
                
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
            self.plc_client.send_mode_settings(self.master_mode_data)
            self.plc_client.send_packing_config(self.master_packing_config)
            # 레시피 교체 시에도 포인트·시퀀스 전체 재전송 (백그라운드)
            threading.Thread(target=self._send_full_recipe_to_plc, daemon=True).start()
            print(f"[Mode] 레시피 '{filename}' 모드/패킹설정 전송 + 전체 재전송 시작")
        
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
            self.pages["packing"]._refresh_base_points_label()
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
            AlarmHistoryOverlay(parent=self).exec()

    def _on_alarm_reset_pressed(self):
        self._alarm_resetting = True
        self.plc_client.write_words(0x09, self.plc_client.ADDR_ALARM_RESET, [1])
        record_op("ALARM_RESET", "알람 리셋 버튼")

    def _on_alarm_reset_released(self):
        self.plc_client.write_words(0x09, self.plc_client.ADDR_ALARM_RESET, [0])
        # 사용자 알람(DT159) 클리어 및 즉시 숨김
        if getattr(self, '_user_alarm_showing', False):
            self.plc_client.write_words(0x09, self.plc_client.ADDR_USER_ALARM, [0])
            self._user_alarm_showing = False
            self._user_alarm_no = 0
            self.alarm_overlay.hide_user_alarm()
        QTimer.singleShot(500, self._clear_alarm_reset_flag)

    def _clear_alarm_reset_flag(self):
        self._alarm_resetting = False

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
            self.plc_client.write_words(0x09, self.plc_client.ADDR_USER_ALARM, [0])
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

