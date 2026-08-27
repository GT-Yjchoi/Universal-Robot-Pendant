from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QGridLayout, QPushButton, QScrollArea,
    QFrame, QScroller, QScrollerProperties, QScrollBar,
    QVBoxLayout, QLabel
)
import json
import os
from utils.paths import get_settings_path

# [스타일] 스크롤바 디자인 (터치 친화적)
SCROLLBAR_STYLE = """
    QScrollBar:vertical { border: none; background: rgba(0, 0, 0, 0.1); width: 8px; margin: 0px; border-radius: 4px; }
    QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.3); min-height: 30px; border-radius: 4px; }
    QScrollBar::handle:vertical:pressed { background: rgba(70, 140, 255, 0.6); }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""

class ValvePanel(QScrollArea):  # [변경] QWidget -> QScrollArea 상속
    def __init__(self, plc_client=None):
        super().__init__()
        
        self.plc_client = plc_client
        self.valve_buttons = []  # 밸브 버튼 리스트 (순서대로)
        self.valve_configs = []  # 밸브 설정 리스트
        self._last_config_mtime = 0  # settings.json 수정 시간 추적
        
        # 1. 스크롤 영역 기본 설정
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("background: transparent;")
        
        # 스크롤바 스타일 적용
        scrollbar = QScrollBar(Qt.Vertical)
        scrollbar.setStyleSheet(SCROLLBAR_STYLE)
        self.setVerticalScrollBar(scrollbar)

        # 2. 터치 스크롤(QScroller) 내장 구현
        QScroller.grabGesture(self.viewport(), QScroller.TouchGesture)
        QScroller.grabGesture(self.viewport(), QScroller.LeftMouseButtonGesture)
        
        scroller = QScroller.scroller(self.viewport())
        props = scroller.scrollerProperties()
        
        # [튜닝] 부드러운 스크롤감 설정
        props.setScrollMetric(QScrollerProperties.MousePressEventDelay, 0.05)
        props.setScrollMetric(QScrollerProperties.DragStartDistance, 0.005)
        props.setScrollMetric(QScrollerProperties.DecelerationFactor, 0.9)  # 관성 (높을수록 부드럽게 미끄러짐)
        props.setScrollMetric(QScrollerProperties.MaximumVelocity, 1.0)
        props.setScrollMetric(QScrollerProperties.OvershootDragResistanceFactor, 0.1)
        props.setScrollMetric(QScrollerProperties.OvershootScrollDistanceFactor, 0.1)
        
        scroller.setScrollerProperties(props)

        # 3. 내부 컨텐츠 위젯 생성
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.setWidget(self.container)

        # 4. 그리드 레이아웃
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(10)
        self.grid.setContentsMargins(5, 5, 5, 5)

        # 5. settings.json에서 밸브 설정 로드 및 UI 생성
        self._load_and_create_valves()

        # 초기 수정 시간 저장
        self._update_config_mtime()

        # [NEW] 자동/확인운전 중 밸브 수동조작 차단 오버레이
        # 반투명 배경 + 중앙 "자동 중 사용 불가" 메시지 + 마우스 이벤트 가로챔
        self._lock_overlay = QFrame(self)
        self._lock_overlay.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.55);
                border-radius: 10px;
            }
            QLabel {
                color: white;
                font-size: 18px;
                font-weight: bold;
                background: transparent;
                border: none;
            }
        """)
        _lock_lay = QVBoxLayout(self._lock_overlay)
        _lock_lay.setAlignment(Qt.AlignCenter)
        _lock_lay.setContentsMargins(12, 8, 12, 8)
        _lock_lbl = QLabel("자동 중에는\n사용할 수 없습니다")
        _lock_lbl.setAlignment(Qt.AlignCenter)
        _lock_lbl.setWordWrap(True)
        _lock_lay.addWidget(_lock_lbl)
        self._lock_overlay.hide()

        # [NEW] PLC 실시간 출력 상태로 토글 버튼 동기화 + 자동운전 감지
        if self.plc_client:
            self.plc_client.sig_monitor_data.connect(self._on_monitor_data)
    
    def showEvent(self, event):
        """페이지 표시 시 설정 변경 확인 및 자동 새로고침"""
        super().showEvent(event)
        
        # settings.json 파일이 변경되었는지 확인
        if self._check_config_changed():
            print("[ValvePanel] 설정 파일 변경 감지! 자동 새로고침...")
            self.reload_valve_config()
            self._update_config_mtime()
    
    def _check_config_changed(self):
        """settings.json 파일이 변경되었는지 확인"""
        try:
            path = get_settings_path()
            if os.path.exists(path):
                current_mtime = os.path.getmtime(path)
                return current_mtime > self._last_config_mtime
        except OSError:
            pass
        return False

    def _update_config_mtime(self):
        """settings.json 수정 시간 업데이트"""
        try:
            path = get_settings_path()
            if os.path.exists(path):
                self._last_config_mtime = os.path.getmtime(path)
        except OSError:
            pass

    def _load_and_create_valves(self):
        """settings.json에서 밸브 설정을 로드하고 버튼 생성"""
        try:
            path = get_settings_path()
            valve_config = []
            
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    valve_config = settings.get("valve_config", [])
            
            # 설정이 없으면 기본값 생성
            if not valve_config or len(valve_config) != 32:
                valve_config = self._get_default_valve_config()
            
            # order 순서대로 정렬
            valve_config.sort(key=lambda x: x.get("order", 0))
            
            # 사용 가능한 밸브만 필터링
            enabled_valves = [v for v in valve_config if v.get("enabled", True)]
            
            self.valve_configs = enabled_valves
            
            # 버튼 생성
            for i, cfg in enumerate(enabled_valves):
                btn = self._create_valve_button(cfg, i)
                self.valve_buttons.append(btn)
                
                # 2열 배치
                row = i // 2
                col = i % 2
                self.grid.addWidget(btn, row, col)
            
            # 하단 여백 (스크롤 끝부분 잘림 방지)
            self.grid.setRowStretch(self.grid.rowCount(), 1)
            
            print(f"[ValvePanel] {len(enabled_valves)}개 밸브 버튼 생성 완료")
            
        except Exception as e:
            print(f"[ValvePanel] 밸브 설정 로드 실패: {e}")
            # 에러 시 기본 버튼 생성
            self._create_default_buttons()
    
    def _create_valve_button(self, config, idx):
        """밸브 설정에 따라 버튼 생성"""
        name = config.get("name", f"밸브 {idx+1}")
        mode = config.get("mode", "toggle")
        bit_index = config.get("index", idx)
        
        btn = QPushButton(name)
        btn.setMinimumHeight(60)
        
        # 동작 모드에 따라 체크 가능 여부 설정
        if mode == "toggle":
            btn.setCheckable(True)
        else:  # momentary
            btn.setCheckable(False)
        
        # 버튼에 비트 인덱스 저장
        btn.setProperty("bit_index", bit_index)
        btn.setProperty("mode", mode)
        
        # 스타일 설정
        btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                color: #DDD; 
                font-weight: bold; 
                font-size: 14px;
            }
            QPushButton:checked {
                background-color: rgba(255, 120, 0, 0.8);
                border: 2px solid #FF9900;
                color: white;
            }
            QPushButton:pressed { 
                background-color: rgba(255, 255, 255, 0.2); 
            }
        """)
        
        # 클릭 이벤트 연결
        if mode == "toggle":
            btn.clicked.connect(lambda checked: self._on_valve_toggle(bit_index, checked))
        else:  # momentary
            btn.pressed.connect(lambda: self._on_valve_pressed(bit_index))
            btn.released.connect(lambda: self._on_valve_released(bit_index))
        
        return btn
    
    def _valve_dt_addr(self, bit_index):
        """bit_index → (DT주소, 비트위치) 반환
        Y00~Y0F (index 0~15)  → DT203, bit 0~15
        Y20~Y2F (index 16~31) → DT204, bit 0~15
        """
        if bit_index < 16:
            return 203, bit_index
        else:
            return 204, bit_index - 16

    def _on_valve_toggle(self, bit_index, checked):
        """토글 모드 밸브 클릭 (ON/OFF 전환)"""
        if self.plc_client and self.plc_client.is_connected:
            try:
                dt_addr, bit_pos = self._valve_dt_addr(bit_index)
                print(f"[ValvePanel] toggle request bit={bit_index} DT{dt_addr} bit{bit_pos} checked={checked}")
                data = self.plc_client.read_words(0x09, dt_addr, 1)
                if data and len(data) >= 1:
                    current_value = data[0]
                    if checked:
                        new_value = current_value | (1 << bit_pos)
                    else:
                        new_value = current_value & ~(1 << bit_pos)
                    result = self.plc_client.write_words(0x09, dt_addr, [new_value & 0xFFFF])
                    print(f"[ValvePanel] 밸브 {bit_index} (DT{dt_addr} bit{bit_pos}) {'ON' if checked else 'OFF'} "
                          f"{current_value:#06x}->{new_value & 0xFFFF:#06x} write={'OK' if result else 'FAIL'}")
                    self._log_valve_op(bit_index, "ON" if checked else "OFF")
                else:
                    print(f"[ValvePanel] read failed DT{dt_addr} for bit={bit_index}")
            except Exception as e:
                print(f"[ValvePanel] 밸브 제어 실패: {e}")

    def _log_valve_op(self, bit_index, state):
        """조작 이력에 밸브 조작 기록."""
        try:
            from utils.op_history import record as op_record
            name = None
            for cfg in self.valve_configs:
                if cfg.get("index") == bit_index:
                    name = cfg.get("name")
                    break
            label = name or f"밸브 #{bit_index}"
            op_record("VALVE", f"{label} {state}")
        except Exception: pass

    def _on_valve_pressed(self, bit_index):
        """모멘터리 모드 밸브 누름 (ON)"""
        if self.plc_client and self.plc_client.is_connected:
            try:
                dt_addr, bit_pos = self._valve_dt_addr(bit_index)
                data = self.plc_client.read_words(0x09, dt_addr, 1)
                if data and len(data) >= 1:
                    new_value = data[0] | (1 << bit_pos)
                    self.plc_client.write_words(0x09, dt_addr, [new_value & 0xFFFF])
                    print(f"[ValvePanel] 밸브 {bit_index} (DT{dt_addr} bit{bit_pos}) 누름 (ON)")
                    self._log_valve_op(bit_index, "모멘터리 ON")
            except Exception as e:
                print(f"[ValvePanel] 밸브 제어 실패: {e}")

    def _on_valve_released(self, bit_index):
        """모멘터리 모드 밸브 뗌 (OFF)"""
        if self.plc_client and self.plc_client.is_connected:
            try:
                dt_addr, bit_pos = self._valve_dt_addr(bit_index)
                data = self.plc_client.read_words(0x09, dt_addr, 1)
                if data and len(data) >= 1:
                    new_value = data[0] & ~(1 << bit_pos)
                    self.plc_client.write_words(0x09, dt_addr, [new_value & 0xFFFF])
                    print(f"[ValvePanel] 밸브 {bit_index} (DT{dt_addr} bit{bit_pos}) 뗌 (OFF)")
            except Exception as e:
                print(f"[ValvePanel] 밸브 제어 실패: {e}")

    # ==========================================================
    # [NEW] 실시간 출력 상태 동기화
    # ==========================================================
    def resizeEvent(self, event):
        """ValvePanel 크기 변경 시 잠금 오버레이도 함께 리사이즈."""
        super().resizeEvent(event)
        if hasattr(self, '_lock_overlay') and self._lock_overlay is not None:
            self._lock_overlay.setGeometry(0, 0, self.width(), self.height())

    def _on_monitor_data(self, data):
        """sig_monitor_data 수신 → 자동운전 감지 + 토글 버튼 상태 동기화."""
        if not isinstance(data, dict):
            return

        # [NEW] 자동/확인운전 중이면 수동조작 차단 오버레이 표시
        op_status = data.get('op_status', 0)
        in_auto = op_status in (1, 2)
        if in_auto and not self._lock_overlay.isVisible():
            self._lock_overlay.setGeometry(0, 0, self.width(), self.height())
            self._lock_overlay.show()
            self._lock_overlay.raise_()
        elif not in_auto and self._lock_overlay.isVisible():
            self._lock_overlay.hide()

        if not self.isVisible():
            return  # 숨겨진 페이지는 버튼 동기화 불필요
        outputs = data.get('outputs', [])
        if not outputs or len(outputs) < 3:
            return
        self._sync_toggle_buttons(outputs)

    def _sync_toggle_buttons(self, outputs):
        """outputs (DT144=Y00~Y0F, DT146=Y20~Y2F) 로 토글 버튼 checked 상태 갱신.
        bit_index 0~15  → outputs[0] (DT144) bit 0~15
        bit_index 16~31 → outputs[2] (DT146) bit 0~15
        모멘터리 버튼은 건드리지 않음 (사용자가 누르고 있는 중일 수 있음).
        """
        for btn in self.valve_buttons:
            if btn.property("mode") != "toggle":
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
                # 신호 차단 후 변경 - _on_valve_toggle 재호출 방지
                btn.blockSignals(True)
                btn.setChecked(is_on)
                btn.blockSignals(False)
    
    def _get_default_valve_config(self):
        """기본 밸브 설정 반환"""
        named_y0x = [
            "형개허가", "형폐허가", "에젝터 허가", "싸이클스타트",
            "컨베어출력1", "컨베어출력2", "예비1", "예비2",
            "예비 Y08", "예비 Y09", "예비 Y0A", "예비 Y0B",
            "예비 Y0C", "예비 Y0D", "예비 Y0E", "예비 Y0F",
        ]
        named_y2x = [
            "척 1 (Chuck 1)", "척 2 (Chuck 2)", "척 3 (Chuck 3)", "척 4 (Chuck 4)",
            "흡착 1 (Vac 1)", "흡착 2 (Vac 2)", "흡착 3 (Vac 3)", "흡착 4 (Vac 4)",
            "포스쳐 반전", "포스쳐 복귀", "스위블 회전", "스위블 복귀",
            "니퍼 컷팅 1", "니퍼 컷팅 2", "컨베이어 출력", "공급기 출력"
        ]

        config = []
        for i in range(32):
            name = named_y2x[i - 16] if i >= 16 else named_y0x[i]
            config.append({
                "index": i,
                "name": name,
                "mode": "toggle",
                "enabled": i >= 16,  # 기본: Y20~Y2F 활성
                "order": i
            })
        return config
    
    def reload_valve_config(self):
        """
        밸브 설정을 다시 로드하고 UI 재생성
        설정 페이지에서 저장 시 호출됨
        """
        print("[ValvePanel] 밸브 설정 새로고침 시작...")
        
        # 기존 버튼 전부 제거
        for btn in self.valve_buttons:
            btn.deleteLater()
        
        self.valve_buttons.clear()
        self.valve_configs.clear()
        
        # 그리드 레이아웃 초기화
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 다시 로드 및 생성
        self._load_and_create_valves()
        
        print("[ValvePanel] 밸브 설정 새로고침 완료!")
    
    def _create_default_buttons(self):
        """에러 시 기본 버튼 생성"""
        valve_names = [
            "척 1", "척 2", "흡착 1", "흡착 2", 
            "니퍼 1", "니퍼 2", "컨베이어", "공급기"
        ]
        
        for i, name in enumerate(valve_names):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setMinimumHeight(60)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 8px;
                    color: #DDD; font-weight: bold; font-size: 14px;
                }
                QPushButton:checked {
                    background-color: rgba(255, 120, 0, 0.8);
                    border: 2px solid #FF9900;
                    color: white;
                }
                QPushButton:pressed { background-color: rgba(255, 255, 255, 0.2); }
            """)
            
            row = i // 2
            col = i % 2
            self.grid.addWidget(btn, row, col)
            self.valve_buttons.append(btn)
        
        self.grid.setRowStretch(self.grid.rowCount(), 1)
