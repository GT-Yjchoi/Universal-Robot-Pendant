import os, json
from PySide6.QtCore import Qt, Signal, QEventLoop
from utils.paths import get_settings_path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFrame, QGridLayout, QLabel, QButtonGroup, QScrollArea, QScroller
)

class JogControlDialog(QWidget):
    sig_jog_event = Signal(str, bool)
    _last_speed = 1  # 마지막 선택 속도 기억 (클래스 변수)

    def __init__(self, plc_client=None, page_manual=None, parent=None):
        super().__init__(parent)
        self.plc_client = plc_client
        self.page_manual = page_manual

        _W, _H = 280, 760  # 패널 크기

        if parent:
            main_window = parent.window()
            self.setParent(main_window)
            # 전체화면 대신 패널 크기만큼만 → 나머지 영역 터치 통과
            self.setFixedSize(_W, _H)
            # 오른쪽 상단에 배치
            x = main_window.width() - _W - 5
            y = (main_window.height() - _H) // 2
            self.move(x, y)

        self.setAttribute(Qt.WA_AcceptTouchEvents, True)

        self._event_loop = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame()
        self.container.setFixedSize(_W, _H)
        self.container.setStyleSheet("""
            QFrame { background-color: #080c15; border: 2px solid #00E5FF; border-radius: 15px; }
            QPushButton { background-color: rgba(255, 255, 255, 0.05); border: 2px solid #005f73; border-radius: 8px; color: white; font-size: 14px; font-weight: bold; font-family: 'Malgun Gothic', sans-serif; }
            QPushButton:pressed { background-color: rgba(0, 229, 255, 0.3); border: 2px solid #00E5FF; color: #00E5FF; }
            QLabel { color: #00E5FF; font-weight: bold; font-size: 18px; background-color: transparent; border: none; }
            QPushButton#btnClose { background-color: transparent; border: none; color: #888; font-size: 30px; font-weight: 900; }
            QPushButton#btnClose:pressed { color: #FF4646; border: none; background-color: transparent; }
        """)
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(15, 10, 15, 15)
        layout.setSpacing(5) 

        # 1. 헤더
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(QLabel("JOG CONTROL"))
        header_layout.addStretch(1)
        btn_close = QPushButton("X")
        btn_close.setObjectName("btnClose")
        btn_close.setFixedSize(53, 53)
        btn_close.clicked.connect(self.close_overlay)
        header_layout.addWidget(btn_close)
        layout.addLayout(header_layout)
        
        line = QLabel(); line.setFixedHeight(2); line.setStyleSheet("background-color: #00E5FF;"); layout.addWidget(line)
        layout.addSpacing(10)

        # 2. 축 조그 버튼 — 위에서부터 1축~4축 (X / Y / Z / A).
        #    각 행 [축− , 축+]. 라벨→DT205 비트 매핑은 _on_jog 에서만 하며
        #    PLC write_bit 호출(영역 0x09 / 주소 205 / 모멘터리)은 기존과
        #    한 글자도 다르지 않음(verbatim). 런너암/제품암 전환 제거.
        axis_grid = QGridLayout()
        axis_grid.setSpacing(8)
        self._axis_btns = {}
        for row, ax in enumerate(("X", "Y", "Z", "A")):
            b_neg = self._create_btn(f"{ax} -", h=56)
            b_pos = self._create_btn(f"{ax} +", h=56)
            axis_grid.addWidget(b_neg, row, 0)
            axis_grid.addWidget(b_pos, row, 1)
            self._axis_btns[f"{ax} -"] = b_neg
            self._axis_btns[f"{ax} +"] = b_pos
        layout.addLayout(axis_grid)
        layout.addSpacing(10)
        
        # ---------------------------------------------------------
        # 속도 조절 섹션 (1~5단)
        # ---------------------------------------------------------
        layout.addSpacing(5)
        lbl_speed = QLabel("JOG SPEED (DT211)")
        lbl_speed.setStyleSheet("color: #AAA; font-size: 12px; margin-bottom: 5px;")
        lbl_speed.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_speed)

        speed_layout = QHBoxLayout()
        speed_layout.setSpacing(5)
        
        self.speed_group = QButtonGroup(self)
        self.speed_group.setExclusive(True)
        self.speed_btns = []

        for i in range(1, 6):
            btn = QPushButton(str(i))
            btn.setCheckable(True)
            btn.setFixedSize(40, 40)
            btn.setStyleSheet(self._get_speed_btn_style(False))
            btn.clicked.connect(lambda checked, val=i: self._set_speed(val))
            
            self.speed_group.addButton(btn, i)
            speed_layout.addWidget(btn)
            self.speed_btns.append(btn)

        layout.addLayout(speed_layout)
        layout.addSpacing(10)

        # (런너암/제품암 전환 버튼 제거 — 1~4축 평면 배치로 대체)

        # 4. 하단 밸브 버튼 (settings.json jog_valve=True 항목, 최대 10개)
        self._valve_btns = []
        self._valve_configs = []
        jog_valves = self._load_jog_valves()

        if jog_valves:
            lbl_valve = QLabel("VALVE")
            lbl_valve.setStyleSheet("color: #AAA; font-size: 12px; margin-bottom: 2px;")
            lbl_valve.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl_valve)

            valve_grid = QGridLayout()
            valve_grid.setSpacing(6)
            for idx, cfg in enumerate(jog_valves):
                btn = self._create_valve_btn(cfg)
                self._valve_btns.append(btn)
                self._valve_configs.append(cfg)
                valve_grid.addWidget(btn, idx // 2, idx % 2)
            layout.addLayout(valve_grid)

        layout.addStretch(1)
        main_layout.addWidget(self.container)

        self._set_speed(JogControlDialog._last_speed)

        # [NEW] 실시간 출력 상태로 토글 밸브 버튼 동기화 (valve_tile.ValvePanel 과 동일 방식)
        self._monitor_connected = False
        if self.plc_client and self._valve_btns:
            self.plc_client.sig_monitor_data.connect(self._on_monitor_data)
            self._monitor_connected = True

    def _load_jog_valves(self):
        """settings.json에서 jog_valve=True인 밸브를 jog_order 순으로 최대 10개 반환"""
        try:
            path = get_settings_path()
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    s = json.load(f)
                cfgs = s.get("valve_config", [])
                result = [c for c in cfgs if c.get("jog_valve", False)]
                result.sort(key=lambda x: x.get("jog_order", 99))
                return result[:10]
        except Exception as e:
            print(f"[JOG] valve config load error: {e}")
        return []

    def _valve_dt_addr(self, bit_index):
        """bit_index → (DT주소, 비트위치)"""
        if bit_index < 16:
            return 203, bit_index
        else:
            return 204, bit_index - 16

    def _create_valve_btn(self, cfg):
        """JOG 팝업용 밸브 버튼 생성"""
        name = cfg.get("name", "밸브")
        mode = cfg.get("mode", "toggle")
        bit_index = cfg.get("index", 0)

        btn = QPushButton(name)
        btn.setMinimumHeight(52)
        btn.setProperty("bit_index", bit_index)
        btn.setProperty("valve_mode", mode)

        if mode == "toggle":
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, bi=bit_index: self._on_valve_toggle(bi, checked))
        else:
            btn.pressed.connect(lambda bi=bit_index: self._on_valve_press(bi))
            btn.released.connect(lambda bi=bit_index: self._on_valve_release(bi))

        btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,0.05);
                border: 2px solid #005f73;
                border-radius: 8px;
                color: white;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: rgba(255,120,0,0.7);
                border: 2px solid #FF9900;
                color: white;
            }
            QPushButton:pressed {
                background-color: rgba(0,229,255,0.2);
                border: 2px solid #00E5FF;
            }
        """)
        return btn

    def _on_valve_toggle(self, bit_index, checked):
        if not self.plc_client or not self.plc_client.is_connected:
            return
        try:
            dt_addr, bit_pos = self._valve_dt_addr(bit_index)
            data = self.plc_client.read_words(0x09, dt_addr, 1)
            if data:
                val = data[0] | (1 << bit_pos) if checked else data[0] & ~(1 << bit_pos)
                self.plc_client.write_words(0x09, dt_addr, [val & 0xFFFF])
                self._log_valve_op(bit_index, "ON" if checked else "OFF")
        except Exception as e:
            print(f"[JOG Valve] toggle error: {e}")

    def _log_valve_op(self, bit_index, state):
        try:
            from utils.op_history import record as op_record
            name = None
            for cfg in self._valve_configs:
                if cfg.get("index") == bit_index:
                    name = cfg.get("name")
                    break
            label = name or f"밸브 #{bit_index}"
            op_record("VALVE", f"(JOG) {label} {state}")
        except Exception: pass

    def _on_valve_press(self, bit_index):
        if not self.plc_client or not self.plc_client.is_connected:
            return
        try:
            dt_addr, bit_pos = self._valve_dt_addr(bit_index)
            data = self.plc_client.read_words(0x09, dt_addr, 1)
            if data:
                self.plc_client.write_words(0x09, dt_addr, [(data[0] | (1 << bit_pos)) & 0xFFFF])
        except Exception as e:
            print(f"[JOG Valve] press error: {e}")

    def _on_valve_release(self, bit_index):
        if not self.plc_client or not self.plc_client.is_connected:
            return
        try:
            dt_addr, bit_pos = self._valve_dt_addr(bit_index)
            data = self.plc_client.read_words(0x09, dt_addr, 1)
            if data:
                self.plc_client.write_words(0x09, dt_addr, [(data[0] & ~(1 << bit_pos)) & 0xFFFF])
        except Exception as e:
            print(f"[JOG Valve] release error: {e}")

    # ==========================================================
    # [NEW] 실시간 출력 상태 → 토글 밸브 버튼 동기화
    # bit_index 0~15  → outputs[0] (DT144=Y00~Y0F) bit 0~15
    # bit_index 16~31 → outputs[2] (DT146=Y20~Y2F) bit 0~15
    # 모멘터리 버튼은 건드리지 않음 (사용자가 누르는 중일 수 있음)
    # ==========================================================
    def _on_monitor_data(self, data):
        if not isinstance(data, dict) or not self.isVisible():
            return
        outputs = data.get('outputs', [])
        if not outputs or len(outputs) < 3:
            return
        for btn in self._valve_btns:
            if btn.property("valve_mode") != "toggle":
                continue
            bit_index = btn.property("bit_index")
            if bit_index is None:
                continue
            if bit_index < 16:
                word_idx, bit_pos = 0, bit_index
            else:
                word_idx, bit_pos = 2, bit_index - 16
            if word_idx >= len(outputs):
                continue
            is_on = bool(outputs[word_idx] & (1 << bit_pos))
            if btn.isChecked() != is_on:
                btn.blockSignals(True)
                btn.setChecked(is_on)
                btn.blockSignals(False)

    def _create_btn(self, text, size=None, h=55):
        btn = QPushButton(text)
        if size: btn.setFixedSize(size[0], size[1])
        else: btn.setMinimumHeight(h)
        btn.setAttribute(Qt.WA_AcceptTouchEvents, True)
        btn.pressed.connect(lambda t=text: self._on_jog(t, True))
        btn.released.connect(lambda t=text: self._on_jog(t, False))
        return btn

    def _get_speed_btn_style(self, active):
        if active:
            return """
                QPushButton { 
                    background-color: rgba(0, 229, 255, 0.2); 
                    border: 2px solid #00E5FF; 
                    color: #00E5FF; 
                    border-radius: 5px; 
                    font-weight: bold; font-size: 16px;
                }
            """
        else:
            return """
                QPushButton { 
                    background-color: rgba(255, 255, 255, 0.05); 
                    border: 1px solid #444; 
                    color: #888; 
                    border-radius: 5px; 
                    font-weight: bold; font-size: 16px;
                }
                QPushButton:hover { border: 1px solid #666; color: #AAA; }
            """

    def _set_speed(self, val):
        JogControlDialog._last_speed = val
        for btn in self.speed_btns:
            if btn.text() == str(val):
                btn.setChecked(True)
                btn.setStyleSheet(self._get_speed_btn_style(True))
            else:
                btn.setChecked(False)
                btn.setStyleSheet(self._get_speed_btn_style(False))
        
        if self.plc_client and self.plc_client.is_connected:
            try:
                self.plc_client.write_words(0x09, self.plc_client.ADDR_JOG_SPEED, [val])
            except Exception as e:
                print(f"[JOG] Speed Error: {e}")

    def _on_jog(self, name, is_on):
        self.sig_jog_event.emit(name, is_on)
        if not self.plc_client or not self.plc_client.is_connected: return

        target_addr = 205
        area_code = 0x09

        # 라벨 → DT205 비트. 위에서부터 1축X / 2축Y / 3축Z / 4축A(=Y2축).
        # 사용자 확정 매핑. 비트 번호는 기존(주행±=0/1, 제품암Y=2/3,
        # 제품암Z=4/5, 런너암Y=6/7)을 그대로 계승 — write_bit 호출 verbatim.
        bit_pos = {
            "X +": 0, "X -": 1,
            "Y +": 2, "Y -": 3,
            "Z +": 4, "Z -": 5,
            "A +": 6, "A -": 7,
        }.get(name, -1)

        if bit_pos >= 0:
            try:
                self.plc_client.write_bit(area_code, target_addr, bit_pos, is_on)
            except Exception as e:
                print(f"[JOG] Error: {e}")

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def close_overlay(self):
        # 시그널 disconnect — 반복 개방 시 슬롯 누적 방지
        if getattr(self, '_monitor_connected', False) and self.plc_client:
            try:
                self.plc_client.sig_monitor_data.disconnect(self._on_monitor_data)
            except (RuntimeError, TypeError):
                pass
            self._monitor_connected = False
        if self._event_loop: self._event_loop.quit()
        self.close(); self.deleteLater()

    def exec(self):
        self.show(); self.raise_(); self._event_loop = QEventLoop(); self._event_loop.exec()
