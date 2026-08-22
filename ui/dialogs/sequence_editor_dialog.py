import copy
import traceback
import os
import json
from PySide6.QtCore import Qt, QPoint, QTimer
from utils.paths import get_settings_path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QListWidget, QListWidgetItem, QStackedWidget,
    QTabWidget, QApplication, QMessageBox, QScroller, QScrollerProperties
)
from PySide6.QtGui import QScreen, QColor

try:
    from ui.widgets.custom_inputs import ClickableLineEdit, TouchComboBox
    from ui.dialogs.sequence_step_ui import StepUIGenerator, VALVE_LIST, INTERNAL_BIT_COUNT
except ImportError as e:
    print(f"!!! [CRITICAL ERROR] StepUIGenerator Import Failed: {e}")
    traceback.print_exc()
    from PySide6.QtWidgets import QLineEdit as ClickableLineEdit, QComboBox as TouchComboBox
    StepUIGenerator = None


def normalize_step(step, timer_library=None):
    """레거시/누락 필드 보정 (in-place). 클릭 여부와 무관하게 송신 직전에 적용.
    _load_data_to_ui 안에서 클릭 시 일어나던 변환과 동일.
    - POS: 'axes' → 'active_axes' (8개로 패딩)
    - IN : 'in_type' 누락 시 port 값으로 추론
    - TMR: timer_ref 가 라이브러리에 있으면 'time' 동기화
    - OUT: delay_enable 이고 delay_timer_ref 가 라이브러리에 있으면 'delay_time' 동기화
    """
    t = step.get("type")
    if t == "POS":
        axes = step.get("active_axes", step.get("axes"))
        if not isinstance(axes, list):
            axes = [False] * 8
        if len(axes) < 8:
            axes = list(axes) + [False] * (8 - len(axes))
        step["active_axes"] = axes
    elif t == "IN":
        if "in_type" not in step:
            p = step.get("port", 0)
            if   p >= 200: step["in_type"] = 3
            elif p >= 100: step["in_type"] = 2
            elif p >= 32:  step["in_type"] = 1
            else:          step["in_type"] = 0
    elif t == "TMR":
        ref = step.get("timer_ref", "")
        if ref and timer_library and ref in timer_library:
            step["time"] = float(timer_library[ref])
    elif t == "OUT":
        if step.get("delay_enable", False):
            ref = step.get("delay_timer_ref", "")
            if ref and timer_library and ref in timer_library:
                step["delay_time"] = float(timer_library[ref])


def normalize_all_sequences(sequences, timer_library=None):
    """sequences dict (slot_name → [step,...]) 내 전 스텝을 정규화."""
    if not isinstance(sequences, dict):
        return
    for steps in sequences.values():
        if not isinstance(steps, list):
            continue
        for step in steps:
            if isinstance(step, dict):
                normalize_step(step, timer_library)

try:
    from ui.dialogs.sequence_utils import (
        DarkConfirmDialog, RenameDialog, NumericKeypad, NewPointDialog,
        DarkMessageDialog, SequenceListDialog, PopupListSelector, PointListDialog,
        CardListDialog
    )
except ImportError:
    print("!!! [CRITICAL] sequence_utils Import Failed")
    DarkConfirmDialog = None
    RenameDialog = None
    NumericKeypad = None
    NewPointDialog = None
    DarkMessageDialog = None
    SequenceListDialog = None
    PopupListSelector = None
    PointListDialog = None
    CardListDialog = None

try:
    from utils.io_manager import IOManager
except ImportError:
    IOManager = None

try:
    from widgets.touch_keyboard import TouchKeyboard
except ImportError:
    TouchKeyboard = None

# 슬롯 39 고정 예약 - 자동운전 중 상태감시/알람용
MONITOR_SEQ_KEY = "Monitor"

class TouchScrollListWidget(QListWidget):
    """드래그로 스크롤되는 리스트 위젯 (터치스크린 대응)"""
    SCROLL_THRESHOLD = 15  # 손가락 떨림 허용: 15px 이상 이동 시 스크롤 모드
    DOUBLE_TAP_MS    = 400 # 더블탭 판정 시간 (ms)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._press_pos = None
        self._is_scrolling = False
        self._pressed_item = None
        self._last_tap_item = None
        self._double_tap_timer = QTimer(self)
        self._double_tap_timer.setSingleShot(True)
        self._double_tap_timer.timeout.connect(self._commit_single_tap)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        # 저사양 ARM 보드 스크롤 경량화: 행이 전부 균일 높이(QSS 42px, 순수 텍스트)
        # 라 행별 sizeHint/지오메트리 재계산을 생략하고 고정 stride 페인트 경로 사용.
        # 외형·선택·로직·PLC 거동 불변, CPU 래스터 부하만 감소.
        self.setUniformItemSizes(True)

    def mousePressEvent(self, event):
        self._press_pos = event.pos()
        self._is_scrolling = False
        item = self.itemAt(event.pos())
        self._pressed_item = item

        if item is None:
            self._double_tap_timer.stop()
            self._last_tap_item = None
            return

        if self._double_tap_timer.isActive() and item is self._last_tap_item:
            # 더블탭: 타이머 취소 후 더블클릭 신호 발생
            self._double_tap_timer.stop()
            self._last_tap_item = None
            self.itemDoubleClicked.emit(item)
        else:
            # 첫 번째 탭: 즉시 선택 (딜레이 없음) + 더블탭 감지 타이머 시작
            self.setCurrentItem(item)
            self.itemClicked.emit(item)
            self._last_tap_item = item
            self._double_tap_timer.start(self.DOUBLE_TAP_MS)

    def _commit_single_tap(self):
        """더블탭 시간 초과 — 아무것도 안 함 (이미 첫 탭에서 선택 완료)"""
        self._last_tap_item = None

    def mouseMoveEvent(self, event):
        if self._press_pos is not None:
            dy = event.pos().y() - self._press_pos.y()
            if not self._is_scrolling and abs(dy) > self.SCROLL_THRESHOLD:
                self._is_scrolling = True
                self._double_tap_timer.stop()
                self._last_tap_item = None
                self.clearSelection()
            if self._is_scrolling:
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() - dy
                )
                self._press_pos = event.pos()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        self._is_scrolling = False
        self._pressed_item = None


class SequenceEditorDialog(QDialog):
    def __init__(self, sequence_data=None, position_points=None, timer_library=None, plc_client=None, mode_data=None, parent=None):
        super().__init__(parent)
        self.setObjectName("SequenceEditor")
        self.setWindowTitle("시퀀스 편집")
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setWindowState(Qt.WindowFullScreen)

        self.plc_client = plc_client
        self._is_loading = False

        # ★ settings.json에서 연결된 축 정보 로드
        self.enabled_axes = self._load_enabled_axes()
        print(f"[시퀀스 편집기] 연결된 축: {self.enabled_axes}")

        self.timer_library = timer_library if timer_library is not None else {}
        self.mode_data = mode_data if mode_data is not None else []

        self.points_library = {}
        if position_points:
            for k, v in position_points.items():
                if k:
                    self.points_library[k] = {
                        "coords": list(v.get("coords", [0.0]*8)),
                        "speeds": list(v.get("speeds", [100.0]*8)),
                        "visible_mode": v.get("visible_mode", []),
                    }
        
        self.sequences = {}
        if isinstance(sequence_data, list): self.sequences["Main"] = copy.deepcopy(sequence_data)
        elif isinstance(sequence_data, dict): self.sequences = copy.deepcopy(sequence_data)
        else: self.sequences["Main"] = []
        if "Main" not in self.sequences: self.sequences["Main"] = []
            
        self.current_seq_key = "Main"
        if "Main" in self.sequences: self.current_seq_key = "Main"
        else: self.current_seq_key = list(self.sequences.keys())[0]

        self.active_step_data = None 

        self._apply_dark_theme()
        self._init_ui()
        self._scan_all_points()
        
        self._update_sequence_info() 
        self._load_step_list_from_memory()

    def showEvent(self, event):
        super().showEvent(event)
        # linuxfb 등 일부 플랫폼에서 setWindowState(FullScreen) 만으론
        # 부모 윈도우 크기로 안 커지는 경우가 있어, 부모 기하로 명시 강제.
        parent = self.parent()
        if parent is not None:
            main_window = parent.window() if hasattr(parent, 'window') else parent
            if main_window is not None:
                self.setGeometry(main_window.geometry())
        self.activateWindow()
        self.raise_()
        self.setFocus()

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QDialog#SequenceEditor { background-color: #0f161e; border: 2px solid #468CFF; }
            QWidget { color: #ffffff; font-family: 'Malgun Gothic', sans-serif; }
            QLabel { background: transparent; color: #eeeeee; }
            QListWidget { background-color: rgba(0, 0, 0, 0.3); border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 6px; color: #dddddd; font-size: 14px; outline: none; }
            QListWidget::item { height: 42px; padding-left: 8px; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }
            QListWidget::item:selected { background-color: rgba(70, 140, 255, 0.3); border: 1px solid #468CFF; color: white; font-weight: bold; }
            QPushButton { background-color: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 4px; color: white; font-weight: bold; font-size: 13px; }
            QPushButton:pressed { background-color: rgba(255, 255, 255, 0.2); }
            QLineEdit { background-color: rgba(0, 0, 0, 0.4); border: 1px solid rgba(255, 255, 255, 0.3); border-radius: 4px; color: white; padding: 5px; font-size: 14px; }
        """)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        header = QHBoxLayout()
        lbl_title = QLabel("시퀀스 편집 (Sequence Editor)")
        lbl_title.setStyleSheet("font-size: 22px; font-weight: 900; color: #468CFF;")
        header.addWidget(lbl_title)
        header.addStretch(1)
        
        btn_cancel = QPushButton("취소 (닫기)")
        btn_cancel.setFixedSize(120, 45)
        btn_cancel.clicked.connect(self.reject)
        header.addWidget(btn_cancel)

        btn_apply = QPushButton("적용 (Apply)")
        btn_apply.setFixedSize(120, 45)
        btn_apply.setStyleSheet("border: 1px solid #00FF7F; color: #00FF7F;")
        btn_apply.clicked.connect(self._on_apply_clicked)
        header.addWidget(btn_apply)

        btn_save = QPushButton("저장 후 닫기")
        btn_save.setFixedSize(140, 45)
        btn_save.setStyleSheet("border: 1px solid #468CFF; color: white;")
        btn_save.clicked.connect(self._on_save_clicked)
        header.addWidget(btn_save)
        layout.addLayout(header)

        content = QHBoxLayout()
        left_widget = QWidget()
        left_box = QVBoxLayout(left_widget)
        
        nav_box = QHBoxLayout()
        nav_box.setSpacing(10)
        
        self.lbl_curr_seq = QLabel("Main")
        self.lbl_curr_seq.setFixedHeight(45)
        self.lbl_curr_seq.setCursor(Qt.PointingHandCursor)
        self.lbl_curr_seq.setStyleSheet("""
            QLabel {
                background: rgba(70, 140, 255, 0.1);
                border: 2px solid #468CFF;
                border-radius: 6px;
                color: #468CFF;
                font-size: 18px;
                font-weight: bold;
                padding-left: 15px;
            }
            QLabel:hover {
                background: rgba(70, 140, 255, 0.25);
            }
        """)
        self.lbl_curr_seq.mousePressEvent = lambda e: self._open_sequence_list() if len(self.sequences) > 1 else None
        nav_box.addWidget(self.lbl_curr_seq, 1)
        
        # [NEW] 이름 변경 버튼 - 현재 선택된 시퀀스 이름 변경 (Main/Monitor 는 비활성)
        self.btn_rename_seq = QPushButton("이름변경")
        self.btn_rename_seq.setFixedSize(80, 45)
        self.btn_rename_seq.setStyleSheet(
            "QPushButton { border: 1px solid #F1C40F; color: #F1C40F; font-size: 13px; font-weight: bold; border-radius: 6px; }"
            "QPushButton:pressed { background: rgba(241,196,15,0.2); }"
            "QPushButton:disabled { border: 1px solid #555; color: #555; }"
        )
        self.btn_rename_seq.clicked.connect(self._on_rename_sequence_clicked)
        nav_box.addWidget(self.btn_rename_seq)

        btn_add_seq = QPushButton("+")
        btn_add_seq.setFixedSize(45, 45)
        btn_add_seq.setStyleSheet("border: 1px solid #00E5FF; color: #00E5FF; font-size: 20px;")
        btn_add_seq.clicked.connect(self._on_add_sequence)
        nav_box.addWidget(btn_add_seq)

        self.btn_del_seq = QPushButton("삭제")
        self.btn_del_seq.setFixedSize(55, 45)
        self.btn_del_seq.setStyleSheet("border: 1px solid #FF4646; color: #FF4646; font-size: 14px; font-weight: bold;")
        self.btn_del_seq.clicked.connect(self._on_delete_sequence)
        nav_box.addWidget(self.btn_del_seq)
        
        left_box.addLayout(nav_box)
        
        # ★ 스텝 리스트 (터치 드래그 스크롤 지원)
        self.step_list = TouchScrollListWidget()
        self.step_list.itemClicked.connect(self._on_item_clicked)
        self.step_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.step_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # 스타일 설정 (큰 스크롤바)
        self.step_list.setStyleSheet("""
            QListWidget {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                color: white;
                font-size: 14px;
                outline: none;
            }
            QListWidget::item {
                padding: 5px 10px;
                height: 30px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QListWidget::item:selected {
                background: rgba(70, 140, 255, 0.4);
                border-left: 3px solid #468CFF;
            }
            QScrollBar:vertical {
                border: none;
                background: rgba(0, 0, 0, 0.2);
                width: 20px;
                margin: 0px;
                border-radius: 10px;
            }
            QScrollBar::handle:vertical {
                background: rgba(70, 140, 255, 0.6);
                min-height: 50px;
                border-radius: 10px;
                border: 2px solid rgba(255, 255, 255, 0.3);
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(70, 140, 255, 0.8);
            }
            QScrollBar::handle:vertical:pressed {
                background: rgba(70, 140, 255, 1.0);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        
        left_box.addWidget(self.step_list)
        
        add_box = QHBoxLayout()
        for cmd, col in [("POS","#468CFF"), ("OUT","#FFA500"), ("IN","#FF69B4"), ("TMR","#FFFF00"), ("JMP","#00E5FF"), ("CALL","#FF00FF"), ("DAT","#00FF9C"), ("END","#FF4646")]:
            btn = QPushButton(cmd)
            btn.setMinimumHeight(45)
            btn.setStyleSheet(f"border: 2px solid {col}; color: {col}; font-weight: bold;")
            btn.clicked.connect(lambda _, c=cmd: self._add_new_step(c))
            add_box.addWidget(btn)
        btn_comment = QPushButton("CMT")
        btn_comment.setMinimumHeight(45)
        btn_comment.setStyleSheet("border: 2px solid #FFD700; color: #FFD700; font-weight: bold;")
        btn_comment.clicked.connect(self._add_comment)
        add_box.addWidget(btn_comment)
        left_box.addLayout(add_box)
        
        edit_box = QHBoxLayout()
        for t, f in [("▲ 위로", self._move_up), ("▼ 아래로", self._move_down), ("[X] 스텝 삭제", self._delete_step)]:
            b = QPushButton(t)
            b.setMinimumHeight(45)
            b.clicked.connect(f)
            edit_box.addWidget(b)
        left_box.addLayout(edit_box)
        
        content.addWidget(left_widget, 4)
        
        right_widget = QWidget()
        right_widget.setStyleSheet("background: rgba(0,0,0,0.2); border-radius: 8px;")
        right_box = QVBoxLayout(right_widget)
        
        lbl_prop = QLabel("속성 설정")
        lbl_prop.setStyleSheet("font-size: 16px; font-weight: bold; color: #AAA;")
        right_box.addWidget(lbl_prop)
        
        self.stack = QStackedWidget()
        self.stack.addWidget(QLabel("스텝을 선택하세요"))
        
        if StepUIGenerator:
            self.stack.addWidget(StepUIGenerator.create_pos_editor(self))
            if hasattr(self, 'axis_checkboxes'):
                for i, chk in enumerate(self.axis_checkboxes):
                    if chk is None:  # ★ None 체크 추가
                        continue
                    try: chk.toggled.disconnect()
                    except RuntimeError: pass
                    chk.toggled.connect(lambda checked, idx=i: self._on_axis_checkbox_changed(idx, checked))
            if hasattr(self, 'chk_pack_base'):
                self.chk_pack_base.toggled.connect(self._on_pack_base_changed)
            if hasattr(self, 'pos_exec_grp'):
                for b in self.pos_exec_grp.buttons():
                    b.toggled.connect(self._on_pos_exec_mode_changed)

            self.stack.addWidget(StepUIGenerator.create_io_editor(self))
            # OUT/IN 라디오버튼 시그널 1회만 연결 (_load_data_to_ui에서 반복 연결 제거)
            if hasattr(self, 'out_type_grp'):
                for b in self.out_type_grp.buttons():
                    b.toggled.connect(self._on_out_type_changed)
            if hasattr(self, 'in_type_grp'):
                for b in self.in_type_grp.buttons():
                    b.toggled.connect(self._on_in_type_changed)
            self.stack.addWidget(StepUIGenerator.create_tmr_editor(self))
            self.stack.addWidget(StepUIGenerator.create_jmp_editor(self))
            self.stack.addWidget(StepUIGenerator.create_call_editor(self))
        else:
            self.stack.addWidget(QLabel("UI 로드 실패 (Import Error)"))

        # 코멘트 편집 패널 (index 6)
        comment_widget = QWidget()
        comment_widget.setStyleSheet("background: transparent;")
        comment_layout = QVBoxLayout(comment_widget)
        comment_layout.setContentsMargins(0, 0, 0, 0)
        comment_layout.setSpacing(12)
        lbl_comment_title = QLabel("// 코멘트")
        lbl_comment_title.setStyleSheet("color: #FFD700; font-size: 16px; font-weight: bold;")
        comment_layout.addWidget(lbl_comment_title)
        self.lbl_comment_text = QLabel("")
        self.lbl_comment_text.setWordWrap(True)
        self.lbl_comment_text.setStyleSheet(
            "color: #FFD700; font-size: 15px; "
            "background: rgba(255,215,0,0.08); "
            "border: 1px solid #FFD700; border-radius: 6px; padding: 10px;"
        )
        comment_layout.addWidget(self.lbl_comment_text)
        btn_edit_comment = QPushButton("코멘트 편집")
        btn_edit_comment.setMinimumHeight(45)
        btn_edit_comment.setStyleSheet("border: 1px solid #FFD700; color: #FFD700;")
        btn_edit_comment.clicked.connect(self._edit_comment_text)
        comment_layout.addWidget(btn_edit_comment)
        comment_layout.addStretch()
        self.stack.addWidget(comment_widget)

        # 데이터연산(DAT) 편집 패널 (index 7)
        if StepUIGenerator:
            self.stack.addWidget(StepUIGenerator.create_dat_editor(self))
            if hasattr(self, 'dat_op_grp'):
                for b in self.dat_op_grp.buttons():
                    b.toggled.connect(self._on_dat_op_changed)

        right_box.addWidget(self.stack)
        content.addWidget(right_widget, 6)
        
        layout.addLayout(content)

    def _scan_all_points(self):
        for seq_name, steps in self.sequences.items():
            for step_data in steps:
                if step_data.get("type") == "POS":
                    p_name = step_data.get("point_name", step_data.get("name", "Point"))
                    if not p_name: p_name = "Point_1"; step_data["point_name"] = p_name
                    if p_name not in self.points_library:
                        self.points_library[p_name] = {
                            "coords": list(step_data.get("coords", [0.0]*8)),
                            "speeds": list(step_data.get("speeds", [100.0]*8))
                        }

    # =========================================================================
    # 로직 (데이터 로딩 & 저장)
    # =========================================================================
    def _on_item_clicked(self, item):
        row = self.step_list.row(item)
        if row < 0: return
        current_list = self.sequences.get(self.current_seq_key, [])
        if row >= len(current_list): return
        self.active_step_data = current_list[row]
        self._is_loading = True
        try: self._load_data_to_ui(self.active_step_data)
        finally: self._is_loading = False 

    def _load_data_to_ui(self, data):
        # ★ [수정] edit_step_name 관련 코드 제거 (위젯이 삭제되었으므로)
        
        type_code = data.get("type", "")
        # self.edit_step_name.setText(data.get("name", "")) # <-- 삭제됨

        if type_code == "COMMENT":
            self.lbl_comment_text.setText(data.get("text", ""))
            self.stack.setCurrentIndex(6)
            return

        idx_map = {"POS": 1, "OUT": 2, "IN": 2, "TMR": 3, "JMP": 4, "CALL": 5, "DAT": 7}
        self.stack.setCurrentIndex(idx_map.get(type_code, 0))

        if type_code == "POS":
            self._refresh_point_selector()

            # 파렛타이징 베이스 체크박스 상태 로드
            if hasattr(self, 'chk_pack_base'):
                self.chk_pack_base.blockSignals(True)
                self.chk_pack_base.setChecked(bool(data.get("pack_base", False)))
                self.chk_pack_base.blockSignals(False)

            # 이행 모드 로드 (wait_completion 누락 시 True=완료 후 이행 → 기존 레시피 하위호환)
            if hasattr(self, 'pos_exec_grp'):
                wait_c = bool(data.get("wait_completion", True))
                self.rb_pos_wait.blockSignals(True)
                self.rb_pos_parallel.blockSignals(True)
                self.rb_pos_wait.setChecked(wait_c)
                self.rb_pos_parallel.setChecked(not wait_c)
                self.rb_pos_wait.blockSignals(False)
                self.rb_pos_parallel.blockSignals(False)

            # ★ active_axes로 통일 (PLC 전송과 동일한 키 사용)
            axes = data.get("active_axes", data.get("axes", [False]*8))
            if len(axes) < 8: axes += [False]*(8-len(axes))
            data["active_axes"] = axes  # active_axes로 저장
            
            p_name_key = data.get("point_name", "")
            speeds = self.points_library.get(p_name_key, {}).get("speeds", [100.0]*8)
            coords = self.points_library.get(p_name_key, {}).get("coords", [0.0]*8)
            
            for i in range(8):
                is_checked = axes[i]
                if hasattr(self, 'axis_checkboxes') and i < len(self.axis_checkboxes):
                    if self.axis_checkboxes[i] is not None:  # ★ None 체크
                        self.axis_checkboxes[i].setChecked(is_checked)
                    if self.speed_spinboxes[i] is not None:  # ★ None 체크
                        self.speed_spinboxes[i].setEnabled(True)
                        
                if hasattr(self, 'pos_labels') and i < len(self.pos_labels):
                    if self.pos_labels[i] is not None:  # ★ None 체크
                        self.pos_labels[i].setText(f"{coords[i]:.3f}")
                        
                if hasattr(self, 'speed_spinboxes') and i < len(self.speed_spinboxes):
                    if self.speed_spinboxes[i] is not None:  # ★ None 체크
                        self.speed_spinboxes[i].setText(f"{speeds[i]:.0f}")

        elif type_code in ["OUT", "IN"]:
            self._update_io_combo(type_code == "OUT")
            self.lbl_io_target.setText("제어할 출력" if type_code=="OUT" else "감시할 센서")
            bit_index = data.get("port", 0)
            self.io_combo.setCurrentIndex(bit_index)

            # ★ OUT 스텝 전용: 출력 구분 라디오 설정
            if hasattr(self, 'out_type_frame'):
                self.out_type_frame.setVisible(type_code == "OUT")
            if hasattr(self, 'in_type_frame'):
                self.in_type_frame.setVisible(type_code == "IN")
            if type_code == "OUT":
                out_type = data.get("out_type", 0)
                if hasattr(self, 'out_type_grp'):
                    btn = self.out_type_grp.button(out_type)
                    if btn: btn.setChecked(True)
            elif type_code == "IN":
                # in_type 기존 데이터 없으면 port값으로 추론
                if "in_type" not in data:
                    p = data.get("port", 0)
                    if p >= 200:
                        data["in_type"] = 3
                    elif p >= 100:
                        data["in_type"] = 2
                    elif p >= 32:
                        data["in_type"] = 1
                    else:
                        data["in_type"] = 0
                in_type = data.get("in_type", 0)
                if hasattr(self, 'in_type_grp'):
                    btn = self.in_type_grp.button(in_type)
                    if btn: btn.setChecked(True)

            # ★ 버튼 텍스트에 이름 표시
            if hasattr(self, 'io_combo_btn'):
                if type_code == "OUT":
                    self.io_combo_btn.setText(self._get_out_name(data.get("out_type", 0), bit_index))
                else:
                    input_name = self._get_input_name_by_index(bit_index)
                    self.io_combo_btn.setText(input_name)

            if data.get("on", True): self.rb_on.setChecked(True)
            else: self.rb_off.setChecked(True)

            # ★ OUT 스텝 전용: 타이머 기동후출력 설정
            if hasattr(self, 'out_delay_frame'):
                self.out_delay_frame.setVisible(type_code == "OUT")
                if type_code == "OUT":
                    delay_enable = data.get("delay_enable", False)
                    delay_timer_ref = data.get("delay_timer_ref", "")
                    # delay_timer_ref가 있으면 timer_library에서 최신값 우선 참조
                    if delay_timer_ref and self.timer_library and delay_timer_ref in self.timer_library:
                        delay_time = float(self.timer_library[delay_timer_ref])
                        data["delay_time"] = delay_time
                    else:
                        delay_time = data.get("delay_time", 1.0)
                    if hasattr(self, 'chk_out_delay'):
                        self.chk_out_delay.blockSignals(True)
                        self.chk_out_delay.setChecked(delay_enable)
                        self.chk_out_delay.blockSignals(False)
                    if hasattr(self, 'out_delay_timer_btn'):
                        self.out_delay_timer_btn.setEnabled(delay_enable)
                        if delay_timer_ref:
                            self.out_delay_timer_btn.setText(f"{delay_timer_ref}  ({delay_time:.1f}s)")
                        else:
                            self.out_delay_timer_btn.setText("타이머 선택하세요")

            # ★ IN 스텝 전용: 타임아웃 설정
            if hasattr(self, 'in_timeout_frame'):
                if type_code == "IN":
                    self.in_timeout_frame.setVisible(True)

                    # 타임아웃 사용 여부 (기존 데이터 호환: 없으면 True)
                    enabled = data.get("timeout_enabled", True)
                    if hasattr(self, 'rb_timeout_enabled'):
                        self.rb_timeout_enabled.setChecked(enabled)
                        self.rb_timeout_disabled.setChecked(not enabled)

                    # 타임아웃 시간
                    timeout = data.get("timeout", 5.0)
                    if hasattr(self, 'timeout_btn'):
                        self.timeout_btn.setText(f"{timeout:.1f} sec")

                    # 타임아웃 동작
                    action = data.get("timeout_action", "continue")
                    if action == "alarm_go":
                        self.rb_timeout_alarm_go.setChecked(True)
                    elif action == "ask":
                        self.rb_timeout_ask.setChecked(True)
                    else:  # "continue"
                        self.rb_timeout_continue.setChecked(True)

                    # 알람 번호 표시 (알람 관련 동작일 때)
                    if action in ("ask", "alarm_go") and hasattr(self, 'timeout_alarm_btn'):
                        alarm_no = data.get("timeout_alarm_no", 1)
                        try:
                            from ui.overlays.alarm_overlay import USER_ALARMS
                            alarm_msg = USER_ALARMS.get(alarm_no, f"알람 #{alarm_no}")
                        except ImportError:
                            alarm_msg = f"알람 #{alarm_no}"
                        self.timeout_alarm_btn.setText(f"A-{alarm_no:03d}: {alarm_msg}")
                        if hasattr(self, 'timeout_alarm_frame'):
                            self.timeout_alarm_frame.setVisible(True)
                else:
                    self.in_timeout_frame.setVisible(False)

        elif type_code == "TMR":
            timer_ref = data.get("timer_ref", "")
            # timer_ref가 있으면 timer_library에서 최신값 우선 참조, 스텝 데이터도 동기화
            if timer_ref and self.timer_library and timer_ref in self.timer_library:
                t = float(self.timer_library[timer_ref])
                data["time"] = t
            else:
                t = data.get("time", 1.0)
            if hasattr(self, 'tmr_btn'):
                self.tmr_btn.setText(timer_ref if timer_ref else "선택하세요")
            if hasattr(self, 'tmr_hold_time_btn'):
                self.tmr_hold_time_btn.setText(f"{t:.1f} sec")
            # 단순 대기 모드: 타이머 선택된 경우 시간 표시
            if hasattr(self, 'tmr_simple_time_frame'):
                has_ref = bool(timer_ref)
                self.tmr_simple_time_frame.setVisible(has_ref)
                if has_ref and hasattr(self, 'tmr_simple_time_btn'):
                    self.tmr_simple_time_btn.setText(f"{t:.1f} sec")

            tmr_mode = data.get("tmr_mode", "simple")
            if hasattr(self, 'rb_tmr_hold'):
                self.rb_tmr_hold.setChecked(tmr_mode == "hold")
                self.rb_tmr_simple.setChecked(tmr_mode != "hold")
            if hasattr(self, 'tmr_mode_stack'):
                self.tmr_mode_stack.setCurrentIndex(1 if tmr_mode == "hold" else 0)

            if tmr_mode == "hold":
                in_type = data.get("in_type", 0)
                if hasattr(self, 'tmr_hold_type_grp'):
                    btn = self.tmr_hold_type_grp.button(in_type)
                    if btn: btn.setChecked(True)
                if hasattr(self, 'tmr_hold_io_btn'):
                    self.tmr_hold_io_btn.setText(self._get_input_name_by_index(data.get("port", 0)))
                if data.get("on", True):
                    if hasattr(self, 'tmr_hold_rb_on'): self.tmr_hold_rb_on.setChecked(True)
                else:
                    if hasattr(self, 'tmr_hold_rb_off'): self.tmr_hold_rb_off.setChecked(True)
        
        elif type_code == "JMP":
            self.jmp_target_combo.blockSignals(True)
            self.jmp_target_combo.clear()
            jmp_items = []
            _jmp_step_num = 0
            for _s in self.sequences[self.current_seq_key]:
                if _s.get("type") == "COMMENT":
                    jmp_items.append(f"// {_s.get('text', '')}")
                else:
                    _jmp_step_num += 1
                    jmp_items.append(f"[{_jmp_step_num:02d}] {_s.get('name', '')}")
            self.jmp_target_combo.addItems(jmp_items)
            target_idx = data.get("target_idx", 0)
            self.jmp_target_combo.setCurrentIndex(target_idx)
            self.jmp_target_combo.blockSignals(False)
            if hasattr(self, 'jmp_target_btn'):
                text = self.jmp_target_combo.currentText()
                self.jmp_target_btn.setText(text if text else "선택하세요")
            
            cond = data.get("condition", False)
            self.rb_jmp_cond.setChecked(cond)
            self.rb_jmp_always.setChecked(not cond)
            self.jmp_cond_frame.setVisible(cond)

            ct = data.get("cond_type", "INPUT")
            # 하위 호환: 구 "PORT" 타입 자동 분류
            if ct == "PORT":
                v = data.get("cond_value", 0)
                if v >= 100:
                    ct = "BIT"
                elif v >= 32:
                    ct = "VALVE"
                else:
                    ct = "INPUT"
            cond_value = data.get("cond_value", 0)

            if ct == "DTCMP":
                # 데이터값 비교 (DT vs 상수). ON/OFF 무관.
                self.rb_src_dtcmp.setChecked(True)
                self.stack_cond_source.setCurrentIndex(5)
                op = int(data.get("cmp_op", 3))
                _ob = self.jmp_dtcmp_op_grp.button(op)
                if _ob:
                    _ob.setChecked(True)
                addr = int(data.get("cmp_dt_addr", 60000))
                const = int(data.get("cmp_const", 0))
                if hasattr(self, 'jmp_dt_addr_btn'):
                    self.jmp_dt_addr_btn.setText(f"DT{addr}")
                if hasattr(self, 'jmp_dt_const_btn'):
                    self.jmp_dt_const_btn.setText(str(const))
            elif ct == "STATE":
                self.rb_src_state.setChecked(True)
                self.stack_cond_source.setCurrentIndex(4)
                rb = getattr(self, 'jmp_run_state_rbs', {}).get(cond_value)
                if rb:
                    rb.setChecked(True)
            elif ct == "MODE":
                self.rb_src_mode.setChecked(True)
                self.stack_cond_source.setCurrentIndex(3)
                self.jmp_mode_combo.setCurrentIndex(cond_value)
                if hasattr(self, 'jmp_mode_btn'):
                    self.jmp_mode_btn.setText(self._get_mode_name_by_index(cond_value))
            elif ct == "VALVE":
                self.rb_src_valve.setChecked(True)
                self.stack_cond_source.setCurrentIndex(1)
                valve_idx = max(0, cond_value - 32)  # X20~X2F → combo index 0~15
                self.jmp_valve_combo.setCurrentIndex(valve_idx)
                if hasattr(self, 'jmp_valve_btn'):
                    self.jmp_valve_btn.setText(self._get_input_name_by_index(cond_value))
            elif ct == "BIT":
                self.rb_src_bit.setChecked(True)
                self.stack_cond_source.setCurrentIndex(2)
                bit_idx = max(0, cond_value - 100)
                self.jmp_bit_combo.setCurrentIndex(bit_idx)
                if hasattr(self, 'jmp_bit_btn'):
                    try:
                        from utils.internal_bit_names import get_name as _ibn_get
                        _nm = _ibn_get(f"M{bit_idx:02d}")
                    except Exception:
                        _nm = ""
                    self.jmp_bit_btn.setText(f"M{bit_idx:02d} {_nm}" if _nm else f"M{bit_idx:02d}")
            else:  # INPUT (X00~X0F)
                self.rb_src_input.setChecked(True)
                self.stack_cond_source.setCurrentIndex(0)
                self.jmp_input_combo.setCurrentIndex(cond_value)
                if hasattr(self, 'jmp_input_btn'):
                    self.jmp_input_btn.setText(self._get_input_name_by_index(cond_value))
            
            if data.get("cond_on", True): self.rb_jmp_on.setChecked(True)
            else: self.rb_jmp_off.setChecked(True)

            # DTCMP 모드에선 ON/OFF 행 숨김 (의미 없음)
            if hasattr(self, 'jmp_onoff_row'):
                self.jmp_onoff_row.setVisible(cond and ct != "DTCMP")

        elif type_code == "CALL":
            self.call_combo.blockSignals(True)
            self.call_combo.clear()
            # ★ 자기 시퀀스 제외
            self.call_combo.addItems([k for k in self.sequences.keys() if k != self.current_seq_key])
            idx = self.call_combo.findText(data.get("target_seq", ""))
            self.call_combo.setCurrentIndex(idx if idx >= 0 else -1)
            self.call_combo.blockSignals(False)
            
            # ★ 버튼 텍스트 업데이트
            if hasattr(self, 'call_btn'):
                target_seq = data.get("target_seq", "")
                if target_seq:
                    self.call_btn.setText(target_seq)
                else:
                    self.call_btn.setText("선택하세요")
            
            # ★ 실행 모드 설정
            if hasattr(self, 'rb_call_wait') and hasattr(self, 'rb_call_parallel'):
                is_parallel = data.get("parallel", False)
                if is_parallel:
                    self.rb_call_parallel.setChecked(True)
                else:
                    self.rb_call_wait.setChecked(True)

        elif type_code == "DAT":
            # 데이터연산: DT주소(60000~60099) / 연산(0:대입 1:가산 2:감산) / 상수
            addr = int(data.get("dat_dt_addr", 60000))
            op = int(data.get("dat_op", 0))
            const = int(data.get("dat_const", 0))
            if hasattr(self, 'dat_addr_btn'):
                self.dat_addr_btn.setText(f"DT{addr}")
            if hasattr(self, 'dat_op_grp'):
                _ob = self.dat_op_grp.button(op)
                if _ob:
                    _ob.setChecked(True)
                self._refresh_dat_const_label(op)
            if hasattr(self, 'dat_const_btn'):
                self.dat_const_btn.setText(str(const))

    def _on_axis_checkbox_changed(self, idx, checked):
        if self._is_loading: return
        if self.active_step_data is None: return
        # ★ active_axes로 통일
        if "active_axes" not in self.active_step_data:
            self.active_step_data["active_axes"] = [False] * 8
        self.active_step_data["active_axes"][idx] = checked

        # ★ None 체크 추가
        if self.speed_spinboxes[idx] is not None:
            self.speed_spinboxes[idx].setEnabled(True)

    def _on_pack_base_changed(self, checked):
        if self._is_loading: return
        if self.active_step_data is None: return
        if self.active_step_data.get("type") != "POS": return
        if checked:
            self.active_step_data["pack_base"] = True
        else:
            self.active_step_data.pop("pack_base", None)

    def _on_pos_exec_mode_changed(self, checked=None):
        if self._is_loading: return
        if self.active_step_data is None: return
        if self.active_step_data.get("type") != "POS": return
        # 완료 후 이행(기본)이면 키 제거, 동시 이행이면 False 저장 → 기존 레시피 diff 최소화
        if self.rb_pos_parallel.isChecked():
            self.active_step_data["wait_completion"] = False
        else:
            self.active_step_data.pop("wait_completion", None)

    def _on_step_name_changed(self, text):
        if self._is_loading: return
        if self.active_step_data is None: return
        self.active_step_data["name"] = text
        item = self.step_list.currentItem()
        if item:
            label = text
            if self.active_step_data.get("type") == "POS":
                p_name = self.active_step_data.get("point_name", "")
                if p_name:
                    label = f"{text}  ({p_name})"
            item.setText(f"[{self._step_num_for_row(self.step_list.row(item)):02d}] {label}")

    def _on_point_combo_changed(self, idx):
        pass 

    def _on_io_value_changed(self):
        if self._is_loading: return
        if self.active_step_data is None: return
        # ★ port는 선택 시(_open_io_selector)에 이미 저장됨
        # io_combo.currentIndex()는 신뢰할 수 없으므로 여기서 업데이트하지 않음
        # self.active_step_data["port"] = self.io_combo.currentIndex()  # 제거!
        self.active_step_data["on"] = self.rb_on.isChecked()

        # ★ OUT 스텝: 출력 구분 + 딜레이 저장
        if self.active_step_data.get("type") == "OUT":
            if hasattr(self, 'out_type_grp'):
                self.active_step_data["out_type"] = self.out_type_grp.checkedId()
            if hasattr(self, 'chk_out_delay'):
                self.active_step_data["delay_enable"] = self.chk_out_delay.isChecked()

        # ★ IN 스텝: 입력 구분 + 타임아웃 설정 저장
        if self.active_step_data.get("type") == "IN":
            if hasattr(self, 'in_type_grp'):
                self.active_step_data["in_type"] = self.in_type_grp.checkedId()
            # 타임아웃 사용 여부
            if hasattr(self, 'rb_timeout_enabled'):
                self.active_step_data["timeout_enabled"] = self.rb_timeout_enabled.isChecked()
            # 타임아웃 동작
            if hasattr(self, 'rb_timeout_ask'):
                if self.rb_timeout_ask.isChecked():
                    self.active_step_data["timeout_action"] = "ask"
                elif hasattr(self, 'rb_timeout_alarm_go') and self.rb_timeout_alarm_go.isChecked():
                    self.active_step_data["timeout_action"] = "alarm_go"
                else:
                    self.active_step_data["timeout_action"] = "continue"

    def _open_timer_selector(self):
        """단순 대기 모드 - 타이머 라이브러리에서 선택 (없으면 추가 가능)"""
        if self.active_step_data is None:
            return

        ADD_KEY = "+ 새 타이머 추가"
        timer_names = [ADD_KEY] + list(self.timer_library.keys())
        current_ref = self.active_step_data.get("timer_ref", None) if self.active_step_data else None
        if CardListDialog:
            def _delete_timer(name):
                if name in self.timer_library:
                    del self.timer_library[name]

            def _rename_timer(old_name, new_name):
                if old_name not in self.timer_library:
                    return
                self.timer_library[new_name] = self.timer_library.pop(old_name)
                for seq_steps in self.sequences.values():
                    if not isinstance(seq_steps, list):
                        continue
                    for step in seq_steps:
                        if step.get("timer_ref") == old_name:
                            step["timer_ref"] = new_name
                            step["name"] = new_name

            dlg = CardListDialog(timer_names, current=current_ref, title="[T] 타이머를 선택하세요", columns=4,
                                 on_delete=_delete_timer, on_rename=_rename_timer, parent=self)
            result = dlg.exec()
            selected = dlg.get_selected() if result == QDialog.Accepted else None
        else:
            selected = None

        if selected == ADD_KEY:
            self._add_timer_to_library()
            return

        if selected:
            time_sec = float(self.timer_library[selected])
            self.active_step_data["timer_ref"] = selected
            self.active_step_data["time"] = time_sec
            self.active_step_data["name"] = selected
            if hasattr(self, 'tmr_btn'):
                self.tmr_btn.setText(selected)
            if hasattr(self, 'tmr_simple_time_btn'):
                self.tmr_simple_time_btn.setText(f"{time_sec:.1f} sec")
            if hasattr(self, 'tmr_simple_time_frame'):
                self.tmr_simple_time_frame.setVisible(True)
            # 스텝 리스트 레이블 갱신
            item = self.step_list.currentItem()
            if item:
                row = self.step_list.row(item)
                item.setText(f"[{self._step_num_for_row(row):02d}] {selected}")

    def _add_timer_to_library(self):
        """타이머 라이브러리에 새 타이머를 추가하고 현재 스텝에 적용"""
        from PySide6.QtWidgets import QInputDialog
        # 이름 입력
        if TouchKeyboard:
            kb = TouchKeyboard("타이머 이름 입력", parent=self)
            if hasattr(kb, 'set_language'):
                kb.set_language("KO")
            if kb.exec() != QDialog.Accepted:
                return
            timer_name = kb.get_text().strip()
        else:
            timer_name, ok = QInputDialog.getText(self, "타이머 추가", "타이머 이름:")
            if not ok:
                return
            timer_name = timer_name.strip()

        if not timer_name:
            return
        if timer_name in self.timer_library:
            if DarkMessageDialog:
                DarkMessageDialog("중복", f"'{timer_name}' 이(가) 이미 존재합니다.", parent=self).exec()
            return

        # 시간 입력
        if NumericKeypad:
            dlg = NumericKeypad(f"'{timer_name}' 시간 설정 (초)", 1.0, 1, parent=self)
            if dlg.exec() != QDialog.Accepted:
                return
            try:
                timer_sec = float(dlg.get_value())
            except (ValueError, TypeError):
                return
        else:
            timer_sec, ok = QInputDialog.getDouble(self, "시간 입력", "시간(초):", 1.0, 0, 999, 1)
            if not ok:
                return

        self.timer_library[timer_name] = timer_sec
        print(f"[Timer Library] Added '{timer_name}': {timer_sec} sec")

        # 현재 스텝에 자동 적용
        if self.active_step_data is not None:
            self.active_step_data["timer_ref"] = timer_name
            self.active_step_data["time"] = timer_sec
            self.active_step_data["name"] = timer_name
            if hasattr(self, 'tmr_btn'):
                self.tmr_btn.setText(timer_name)
            item = self.step_list.currentItem()
            if item:
                row = self.step_list.row(item)
                item.setText(f"[{self._step_num_for_row(row):02d}] {timer_name}")

    def _on_tmr_simple_time_clicked(self):
        """단순 대기 모드 - 타이머 시간 편집"""
        if self.active_step_data is None: return
        if NumericKeypad:
            cur_val = self.active_step_data.get("time", 1.0)
            dlg = NumericKeypad("타이머 시간 설정 (초)", cur_val, 1, self)
            if dlg.exec() == QDialog.Accepted:
                val = float(dlg.get_value())
                self.active_step_data["time"] = val
                # timer_library에도 반영
                timer_ref = self.active_step_data.get("timer_ref", "")
                if timer_ref and timer_ref in self.timer_library:
                    self.timer_library[timer_ref] = val
                    # 같은 타이머를 참조하는 다른 스텝도 동기화
                    for seq_steps in self.sequences.values():
                        if not isinstance(seq_steps, list): continue
                        for step in seq_steps:
                            if step.get("type") == "TMR" and step.get("timer_ref") == timer_ref:
                                step["time"] = val
                if hasattr(self, 'tmr_simple_time_btn'):
                    self.tmr_simple_time_btn.setText(f"{val:.1f} sec")

    def _on_tmr_edit_clicked(self):
        """신호 유지 모드 - 유지 시간 직접 편집"""
        if self.active_step_data is None: return
        if NumericKeypad:
            cur_val = self.active_step_data.get("time", 1.0)
            dlg = NumericKeypad("유지 시간 설정 (초)", cur_val, 1, self)
            if dlg.exec() == QDialog.Accepted:
                val = dlg.get_value()
                self.active_step_data["time"] = val
                if hasattr(self, 'tmr_hold_time_btn'): self.tmr_hold_time_btn.setText(f"{val:.1f} sec")
    
    def _on_timeout_edit_clicked(self):
        """IN 스텝 타임아웃 편집"""
        if self.active_step_data is None: return
        if NumericKeypad:
            cur_val = self.active_step_data.get("timeout", 5.0)
            dlg = NumericKeypad("타임아웃 설정 (초)", cur_val, 1, self)
            if dlg.exec() == QDialog.Accepted:
                val = dlg.get_value()
                self.active_step_data["timeout"] = val
                self.timeout_btn.setText(f"{val:.1f} sec")

    def _on_jmp_value_changed(self):
        if self._is_loading: return
        if self.active_step_data is None: return
        d = self.active_step_data
        d["target_idx"] = self.jmp_target_combo.currentIndex()
        d["condition"] = self.rb_jmp_cond.isChecked()
        self.jmp_cond_frame.setVisible(d["condition"])

        if hasattr(self, 'rb_src_state') and self.rb_src_state.isChecked():
            d["cond_type"] = "STATE"
            checked_id = self.jmp_run_state_grp.checkedId() if hasattr(self, 'jmp_run_state_grp') else 2
            d["cond_value"] = checked_id if checked_id >= 0 else 2
            self.stack_cond_source.setCurrentIndex(4)
        elif self.rb_src_mode.isChecked():
            d["cond_type"] = "MODE"
            if d.get("cond_value", -1) < 0 or d.get("cond_value", 0) > 43:
                d["cond_value"] = 0
            self.stack_cond_source.setCurrentIndex(3)
        elif self.rb_src_valve.isChecked():
            d["cond_type"] = "VALVE"
            if d.get("cond_value", 0) < 32 or d.get("cond_value", 0) > 47:
                d["cond_value"] = 32  # X20
            self.stack_cond_source.setCurrentIndex(1)
        elif self.rb_src_bit.isChecked():
            d["cond_type"] = "BIT"
            if d.get("cond_value", 0) < 100 or d.get("cond_value", 0) > 131:
                d["cond_value"] = 100  # M00
            self.stack_cond_source.setCurrentIndex(2)
        elif hasattr(self, 'rb_src_dtcmp') and self.rb_src_dtcmp.isChecked():
            # 데이터값 비교 (DT vs 상수). 주소/상수는 팝업이 직접 기록,
            # 연산자만 여기서 읽음. ON/OFF 무관.
            d["cond_type"] = "DTCMP"
            op = self.jmp_dtcmp_op_grp.checkedId() if hasattr(self, 'jmp_dtcmp_op_grp') else 3
            d["cmp_op"] = op if op >= 0 else 3
            d.setdefault("cmp_dt_addr", 60000)
            d.setdefault("cmp_const", 0)
            self.stack_cond_source.setCurrentIndex(5)
        else:  # INPUT (X00~X0F)
            d["cond_type"] = "INPUT"
            if d.get("cond_value", -1) < 0 or d.get("cond_value", 0) > 15:
                d["cond_value"] = 0
            self.stack_cond_source.setCurrentIndex(0)

        d["cond_on"] = self.rb_jmp_on.isChecked()

        # DTCMP 모드에선 ON/OFF 행 숨김 (의미 없음)
        if hasattr(self, 'jmp_onoff_row'):
            self.jmp_onoff_row.setVisible(d["condition"] and d.get("cond_type") != "DTCMP")

    def _on_call_value_changed(self):
        if self._is_loading: return
        if self.active_step_data is None: return
        self.active_step_data["target_seq"] = self.call_combo.currentText()
        
        # ★ 실행 모드 저장
        if hasattr(self, 'rb_call_parallel'):
            self.active_step_data["parallel"] = self.rb_call_parallel.isChecked()

    # =========================================================================
    # 팝업 연결 (Overlay)
    # =========================================================================

    def _on_speed_edit_clicked(self, idx):
        if self.active_step_data is None: return
        if NumericKeypad:
            p_name = self.active_step_data.get("point_name", "")
            cur = self.points_library.get(p_name, {}).get("speeds", [100.0]*8)[idx]
            dlg = NumericKeypad("속도 입력 (1~100 %)", cur, 0, self)
            if dlg.exec() == QDialog.Accepted:
                val = max(1, min(100, int(dlg.get_value())))
                if p_name in self.points_library:
                    self.points_library[p_name]["speeds"][idx] = val
                if self.speed_spinboxes[idx] is not None:
                    self.speed_spinboxes[idx].setText(str(val))

    def _on_pos_edit_clicked(self, idx):
        if self.active_step_data is None: return
        p_name = self.active_step_data.get("point_name", "")
        if p_name in self.points_library:
            coords = self.points_library[p_name]["coords"]
            if NumericKeypad:
                from utils.axis_limits import get_axis_strokes
                stroke = get_axis_strokes()[idx] if 0 <= idx < 8 else 1000.0
                dlg = NumericKeypad(f"{idx+1}축 위치 입력 (0~{stroke:.1f} mm)", coords[idx], 3, self)
                if dlg.exec() == QDialog.Accepted:
                    val = dlg.get_value()
                    if val < 0.0 or val > stroke:
                        from ui.dialogs.sequence_utils import DarkMessageDialog
                        DarkMessageDialog(
                            "입력 범위 초과",
                            f"스트로크 한계를 벗어났습니다.\n허용 범위: 0 ~ {stroke:.3f} mm\n입력값: {val:.3f} mm",
                            is_error=True, parent=self
                        ).exec()
                        return
                    coords[idx] = val
                    if self.pos_labels[idx] is not None:
                        self.pos_labels[idx].setText(f"{coords[idx]:.3f}")

    def _refresh_point_combo(self):
        self.point_combo.blockSignals(True)
        cur = self.point_combo.currentText()
        self.point_combo.clear()
        self.point_combo.addItems(sorted(list(self.points_library.keys())))
        idx = self.point_combo.findText(cur)
        if idx >= 0: self.point_combo.setCurrentIndex(idx)
        self.point_combo.blockSignals(False)

    def _update_io_combo(self, is_out):
        # 동일 타입이면 재빌드 생략 (매 스텝 클릭마다 80개 아이템 재생성 방지)
        if getattr(self, '_io_combo_is_out', None) == is_out:
            return
        self._io_combo_is_out = is_out
        self.io_combo.blockSignals(True)
        self.io_combo.clear()
        mgr = IOManager.instance() if IOManager else None
        items = []
        if is_out:
            for i in range(32): items.append(f"[Y{i:02X}] {VALVE_LIST[i] if i<len(VALVE_LIST) else (mgr.get_output_name(i) if mgr else '예비')}")
        else:
            for i in range(32): items.append(f"[X{i:02X}] {mgr.get_input_name(i) if mgr else '입력'}")
        for i in range(INTERNAL_BIT_COUNT): items.append(f"[M{i:02X}] 내부 비트 {i}")
        self.io_combo.addItems(items)
        self.io_combo.blockSignals(False)

    def _init_tabs(self): pass
    def _on_seq_tab_changed(self, index): pass

    def _step_num_for_row(self, row):
        """COMMENT 제외 스텝 번호(1-based). COMMENT 행이면 직전 번호 반환."""
        steps = self.sequences.get(self.current_seq_key, [])
        return sum(1 for s in steps[:row+1] if s.get("type") != "COMMENT")

    def _make_step_label(self, step_num, step):
        if step.get("type") == "COMMENT":
            return f"// {step.get('text', '')}"
        label = step.get('name', '')
        t = step.get("type")
        if t == "POS":
            p_name = step.get("point_name", "")
            if p_name:
                label = f"{label}  ({p_name})"
        elif t == "CALL":
            t_seq = step.get("target_seq", "")
            if t_seq:
                label = f"{label}  ({t_seq})"
        elif t == "OUT":
            out_type = int(step.get("out_type", 0))
            port = int(step.get("port", 0))
            on_val = step.get("on", step.get("on_off", False))
            port_name = self._get_out_name(out_type, port)
            label = f"{label}  ({port_name} {'ON' if on_val else 'OFF'})"
        elif t == "IN":
            port = int(step.get("port", step.get("io_index", 0)))
            on_val = step.get("on", step.get("on_off", True))
            port_name = self._get_input_name_by_index(port)
            label = f"{label}  ({port_name} {'ON' if on_val else 'OFF'})"
        elif t == "JMP":
            target_idx = int(step.get("target_idx", 0))
            target_name = self._get_jmp_target_name(target_idx)
            if step.get("condition") and step.get("cond_type") == "DTCMP":
                _ops = {0: "=", 1: "≠", 2: ">", 3: "≥", 4: "<", 5: "≤"}
                expr = (f"DT{int(step.get('cmp_dt_addr', 60000))} "
                        f"{_ops.get(int(step.get('cmp_op', 3)), '?')} "
                        f"{int(step.get('cmp_const', 0))}")
                label = f"{label}  ({expr} → {target_name})" if target_name else f"{label}  ({expr})"
            else:
                label = f"{label}  ({target_name})" if target_name else label
        elif t == "TMR":
            ref = step.get("timer_ref", "")
            if ref:
                label = f"{label}  ({ref})"
        elif t == "DAT":
            _ops = {0: "=", 1: "+=", 2: "-="}
            addr = int(step.get("dat_dt_addr", 60000))
            op = _ops.get(int(step.get("dat_op", 0)), "=")
            const = int(step.get("dat_const", 0))
            label = f"{label}  (DT{addr} {op} {const})"
        return f"[{step_num:02d}] {label}"

    def _get_jmp_target_name(self, target_idx):
        """JMP 타겟 스텝의 표시 이름 반환 (없으면 빈 문자열).
        target_idx 는 콤보/저장/_fix_jmp_targets 와 동일하게 원본 리스트 인덱스
        (COMMENT 포함) 기준이다."""
        current_list = self.sequences.get(self.current_seq_key, [])
        if 0 <= target_idx < len(current_list):
            step = current_list[target_idx]
            if step.get("type") == "COMMENT":
                return f"// {step.get('text', '')}"
            return step.get("name", f"스텝{target_idx}")
        return f"스텝{target_idx}"

    def _load_step_list_from_memory(self):
        current_list = self.sequences.get(self.current_seq_key, [])
        new_labels = []
        step_num = 0
        for s in current_list:
            if s.get("type") != "COMMENT":
                step_num += 1
            new_labels.append(self._make_step_label(step_num, s))
        cur_count = self.step_list.count()
        new_count = len(new_labels)

        # 기존 아이템 수와 다르거나 내용이 바뀐 경우에만 업데이트
        same = (cur_count == new_count) and all(
            self.step_list.item(i).text() == new_labels[i] for i in range(cur_count)
        )
        if not same:
            self.step_list.blockSignals(True)
            self.step_list.clear()
            for label, step in zip(new_labels, current_list):
                item = QListWidgetItem(label)
                if step.get("type") == "COMMENT":
                    item.setForeground(QColor("#FFD700"))
                self.step_list.addItem(item)
            self.step_list.blockSignals(False)

        self.active_step_data = None
        self.stack.setCurrentIndex(0)
        if self.step_list.count() > 0:
            self.step_list.setCurrentRow(0)
            self._on_item_clicked(self.step_list.item(0))

    def _next_step_name(self, type_code):
        """현재 시퀀스 내에서 비어 있는 가장 낮은 번호로 이름 생성"""
        base_name = {"POS":"위치 이동","OUT":"출력 제어","IN":"입력 대기","TMR":"타이머","JMP":"점프","CALL":"호출","DAT":"데이터연산","END":"END"}.get(type_code, "Step")
        used = set()
        prefix = base_name + "_"
        for step in self.sequences.get(self.current_seq_key, []):
            if step.get("type") == type_code:
                name = step.get("name", "")
                if name.startswith(prefix):
                    suffix = name[len(prefix):]
                    if suffix.isdigit():
                        used.add(int(suffix))
        n = 1
        while n in used:
            n += 1
        return f"{base_name}_{n}"

    def _add_comment(self):
        text = self._prompt_comment_text("")
        if text is None:
            return
        data = {"type": "COMMENT", "text": text}
        current_row = self.step_list.currentRow()
        if current_row >= 0:
            insert_pos = current_row + 1
            self._fix_jmp_targets("insert", insert_pos)
            self.sequences[self.current_seq_key].insert(insert_pos, data)
            new_row = insert_pos
        else:
            self.sequences[self.current_seq_key].append(data)
            new_row = self.step_list.count()
        self._load_step_list_from_memory()
        self.step_list.setCurrentRow(new_row)
        self._on_item_clicked(self.step_list.item(new_row))

    def _edit_comment_text(self):
        if self.active_step_data is None or self.active_step_data.get("type") != "COMMENT":
            return
        current = self.active_step_data.get("text", "")
        text = self._prompt_comment_text(current)
        if text is None:
            return
        self.active_step_data["text"] = text
        self.lbl_comment_text.setText(text)
        item = self.step_list.currentItem()
        if item:
            item.setText(f"// {text}")

    def _prompt_comment_text(self, current=""):
        """코멘트 텍스트 입력 팝업. 취소 시 None 반환."""
        if TouchKeyboard:
            kb = TouchKeyboard("코멘트 입력", parent=self)
            if hasattr(kb, 'set_text'):
                kb.set_text(current)
            if hasattr(kb, 'set_language'):
                kb.set_language("KO")
            if kb.exec() == QDialog.Accepted:
                return kb.get_text().strip()
            return None
        elif RenameDialog:
            dlg = RenameDialog(current, [], self)
            if dlg.exec() == QDialog.Accepted:
                return dlg.get_new_name()
            return None
        return ""

    def _add_new_step(self, type_code):
        final_name = self._next_step_name(type_code)
        data = {"type": type_code, "name": final_name}
        if type_code == "POS":
            p_names = sorted(list(self.points_library.keys()))
            data["point_name"] = p_names[0] if p_names else final_name
            if not p_names: self.points_library[final_name] = {"coords": [0.0]*8, "speeds": [100.0]*8}
            # 새 POS는 연결된 축을 기본 선택해 무축 POS가 그대로 전송되는 것을 방지한다.
            data["active_axes"] = list(self.enabled_axes[:8])
        elif type_code == "OUT": data["port"]=0; data["on"]=True; data["out_type"]=0; data["delay_enable"]=False
        elif type_code == "IN": data["port"]=0; data["on"]=True; data["in_type"]=0
        elif type_code == "TMR": data["time"] = 1.0
        elif type_code == "JMP": data.update({"target_idx":0, "condition":False,
                                               "cmp_dt_addr":60000, "cmp_op":3, "cmp_const":0})
        elif type_code == "CALL": data["target_seq"] = ""
        elif type_code == "DAT": data.update({"dat_dt_addr":60000, "dat_op":0, "dat_const":0})
        elif type_code == "END": data["name"] = "END"
        
        # ★ 선택된 스텝 바로 아래에 삽입
        current_row = self.step_list.currentRow()
        if current_row >= 0:
            insert_pos = current_row + 1
            self._fix_jmp_targets("insert", insert_pos)
            self.sequences[self.current_seq_key].insert(insert_pos, data)
            new_row = insert_pos
        else:
            self.sequences[self.current_seq_key].append(data)
            new_row = self.step_list.count()
        
        self._load_step_list_from_memory()
        self.step_list.setCurrentRow(new_row)
        self._on_item_clicked(self.step_list.item(new_row))

    def _fix_jmp_targets(self, op, pos, pos2=None):
        """JMP target_idx를 스텝 조작 후 자동 보정
        op: 'insert'(pos에 삽입), 'delete'(pos 삭제), 'swap'(pos↔pos2 교환)
        """
        for step in self.sequences[self.current_seq_key]:
            if step.get("type") != "JMP": continue
            t = step.get("target_idx", 0)
            if op == "insert":
                if t >= pos: step["target_idx"] = t + 1
            elif op == "delete":
                if t == pos:   step["target_idx"] = 0
                elif t > pos:  step["target_idx"] = t - 1
            elif op == "swap" and pos2 is not None:
                if t == pos:   step["target_idx"] = pos2
                elif t == pos2: step["target_idx"] = pos

    def _delete_step(self):
        row = self.step_list.currentRow()
        if row >= 0 and DarkConfirmDialog:
            if DarkConfirmDialog("삭제", "정말 삭제하시겠습니까?", self).exec() == QDialog.Accepted:
                self._fix_jmp_targets("delete", row)
                del self.sequences[self.current_seq_key][row]
                self._load_step_list_from_memory()
                new_count = self.step_list.count()
                if new_count > 0:
                    new_row = min(row, new_count - 1)
                    self.step_list.setCurrentRow(new_row)
                    self._on_item_clicked(self.step_list.item(new_row))

    def _move_up(self):
        r = self.step_list.currentRow()
        if r > 0:
            lst = self.sequences[self.current_seq_key]
            self._fix_jmp_targets("swap", r - 1, r)
            lst[r], lst[r-1] = lst[r-1], lst[r]
            self._load_step_list_from_memory()
            self.step_list.setCurrentRow(r-1)
            self._on_item_clicked(self.step_list.item(r-1))

    def _move_down(self):
        r = self.step_list.currentRow()
        lst = self.sequences[self.current_seq_key]
        if r < len(lst)-1:
            self._fix_jmp_targets("swap", r, r + 1)
            lst[r], lst[r+1] = lst[r+1], lst[r]
            self._load_step_list_from_memory()
            self.step_list.setCurrentRow(r+1)
            self._on_item_clicked(self.step_list.item(r+1))

    def _on_apply_clicked(self):
        if not self.plc_client: return
        if self._send_all_sequences_to_plc():
            if DarkMessageDialog:
                DarkMessageDialog("전송 완료", "모든 시퀀스가 PLC로 전송되었습니다.", parent=self).exec()
            else:
                QMessageBox.information(self, "전송 완료", "PLC 전송 완료")
        else:
            msg = getattr(self, "_last_transfer_error", "통신 상태를 확인하세요.")
            if DarkMessageDialog:
                DarkMessageDialog("전송 실패", msg, is_error=True, parent=self).exec()
            else:
                QMessageBox.warning(self, "전송 실패", msg)

    def _on_save_clicked(self):
        if self.plc_client:
            if not self._send_all_sequences_to_plc():
                msg = getattr(self, "_last_transfer_error", "전송 실패. 그래도 저장하고 닫을까요?")
                if DarkConfirmDialog:
                    if DarkConfirmDialog("전송 실패", f"{msg}\n그래도 저장하고 닫을까요?", self).exec() != QDialog.Accepted:
                        return
                else:
                    if QMessageBox.question(self, "전송 실패", f"{msg}\n저장하고 닫을까요?") != QMessageBox.Yes:
                        return
        self.accept()

    def _send_all_sequences_to_plc(self):
        self._last_transfer_error = ""
        if not self.plc_client or not self.plc_client.is_connected:
            self._last_transfer_error = "PLC가 연결되어 있지 않습니다."
            return False
        if not self.plc_client.begin_recipe_transfer():
            mode = self.plc_client.current_op_status() if hasattr(self.plc_client, "current_op_status") else 0
            mode_name = "자동운전" if mode == 1 else "확인운전" if mode == 2 else "운전"
            self._last_transfer_error = f"{mode_name} 중에는 시퀀스를 전송할 수 없습니다.\n정지 후 다시 전송해주세요."
            return False

        try:
            # ★ 클릭 여부와 무관하게 전 스텝 정규화 (옛 필드/누락 필드 보정)
            normalize_all_sequences(self.sequences, self.timer_library)

            # ★ 디버그: 전송할 시퀀스 데이터 확인
            print(f"\n[시퀀스 전송] 전송할 시퀀스 데이터:")
            for seq_name, steps in self.sequences.items():
                print(f"  시퀀스: {seq_name}")
                for i, step in enumerate(steps):
                    if step.get("type") in ["OUT", "IN"]:
                        print(f"    Step {i}: {step.get('type')} - port={step.get('port', 'NONE')}, on={step.get('on', 'NONE')}, name={step.get('name', 'NONE')}")

            sorted_p_names = sorted(list(self.points_library.keys()))
            point_map = {name: i for i, name in enumerate(sorted_p_names)}
            seq_map = {"Main": 0, MONITOR_SEQ_KEY: 39}
            reserved = set(seq_map.keys())
            sub = sorted([k for k in self.sequences.keys() if k not in reserved])
            for i, k in enumerate(sub): seq_map[k] = i + 1
            success = True
            for seq_name, slot_id in seq_map.items():
                raw_steps = self.sequences.get(seq_name, [])

                # COMMENT 제외 인덱스 재매핑 (list_idx → plc_step_idx)
                plc_idx_map = {}
                plc_idx = 0
                for orig_idx, step in enumerate(raw_steps):
                    if step.get("type") != "COMMENT":
                        plc_idx_map[orig_idx] = plc_idx
                        plc_idx += 1

                plc_steps = []
                for orig_idx, step in enumerate(raw_steps):
                    if step.get("type") == "COMMENT":
                        continue  # 전송 제외
                    s_data = copy.deepcopy(step)
                    if s_data.get("type") == "POS":
                        s_data["point_index"] = point_map.get(s_data.get("point_name"), 0)
                    elif s_data.get("type") == "CALL":
                        s_data["sequence_id"] = seq_map.get(s_data.get("target_seq"), 0)
                    elif s_data.get("type") == "JMP":
                        s_data["target_step"] = plc_idx_map.get(s_data.get("target_idx", 0), 0)
                    plc_steps.append(s_data)
                if not self.plc_client.send_sequence_to_slot(slot_id, plc_steps): success = False
            if not self.plc_client.send_all_points(self.points_library, sorted_p_names): success = False
            return success
        finally:
            self.plc_client.end_recipe_transfer()

    def get_sequence_data(self):
        for seq in self.sequences.values():
            for s in seq:
                if s.get("type") == "POS" and s.get("point_name") in self.points_library:
                    s["coords"] = list(self.points_library[s["point_name"]]["coords"])
        return self.sequences
    
    def get_position_points(self):
        return self.points_library
    
    def _open_step_name_keyboard(self):
        if self.active_step_data is None: return
        if RenameDialog:
            all_names = [s.get('name', '') for s in self.sequences[self.current_seq_key] if s.get('type') != 'COMMENT']
            dlg = RenameDialog(self.active_step_data["name"], all_names, self)
            if dlg.exec() == QDialog.Accepted:
                self._on_step_name_changed(dlg.get_new_name())
    
    def _on_item_double_clicked(self, item):
        if self.active_step_data and self.active_step_data.get("type") == "COMMENT":
            self._edit_comment_text()
        else:
            self._open_step_name_keyboard()
    
    MAX_POINTS_LIMIT = 60  # RTEX 테이블 할당 정책과 동기화 (plc_client.MAX_POINTS)

    def _on_new_point_clicked(self):
        if len(self.points_library) >= self.MAX_POINTS_LIMIT:
            if DarkMessageDialog:
                DarkMessageDialog(
                    "포인트 한도 초과",
                    f"포인트는 최대 {self.MAX_POINTS_LIMIT}개까지 등록 가능합니다.\n"
                    f"(RTEX 테이블 정책: 60 일반 / 3 예약 / 1 파렛타이징 스크래치)",
                    parent=self
                ).exec()
            return
        if NewPointDialog:
            dlg = NewPointDialog(list(self.points_library.keys()), self)
            if dlg.exec() == QDialog.Accepted:
                name = dlg.get_name()
                if name:
                    self.points_library[name] = {
                        "coords": [0.0]*8,
                        "speeds": [100.0]*8,
                        "visible_mode": dlg.get_visible_mode(),
                    }
                    if self.active_step_data is not None:
                        self.active_step_data["point_name"] = name
                    self._refresh_point_selector()

    def _on_rename_point_clicked(self):
        if not hasattr(self, 'btn_point_select'): return
        old = self.btn_point_select.text()

        if RenameDialog:
            cur_vm = self.points_library.get(old, {}).get("visible_mode", -1)
            dlg = RenameDialog(old, list(self.points_library.keys()), self, visible_mode=cur_vm)
            if dlg.exec() == QDialog.Accepted:
                new = dlg.get_new_name()
                new_vm = dlg.get_visible_mode()
                if new and new != old:
                    self.points_library[new] = self.points_library.pop(old)
                    # 모든 시퀀스의 POS 스텝에서 point_name 과 name(표시용) 동기 갱신.
                    # [D-1] name 까지 맞춰 레거시 스텝(point_name 없이 name 만 가진)도 호환.
                    for seq in self.sequences.values():
                        for s in seq:
                            if s.get("point_name") == old:
                                s["point_name"] = new
                            if s.get("type") == "POS" and s.get("name") == old:
                                s["name"] = new
                    if self.active_step_data.get("point_name") == old:
                        self.active_step_data["point_name"] = new
                    if self.active_step_data.get("type") == "POS" and self.active_step_data.get("name") == old:
                        self.active_step_data["name"] = new
                    old = new
                # visible_mode 항상 업데이트
                if old in self.points_library:
                    self.points_library[old]["visible_mode"] = new_vm
                self._refresh_point_selector()
                self._load_step_list_from_memory()

    def _on_delete_point_clicked(self):
        if not hasattr(self, 'btn_point_select'): return
        cur = self.btn_point_select.text()
        
        if cur and DarkConfirmDialog:
            if DarkConfirmDialog("삭제", "포인트를 삭제하시겠습니까?", self).exec() == QDialog.Accepted:
                del self.points_library[cur]
                if self.points_library:
                    next_point = sorted(list(self.points_library.keys()))[0]
                else:
                    next_point = "Point_1"
                    self.points_library[next_point] = {"coords": [0.0]*8, "speeds": [100.0]*8}
                
                self.active_step_data["point_name"] = next_point
                self._refresh_point_selector()
                self._load_step_list_from_memory()
    
    # ★ 네비게이션 관리
    def _update_sequence_info(self):
        self.lbl_curr_seq.setText(f" {self.current_seq_key}")
        seq_count = len(self.sequences)
        if seq_count > 1:
            self.lbl_curr_seq.setStyleSheet("""
                QLabel { background: rgba(70,140,255,0.1); border: 2px solid #468CFF;
                         border-radius: 6px; color: #468CFF; font-size: 18px;
                         font-weight: bold; padding-left: 15px; }
                QLabel:hover { background: rgba(70,140,255,0.25); }
            """)
        else:
            self.lbl_curr_seq.setStyleSheet("""
                QLabel { background: rgba(70,140,255,0.05); border: 2px solid #335a99;
                         border-radius: 6px; color: #5578aa; font-size: 18px;
                         font-weight: bold; padding-left: 15px; }
            """)
        self.btn_del_seq.setEnabled(self.current_seq_key != "Main")
        # 이름변경도 Main/Monitor 는 비활성
        if hasattr(self, 'btn_rename_seq'):
            self.btn_rename_seq.setEnabled(self.current_seq_key not in ("Main", MONITOR_SEQ_KEY))

    def _on_rename_sequence_clicked(self):
        """현재 선택된 시퀀스 이름 변경. Main/Monitor 는 변경 불가."""
        cur = self.current_seq_key
        if cur in ("Main", MONITOR_SEQ_KEY):
            return
        self._rename_sequence(cur)

    def _on_add_sequence(self):
        if RenameDialog:
            dlg = RenameDialog("", list(self.sequences.keys()), self, confirm_text="추가")
            dlg.setWindowTitle("새 시퀀스 생성")
            if dlg.exec() == QDialog.Accepted:
                name = dlg.get_new_name()
                if name:
                    self.sequences[name] = []
                    self.current_seq_key = name
                    self._update_sequence_info()
                    self._load_step_list_from_memory()

    def _open_sequence_list(self):
        if SequenceListDialog:
            seq_map = {MONITOR_SEQ_KEY: 39, "Main": 0}
            reserved = set(seq_map.keys())
            for i, k in enumerate(sorted(k for k in self.sequences if k not in reserved)):
                seq_map[k] = i + 1
            dlg = SequenceListDialog(self.sequences.keys(), self.current_seq_key, self, seq_map=seq_map)
            if dlg.exec() == QDialog.Accepted:
                if dlg.rename_requested:
                    self._rename_sequence(dlg.rename_requested)
                else:
                    selected = dlg.get_selected()
                    if selected:
                        self.current_seq_key = selected
                        self._update_sequence_info()
                        self._load_step_list_from_memory()

    def _rename_sequence(self, old_name):
        if not RenameDialog: return
        if old_name in ("Main", MONITOR_SEQ_KEY): return
        dlg = RenameDialog(old_name, list(self.sequences.keys()), self, confirm_text="변경")
        if dlg.exec() == QDialog.Accepted:
            new_name = dlg.get_new_name()
            if new_name and new_name != old_name:
                # 1) sequences dict key 교체
                self.sequences = {(new_name if k == old_name else k): v
                                  for k, v in self.sequences.items()}
                # 2) [중요] 모든 시퀀스의 CALL 스텝에서 target_seq 일괄 갱신
                #    이걸 안 하면 저장 후 CALL 이 존재하지 않는 이름을 참조해
                #    PLC 전송 시 seq_map.get() 기본값 0(Main)으로 떨어져 무한 재귀 위험.
                replaced = 0
                for seq_list in self.sequences.values():
                    for step in seq_list:
                        if step.get("type") == "CALL" and step.get("target_seq") == old_name:
                            step["target_seq"] = new_name
                            replaced += 1
                if replaced:
                    print(f"[SequenceEditor] CALL 참조 갱신: '{old_name}' → '{new_name}' ({replaced}개)")
                if self.current_seq_key == old_name:
                    self.current_seq_key = new_name
                self._update_sequence_info()
                self._load_step_list_from_memory()

    def _on_delete_sequence(self):
        if self.current_seq_key == "Main": return
        if DarkConfirmDialog:
            if DarkConfirmDialog("삭제", f"'{self.current_seq_key}' 시퀀스를 삭제하시겠습니까?", self).exec() == QDialog.Accepted:
                del self.sequences[self.current_seq_key]
                self.current_seq_key = "Main"
                self._update_sequence_info()
                self._load_step_list_from_memory()
    
    def _is_point_visible(self, name):
        """포인트의 visible_mode + 현재 mode_data 기준 표시 여부 (page_position과 동일 규칙)"""
        vm = self.points_library.get(name, {}).get("visible_mode", -1)
        # 구버전 int 형식 하위 호환
        if isinstance(vm, int):
            if vm < 0:
                return True
            return bool(self.mode_data[vm]) if self.mode_data and vm < len(self.mode_data) else False
        # 신규 list 형식: 빈 리스트 = 항상 표시, 아니면 OR 조건
        if not vm:
            return True
        return any(bool(self.mode_data[i]) for i in vm if self.mode_data and i < len(self.mode_data))

    # ★ [수정] 포인트 선택기 팝업 호출
    def _open_point_list(self):
        if self._is_loading: return
        if self.active_step_data is None: return

        cur_point = self.active_step_data.get("point_name", "")
        if PointListDialog:
            # visible_mode 기준으로 현재 모드에서 보이는 포인트만 필터링
            visible_keys = [k for k in self.points_library.keys() if self._is_point_visible(k)]
            # 현재 선택된 포인트는 숨겨져 있더라도 리스트에 유지 (편집 중 확인용)
            if cur_point and cur_point in self.points_library and cur_point not in visible_keys:
                visible_keys.append(cur_point)
            dlg = PointListDialog(visible_keys, cur_point, self)
            if dlg.exec() == QDialog.Accepted:
                selected = dlg.get_selected()
                if selected:
                    self.active_step_data["point_name"] = selected
                    self._refresh_point_selector()

                    # 리스트 아이템 포인트명 갱신
                    item = self.step_list.currentItem()
                    if item:
                        name = self.active_step_data.get("name", "")
                        row = self.step_list.row(item)
                        item.setText(f"[{self._step_num_for_row(row):02d}] {name}  ({selected})")

                    coords = self.points_library.get(selected, {}).get("coords", [0.0]*8)
                    for i in range(8):
                        if self.pos_labels[i] is not None:
                            self.pos_labels[i].setText(f"{coords[i]:.3f}")

    # ★ [수정] 버튼 텍스트 갱신 함수
    def _refresh_point_selector(self):
        if self.active_step_data is None: return
        if hasattr(self, 'btn_point_select'):
            p_name = self.active_step_data.get("point_name", "선택하세요")
            self.btn_point_select.setText(p_name)
    
    # =========================================================
    # ★ [신규] 카드형 선택 팝업 함수들
    # =========================================================
    
    def _open_io_selector(self):
        """IO 선택 팝업 (OUT: 밸브 설정, IN: 입력 이름)"""
        if not hasattr(self, 'io_combo'): return
        
        # 현재 스텝 타입 확인
        step_type = self.active_step_data.get("type", "OUT") if self.active_step_data else "OUT"
        
        if step_type == "OUT":
            # ========== OUT 스텝: 출력 구분별 비트 선택 ==========
            out_type = self.active_step_data.get("out_type", 0) if self.active_step_data else 0
            current_port = self.active_step_data.get("port", 0) if self.active_step_data else 0

            try:
                from utils.io_manager import IOManager
                _mgr = IOManager.instance()
            except Exception:
                _mgr = None

            if out_type == 0:   # 시스템 출력 Y00~Y0F (DT203, 16비트)
                if _mgr:
                    items = [f"Y{i:02X}: {_mgr.get_output_name(i)}" for i in range(16)]
                else:
                    items = [f"Y{i:02X}" for i in range(16)]
                title = "시스템 출력 선택 (Y00~Y0F)"
            elif out_type == 1: # 밸브 출력 Y20~Y2F (DT204, 16비트)
                if _mgr:
                    items = [f"Y{0x20+i:02X}: {_mgr.get_output_name(16+i)}" for i in range(16)]
                else:
                    items = [f"Y{0x20+i:02X}" for i in range(16)]
                title = "밸브 출력 선택 (Y20~Y2F)"
            else:               # 내부 비트 (M00~M31)
                from utils.internal_bit_names import format_card, set_name, get_name, parse_key
                items = [format_card(i) for i in range(32)]
                title = "내부 비트 선택 (M00~M31)"
                current = items[current_port] if 0 <= current_port < len(items) else None

                def _rename_m(old_item, parent_dlg):
                    """내부비트 rename — 초기값은 현재 저장된 이름만, 빈 이름 허용(=삭제)."""
                    from ui.dialogs.sequence_utils import RenameDialog
                    key = parse_key(old_item)
                    cur_nm = get_name(key)
                    dlg_rn = RenameDialog(key, [], parent=parent_dlg, confirm_text="변경",
                                          initial_text=cur_nm, allow_empty=True)
                    if dlg_rn.exec() != QDialog.Accepted:
                        return None
                    new_name = dlg_rn.get_new_name().strip()
                    set_name(key, new_name)  # 빈 이름이면 내부에서 삭제 처리
                    return f"{key}\n{new_name}" if new_name else key

                from ui.dialogs.sequence_utils import CardListDialog
                dlg = CardListDialog(items, current, title, columns=4, parent=self, rename_handler=_rename_m)
                if dlg.exec() == QDialog.Accepted:
                    selected = dlg.get_selected()
                    if selected:
                        key = parse_key(selected)  # "M00"
                        try:
                            bit_idx = int(key[1:])
                        except ValueError:
                            bit_idx = 0
                        if self.active_step_data:
                            self.active_step_data["port"] = bit_idx
                        self.io_combo.setCurrentIndex(bit_idx)
                        if hasattr(self, 'io_combo_btn'):
                            self.io_combo_btn.setText(self._get_out_name(out_type, bit_idx))
                        print(f"[시퀀스 편집기] OUT 내부비트 선택: {key} (bit_idx={bit_idx})")
                return

            current = items[current_port] if 0 <= current_port < len(items) else None

            from ui.dialogs.sequence_utils import CardListDialog
            dlg = CardListDialog(items, current, title, columns=4, parent=self)
            if dlg.exec() == QDialog.Accepted:
                selected = dlg.get_selected()
                if selected and selected in items:
                    bit_idx = items.index(selected)
                    if self.active_step_data:
                        self.active_step_data["port"] = bit_idx
                    self.io_combo.setCurrentIndex(bit_idx)
                    if hasattr(self, 'io_combo_btn'):
                        self.io_combo_btn.setText(self._get_out_name(out_type, bit_idx))
                    print(f"[시퀀스 편집기] OUT 포트 선택: {selected} (out_type={out_type}, bit_idx={bit_idx})")
        
        else:  # step_type == "IN"
            # ========== IN 스텝: 입력 구분별 필터링 ==========
            in_type = self.active_step_data.get("in_type", 0) if self.active_step_data else 0
            current_port = self.active_step_data.get("port", 0) if self.active_step_data else 0

            try:
                from utils.io_manager import IOManager
                mgr = IOManager.instance() if IOManager else None
            except Exception:
                mgr = None

            items = []
            port_indices = []

            if in_type == 0:  # 시스템 입력 X00~X0F
                for i in range(16):
                    name = mgr.get_input_name(i) if mgr else f"X{i:02X}"
                    items.append(f"X{i:02X}: {name}")
                    port_indices.append(i)
                title = "시스템 입력 선택 (X00~X0F)"
            elif in_type == 1:  # 밸브 입력 X20~X2F
                for i in range(16):
                    x_addr = 0x20 + i
                    io_idx = 16 + i
                    name = mgr.get_input_name(io_idx) if mgr else f"X{x_addr:02X}"
                    items.append(f"X{x_addr:02X}: {name}")
                    port_indices.append(x_addr)  # 32~47
                title = "밸브 입력 선택 (X20~X2F)"
            else:  # 내부 비트 M00~M31
                from utils.internal_bit_names import format_card, set_name, get_name, parse_key
                items = [format_card(i) for i in range(32)]
                port_indices = [100 + i for i in range(32)]
                title = "내부 비트 선택 (M00~M31)"

                current = None
                try:
                    idx = port_indices.index(current_port)
                    current = items[idx]
                except ValueError:
                    current = None

                def _rename_m(old_item, parent_dlg):
                    from ui.dialogs.sequence_utils import RenameDialog
                    key = parse_key(old_item)
                    cur_nm = get_name(key)
                    dlg_rn = RenameDialog(key, [], parent=parent_dlg, confirm_text="변경",
                                          initial_text=cur_nm, allow_empty=True)
                    if dlg_rn.exec() != QDialog.Accepted:
                        return None
                    new_name = dlg_rn.get_new_name().strip()
                    set_name(key, new_name)
                    return f"{key}\n{new_name}" if new_name else key

                from ui.dialogs.sequence_utils import CardListDialog
                dlg = CardListDialog(items, current, title, columns=4, parent=self, rename_handler=_rename_m)
                if dlg.exec() == QDialog.Accepted:
                    selected = dlg.get_selected()
                    if selected:
                        key = parse_key(selected)
                        try:
                            bit_idx = int(key[1:])
                        except ValueError:
                            bit_idx = 0
                        port_idx = 100 + bit_idx
                        if self.active_step_data:
                            self.active_step_data["port"] = port_idx
                        self.io_combo.setCurrentIndex(0)
                        if hasattr(self, 'io_combo_btn'):
                            self.io_combo_btn.setText(selected.replace("\n", " "))
                        print(f"[시퀀스 편집기] IN 내부비트 선택: {key} (port_idx={port_idx})")
                return

            current = None
            try:
                idx = port_indices.index(current_port)
                current = items[idx]
            except ValueError:
                current = None

            from ui.dialogs.sequence_utils import CardListDialog
            dlg = CardListDialog(items, current, title, columns=4, parent=self)
            if dlg.exec() == QDialog.Accepted:
                selected = dlg.get_selected()
                if selected and selected in items:
                    list_idx = items.index(selected)
                    port_idx = port_indices[list_idx]
                    if self.active_step_data:
                        self.active_step_data["port"] = port_idx
                    self.io_combo.setCurrentIndex(port_idx if port_idx < 100 else 0)
                    if hasattr(self, 'io_combo_btn'):
                        self.io_combo_btn.setText(selected)
                    print(f"[시퀀스 편집기] IN 포트 선택: {selected} (port_idx={port_idx})")
    
    def _open_jmp_input_selector(self):
        """JMP 조건 - 시스템입력 (X00~X0F) 선택 팝업"""
        if not hasattr(self, 'jmp_input_combo'): return

        try:
            from utils.io_manager import IOManager
            mgr = IOManager.instance() if IOManager else None
            items = []
            port_indices = []
            for i in range(16):  # X00~X0F
                name = mgr.get_input_name(i) if mgr else None
                items.append(f"X{i:02X}: {name}" if name else f"X{i:02X}")
                port_indices.append(i)
        except Exception:
            items = [f"X{i:02X}" for i in range(16)]
            port_indices = list(range(16))

        current_val = self.active_step_data.get("cond_value", 0) if self.active_step_data else 0
        current = None
        try:
            current = items[port_indices.index(current_val)]
        except ValueError:
            pass

        from ui.dialogs.sequence_utils import CardListDialog
        dlg = CardListDialog(items, current, " 시스템입력을 선택하세요", columns=4, parent=self)
        if dlg.exec() == QDialog.Accepted:
            selected = dlg.get_selected()
            if selected and selected in items:
                port_idx = port_indices[items.index(selected)]
                if self.active_step_data:
                    self.active_step_data["cond_value"] = port_idx
                self.jmp_input_combo.setCurrentIndex(port_idx)
                if hasattr(self, 'jmp_input_btn'):
                    self.jmp_input_btn.setText(selected)

    def _open_jmp_valve_selector(self):
        """JMP 조건 - 밸브입력 (X20~X2F) 선택 팝업"""
        if not hasattr(self, 'jmp_valve_combo'): return

        try:
            from utils.io_manager import IOManager
            mgr = IOManager.instance() if IOManager else None
            items = []
            port_indices = []
            for i in range(16):  # X20~X2F (port_idx 32~47)
                port_idx = 32 + i
                io_idx = 16 + i  # IOManager 내 인덱스 (X20 = io_idx 16)
                name = mgr.get_input_name(io_idx) if mgr else None
                items.append(f"X{port_idx:02X}: {name}" if name else f"X{port_idx:02X}")
                port_indices.append(port_idx)
        except Exception:
            items = [f"X{32+i:02X}" for i in range(16)]
            port_indices = list(range(32, 48))

        current_val = self.active_step_data.get("cond_value", 32) if self.active_step_data else 32
        current = None
        try:
            current = items[port_indices.index(current_val)]
        except ValueError:
            pass

        from ui.dialogs.sequence_utils import CardListDialog
        dlg = CardListDialog(items, current, " 밸브입력을 선택하세요", columns=4, parent=self)
        if dlg.exec() == QDialog.Accepted:
            selected = dlg.get_selected()
            if selected and selected in items:
                port_idx = port_indices[items.index(selected)]
                if self.active_step_data:
                    self.active_step_data["cond_value"] = port_idx
                self.jmp_valve_combo.setCurrentIndex(port_idx - 32)
                if hasattr(self, 'jmp_valve_btn'):
                    self.jmp_valve_btn.setText(selected)

    def _open_jmp_bit_selector(self):
        """JMP 조건 - 내부비트 (M) 선택 팝업 — 이름 표시/편집 지원 (IN/OUT 과 동일)."""
        if not hasattr(self, 'jmp_bit_combo'): return

        from utils.internal_bit_names import format_card, set_name, get_name, parse_key
        items = [format_card(i) for i in range(32)]
        port_indices = [100 + i for i in range(32)]

        current_val = self.active_step_data.get("cond_value", 100) if self.active_step_data else 100
        current = None
        try:
            current = items[port_indices.index(current_val)]
        except ValueError:
            pass

        def _rename_m(old_item, parent_dlg):
            from ui.dialogs.sequence_utils import RenameDialog
            key = parse_key(old_item)
            cur_nm = get_name(key)
            dlg_rn = RenameDialog(key, [], parent=parent_dlg, confirm_text="변경",
                                  initial_text=cur_nm, allow_empty=True)
            if dlg_rn.exec() != QDialog.Accepted:
                return None
            new_name = dlg_rn.get_new_name().strip()
            set_name(key, new_name)
            return f"{key}\n{new_name}" if new_name else key

        from ui.dialogs.sequence_utils import CardListDialog
        dlg = CardListDialog(items, current, " 내부비트를 선택하세요", columns=4, parent=self,
                             rename_handler=_rename_m)
        if dlg.exec() == QDialog.Accepted:
            selected = dlg.get_selected()
            if selected:
                key = parse_key(selected)
                try:
                    bit_idx = int(key[1:])
                except ValueError:
                    bit_idx = 0
                port_idx = 100 + bit_idx
                if self.active_step_data:
                    self.active_step_data["cond_value"] = port_idx
                self.jmp_bit_combo.setCurrentIndex(bit_idx)
                if hasattr(self, 'jmp_bit_btn'):
                    self.jmp_bit_btn.setText(selected.replace("\n", " "))
    
    def _open_jmp_dt_addr(self):
        """JMP 데이터값 비교 - DT 주소 입력 (숫자 키패드)."""
        if self.active_step_data is None or NumericKeypad is None:
            return
        cur = int(self.active_step_data.get("cmp_dt_addr", 60000))
        dlg = NumericKeypad("비교할 DT 주소 (60000~60099)", cur, 0, self)
        if dlg.exec() == QDialog.Accepted:
            # PLC DTPool(g_DTPool AT DT60000, 100워드) 범위로 클램프
            addr = max(60000, min(60099, int(dlg.get_value())))
            self.active_step_data["cmp_dt_addr"] = addr
            if hasattr(self, 'jmp_dt_addr_btn'):
                self.jmp_dt_addr_btn.setText(f"DT{addr}")

    def _open_jmp_dt_const(self):
        """JMP 데이터값 비교 - 비교 상수 입력 (부호 허용, 숫자 키패드)."""
        if self.active_step_data is None or NumericKeypad is None:
            return
        cur = int(self.active_step_data.get("cmp_const", 0))
        dlg = NumericKeypad("비교 상수 입력", cur, 0, self)
        if dlg.exec() == QDialog.Accepted:
            val = int(dlg.get_value())
            self.active_step_data["cmp_const"] = val
            if hasattr(self, 'jmp_dt_const_btn'):
                self.jmp_dt_const_btn.setText(str(val))

    # ── 데이터연산(DAT) ──────────────────────────────────────────
    def _open_dat_addr(self):
        """DAT - 대상 DT 주소 입력 (60000~60099 클램프)."""
        if self.active_step_data is None or NumericKeypad is None:
            return
        cur = int(self.active_step_data.get("dat_dt_addr", 60000))
        dlg = NumericKeypad("대상 DT 주소 (60000~60099)", cur, 0, self)
        if dlg.exec() == QDialog.Accepted:
            addr = max(60000, min(60099, int(dlg.get_value())))  # g_DTPool 범위
            self.active_step_data["dat_dt_addr"] = addr
            if hasattr(self, 'dat_addr_btn'):
                self.dat_addr_btn.setText(f"DT{addr}")

    def _open_dat_const(self):
        """DAT - 상수 입력 (부호 허용)."""
        if self.active_step_data is None or NumericKeypad is None:
            return
        cur = int(self.active_step_data.get("dat_const", 0))
        op = int(self.active_step_data.get("dat_op", 0))
        title = {0: "대입 값 입력", 1: "가산 값 입력", 2: "감산 값 입력"}.get(op, "상수 값 입력")
        dlg = NumericKeypad(title, cur, 0, self)
        if dlg.exec() == QDialog.Accepted:
            val = int(dlg.get_value())
            self.active_step_data["dat_const"] = val
            if hasattr(self, 'dat_const_btn'):
                self.dat_const_btn.setText(str(val))

    def _refresh_dat_const_label(self, op=None):
        if not hasattr(self, 'dat_const_label'):
            return
        if op is None:
            op = self.dat_op_grp.checkedId() if hasattr(self, 'dat_op_grp') else 0
        label = {0: "대입 값", 1: "가산 값", 2: "감산 값"}.get(op, "상수 값")
        self.dat_const_label.setText(label)

    def _on_dat_op_changed(self, checked=None):
        """DAT - 연산자(대입/가산/감산) 변경 → active_step_data 기록."""
        if self._is_loading: return
        if self.active_step_data is None: return
        if self.active_step_data.get("type") != "DAT": return
        if hasattr(self, 'dat_op_grp'):
            op = self.dat_op_grp.checkedId()
            self.active_step_data["dat_op"] = op if op >= 0 else 0
            self._refresh_dat_const_label(self.active_step_data["dat_op"])

    def _open_jmp_mode_selector(self):
        """JMP 조건 - 모드 선택 팝업"""
        if not hasattr(self, 'jmp_mode_combo'): return
        
        # 모드 0~43 (page_mode.py 참조)
        items = []
        
        # 기본 모드 이름 (page_mode.py에서 복사)
        default_names = [
            "제품측 취출", "런너측 취출", "주행 대기", "하강 대기",
            "주행도중개방", "복귀도중개방", "안전도어 회피", "안전도어 회피2",
            "낙하측 반전", "주행도중 반전", "취출대기 반전", "고정측 취출",
            "제품 형내개방", "런너 형내개방", "에젝터 연동", "언더컷 취출모드",
            "척1 사용", "척1 감지", "척2 사용", "척2 감지",
            "척3 사용", "척3 감지", "척4 사용", "척4 감지",
            "흡착1 사용", "흡착1 감지", "흡착2 사용", "흡착2 감지",
            "흡착3 사용", "흡착3 감지", "흡착4 사용", "흡착4 감지",
            "2포인트 개방", "공정감시 모드"
        ]
        
        # ModeManager에서 이름 가져오기
        try:
            from utils.mode_manager import ModeManager
            mgr = ModeManager.instance() if ModeManager else None
            
            for i in range(44):
                if mgr:
                    name = mgr.get_name(i)
                elif i < len(default_names):
                    name = default_names[i]
                else:
                    name = f"User Mode {i - 34 + 1}"
                
                items.append(f"[{i:02d}] {name}")
        except Exception as e:
            print(f"[시퀀스 편집기] 모드 로드 실패: {e}")
            for i in range(44):
                if i < len(default_names):
                    items.append(f"[{i:02d}] {default_names[i]}")
                else:
                    items.append(f"[{i:02d}] User Mode {i - 34 + 1}")
        
        from ui.dialogs.sequence_utils import CardListDialog
        
        # ★ 현재 선택 (active_step_data에서 가져오기)
        current_mode = self.active_step_data.get("cond_value", 0) if self.active_step_data else 0
        current = items[current_mode] if current_mode < len(items) else None
        
        print(f"[DEBUG] JMP 모드 선택 팝업 - current_mode={current_mode}, current={current}")
        
        dlg = CardListDialog(items, current, " 모드를 선택하세요", columns=4, parent=self)
        if dlg.exec() == QDialog.Accepted:
            selected = dlg.get_selected()
            if selected and selected in items:
                mode_idx = items.index(selected)
                
                # active_step_data에 직접 저장
                if self.active_step_data:
                    self.active_step_data["cond_value"] = mode_idx
                
                self.jmp_mode_combo.setCurrentIndex(mode_idx)
                
                if hasattr(self, 'jmp_mode_btn'):
                    self.jmp_mode_btn.setText(selected)
                
                print(f"[시퀀스 편집기] JMP 모드 선택: {selected} (mode_idx={mode_idx})")
    
    def _open_jmp_target_selector(self):
        """JMP 타겟 스텝 선택 팝업 (리스트형, COMMENT 제외, 터치 스크롤)"""
        if not hasattr(self, 'jmp_target_combo'): return

        steps = self.sequences.get(self.current_seq_key, [])

        # COMMENT 제외 (list_idx, label) 수집
        entries = []
        step_num = 0
        for i, s in enumerate(steps):
            if s.get("type") == "COMMENT":
                continue
            step_num += 1
            name = s.get('name', 'Unnamed')
            stype = s.get("type")
            if stype == "POS":
                p_name = s.get('point_name', '')
                label = f"[{step_num:02d}] {name}  ({p_name})" if p_name else f"[{step_num:02d}] {name}"
            elif stype == "CALL":
                t_seq = s.get('target_seq', '')
                label = f"[{step_num:02d}] {name}  ({t_seq})" if t_seq else f"[{step_num:02d}] {name}"
            else:
                label = f"[{step_num:02d}] {name}"
            entries.append((i, label))

        from ui.dialogs.sequence_utils import OverlayDialog
        current_list_idx = self.jmp_target_combo.currentIndex()

        dlg = OverlayDialog(self)
        dlg.setFixedContentSize(500, 600)
        dlg.layout.addWidget(QLabel(" 점프할 스텝을 선택하세요"))

        list_widget = TouchScrollListWidget()
        list_widget.setStyleSheet(
            "QListWidget { background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.15);"
            " border-radius: 8px; color: #EEE; font-size: 18px; padding: 6px; outline: none; }"
            " QListWidget::item { height: 50px; padding-left: 12px;"
            " border-bottom: 1px solid rgba(255,255,255,0.05); }"
            " QListWidget::item:selected { background: rgba(70, 140, 255, 0.4);"
            " border: 1px solid #468CFF; color: white; }"
        )
        list_widget.setFocusPolicy(Qt.NoFocus)

        if not entries:
            empty = QListWidgetItem("(스텝 없음)")
            empty.setFlags(empty.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsEnabled)
            list_widget.addItem(empty)
        else:
            for list_idx, label in entries:
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, list_idx)
                list_widget.addItem(item)
                if list_idx == current_list_idx:
                    list_widget.setCurrentItem(item)
        dlg.layout.addWidget(list_widget, 1)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("취소")
        btn_ok = QPushButton("선택")
        btn_cancel.setFixedHeight(50); btn_ok.setFixedHeight(50)
        btn_cancel.setStyleSheet("QPushButton { background: rgba(255,255,255,0.1); border: 1px solid #888;"
                                 " color: white; border-radius: 8px; font-size: 16px; }")
        btn_ok.setStyleSheet("QPushButton { background: rgba(70,140,255,0.4); border: 1px solid #468CFF;"
                             " color: white; border-radius: 8px; font-size: 16px; font-weight: bold; }")
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok.clicked.connect(dlg.accept)
        list_widget.itemDoubleClicked.connect(lambda _: dlg.accept())
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_ok)
        dlg.layout.addLayout(btn_row)

        if dlg.exec() == QDialog.Accepted:
            item = list_widget.currentItem()
            if item is None: return
            list_idx = item.data(Qt.UserRole)
            if list_idx is None: return
            self.jmp_target_combo.setCurrentIndex(list_idx)
            if hasattr(self, 'jmp_target_btn'):
                self.jmp_target_btn.setText(self.jmp_target_combo.currentText())
    
    def _open_timeout_alarm_selector(self):
        """IN 타임아웃 알람 번호 선택 팝업"""
        if self.active_step_data is None: return

        try:
            from ui.overlays.alarm_overlay import USER_ALARMS
        except ImportError:
            return

        from ui.dialogs.sequence_utils import CardListDialog

        items = [f"A-{no:03d}: {msg}" for no, msg in sorted(USER_ALARMS.items())]
        if not items:
            return

        current_no = self.active_step_data.get("timeout_alarm_no", 1)
        current = f"A-{current_no:03d}: {USER_ALARMS.get(current_no, '')}"

        dlg = CardListDialog(items, current, " 알람 번호 선택", columns=2, parent=self)
        if dlg.exec() == QDialog.Accepted:
            selected = dlg.get_selected()
            if selected:
                # "A-001: 메시지" 형식에서 번호 파싱
                alarm_no = int(selected[2:5])
                self.active_step_data["timeout_alarm_no"] = alarm_no
                if hasattr(self, 'timeout_alarm_btn'):
                    self.timeout_alarm_btn.setText(selected)
                print(f"[시퀀스 편집기] 타임아웃 알람 선택: {selected}")
    
    def _open_call_selector(self):
        """CALL 시퀀스 선택 팝업"""
        if not hasattr(self, 'call_combo'): return
        
        # ★ 시퀀스 리스트 (자기 시퀀스 제외)
        items = [k for k in self.sequences.keys() if k != self.current_seq_key]
        
        from ui.dialogs.sequence_utils import CardListDialog
        
        # ★ 현재 선택 (active_step_data에서 가져오기)
        current_seq = self.active_step_data.get("target_seq", "") if self.active_step_data else ""
        current = current_seq if current_seq in items else None
        
        print(f"[DEBUG] CALL 선택 팝업 - current_seq={current_seq}, current={current}, items={items}")
        
        dlg = CardListDialog(items, current, "[C] 호출할 시퀀스를 선택하세요", columns=4, parent=self)
        if dlg.exec() == QDialog.Accepted:
            selected = dlg.get_selected()
            if selected:
                # ★ active_step_data에 직접 저장
                if self.active_step_data:
                    self.active_step_data["target_seq"] = selected
                
                idx = items.index(selected)
                self.call_combo.setCurrentIndex(idx)
                
                # 버튼 텍스트도 업데이트
                if hasattr(self, 'call_btn'):
                    self.call_btn.setText(selected)
                
                print(f"[시퀀스 편집기] CALL 시퀀스 선택: {selected}")
    
    # =========================================================
    # ★ [신규] 밸브 설정 헬퍼 함수
    # =========================================================
    
    def _get_out_name(self, out_type, bit_index):
        """출력 구분 + 비트 인덱스 → 표시 이름 (IOManager 실제 이름 사용)"""
        try:
            from utils.io_manager import IOManager
            mgr = IOManager.instance()
            if out_type == 0:  # 시스템 출력 Y00~Y0F
                name = mgr.get_output_name(bit_index)
                return f"Y{bit_index:02X}: {name}"
            elif out_type == 1:  # 밸브 출력 Y20~Y2F
                io_idx = 16 + bit_index
                y_addr = 0x20 + bit_index
                name = mgr.get_output_name(io_idx)
                return f"Y{y_addr:02X}: {name}"
        except Exception:
            pass
        if out_type == 0:
            return f"Y{bit_index:02X}"
        elif out_type == 1:
            return f"Y{0x20 + bit_index:02X}"
        else:
            # 내부비트 - 사용자 정의 이름 있으면 "M00: 감지비트" 형식
            try:
                from utils.internal_bit_names import get_name
                nm = get_name(f"M{bit_index:02d}")
                if nm:
                    return f"M{bit_index:02d}: {nm}"
            except Exception: pass
            return f"M{bit_index:02d} (내부비트)"

    def _open_out_delay_timer_selector(self):
        """OUT 스텝 - 타이머 기동후출력 타이머 선택"""
        if self.active_step_data is None:
            return
        ADD_KEY = "+ 새 타이머 추가"
        timer_names = [ADD_KEY] + list(self.timer_library.keys())
        current_ref = self.active_step_data.get("delay_timer_ref", None)
        if CardListDialog:
            def _delete_timer(name):
                if name in self.timer_library:
                    del self.timer_library[name]

            def _rename_timer(old_name, new_name):
                if old_name not in self.timer_library:
                    return
                self.timer_library[new_name] = self.timer_library.pop(old_name)
                for seq_steps in self.sequences.values():
                    if not isinstance(seq_steps, list):
                        continue
                    for step in seq_steps:
                        if step.get("timer_ref") == old_name:
                            step["timer_ref"] = new_name
                            step["name"] = new_name
                        if step.get("delay_timer_ref") == old_name:
                            step["delay_timer_ref"] = new_name

            dlg = CardListDialog(timer_names, current=current_ref, title="[딜레이] 타이머를 선택하세요", columns=4,
                                 on_delete=_delete_timer, on_rename=_rename_timer, parent=self)
            result = dlg.exec()
            selected = dlg.get_selected() if result == QDialog.Accepted else None
        else:
            selected = None

        if selected == ADD_KEY:
            self._add_timer_to_library()
            return

        if selected and selected in self.timer_library:
            time_sec = float(self.timer_library[selected])
            self.active_step_data["delay_timer_ref"] = selected
            self.active_step_data["delay_time"] = time_sec
            if hasattr(self, 'out_delay_timer_btn'):
                self.out_delay_timer_btn.setText(f"{selected}  ({time_sec:.1f}s)")

    def _on_out_type_changed(self, checked):
        """OUT 타입 변경 시 포트 리셋"""
        if not checked: return
        if self._is_loading: return
        if self.active_step_data is None: return
        if self.active_step_data.get("type") != "OUT": return
        out_type = self.out_type_grp.checkedId()
        self.active_step_data["out_type"] = out_type
        self.active_step_data["port"] = 0
        if hasattr(self, 'io_combo_btn'):
            self.io_combo_btn.setText(self._get_out_name(out_type, 0))

    def _on_in_type_changed(self, checked):
        """IN 타입 변경 시 포트 리셋"""
        if not checked: return
        if self._is_loading: return
        if self.active_step_data is None: return
        if self.active_step_data.get("type") != "IN": return
        in_type = self.in_type_grp.checkedId()
        self.active_step_data["in_type"] = in_type
        default_port = 100 if in_type == 2 else 0
        self.active_step_data["port"] = default_port
        if hasattr(self, 'io_combo_btn'):
            self.io_combo_btn.setText(self._get_input_name_by_index(default_port))

    def _on_tmr_mode_changed(self, checked=False):
        """TMR 모드 전환 (단순 대기 ↔ 신호 유지)"""
        if self._is_loading: return
        if self.active_step_data is None: return
        if self.active_step_data.get("type") != "TMR": return
        is_hold = hasattr(self, 'rb_tmr_hold') and self.rb_tmr_hold.isChecked()
        self.active_step_data["tmr_mode"] = "hold" if is_hold else "simple"
        if hasattr(self, 'tmr_mode_stack'):
            self.tmr_mode_stack.setCurrentIndex(1 if is_hold else 0)

    def _on_tmr_hold_type_changed(self, checked=False):
        """TMR 신호유지 - 입력 구분 변경 시 포트 리셋"""
        if not checked: return
        if self._is_loading: return
        if self.active_step_data is None: return
        in_type = self.tmr_hold_type_grp.checkedId()
        self.active_step_data["in_type"] = in_type
        self.active_step_data["port"] = 0
        if hasattr(self, 'tmr_hold_io_btn'):
            self.tmr_hold_io_btn.setText(self._get_input_name_by_index(0))

    def _on_tmr_hold_value_changed(self):
        """TMR 신호유지 - 상태(ON/OFF) 변경 저장"""
        if self._is_loading: return
        if self.active_step_data is None: return
        if hasattr(self, 'tmr_hold_rb_on'):
            self.active_step_data["on"] = self.tmr_hold_rb_on.isChecked()

    def _open_tmr_hold_io_selector(self):
        """TMR 신호유지 - 감시 신호 선택 팝업"""
        if self.active_step_data is None: return
        in_type = self.active_step_data.get("in_type", 0)
        current_port = self.active_step_data.get("port", 0)

        try:
            from utils.io_manager import IOManager
            mgr = IOManager.instance() if IOManager else None
        except Exception:
            mgr = None

        items = []
        port_indices = []
        if in_type == 0:
            for i in range(16):
                name = mgr.get_input_name(i) if mgr else f"X{i:02X}"
                items.append(f"X{i:02X}: {name}")
                port_indices.append(i)
            title = "시스템 입력 선택 (X00~X0F)"
        elif in_type == 1:
            for i in range(16):
                x_addr = 0x20 + i
                name = mgr.get_input_name(16 + i) if mgr else f"X{x_addr:02X}"
                items.append(f"X{x_addr:02X}: {name}")
                port_indices.append(x_addr)
            title = "밸브 입력 선택 (X20~X2F)"
        else:  # 내부 비트 M00~M31
            items = [f"M{i:02d} (내부비트)" for i in range(32)]
            port_indices = [100 + i for i in range(32)]
            title = "내부 비트 선택 (M00~M31)"

        current = None
        try:
            current = items[port_indices.index(current_port)]
        except ValueError:
            pass

        from ui.dialogs.sequence_utils import CardListDialog
        dlg = CardListDialog(items, current, title, columns=4, parent=self)
        if dlg.exec() == QDialog.Accepted:
            selected = dlg.get_selected()
            if selected and selected in items:
                port_idx = port_indices[items.index(selected)]
                self.active_step_data["port"] = port_idx
                if hasattr(self, 'tmr_hold_io_btn'):
                    self.tmr_hold_io_btn.setText(selected)

    def _get_valve_name_by_index(self, bit_index):
        """비트 인덱스로 밸브 이름 가져오기"""
        # ★ 내부 제어 비트 (100~131)
        if 100 <= bit_index <= 131:
            return f" M{bit_index-100:02d} (내부비트)"
        
        try:
            path = get_settings_path()
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    valve_config = settings.get("valve_config", [])
                    
                    # 비트 인덱스로 밸브 찾기
                    for cfg in valve_config:
                        if cfg.get("index", -1) == bit_index and cfg.get("enabled", True):
                            return cfg.get("name", f"밸브 {bit_index+1}")
        except Exception as e:
            print(f"[SequenceEditor] 밸브 이름 조회 실패: {e}")
        
        # 기본값
        return f"밸브 {bit_index+1}"
    
    def _get_input_name_by_index(self, port_index):
        """포트 번호로 입력 이름 가져오기 (IOManager 사용)"""
        if 100 <= port_index <= 131:
            bit_idx = port_index - 100
            # 내부비트 - 사용자 정의 이름 있으면 "M00: 감지비트"
            try:
                from utils.internal_bit_names import get_name
                nm = get_name(f"M{bit_idx:02d}")
                if nm:
                    return f"M{bit_idx:02d}: {nm}"
            except Exception: pass
            return f"M{bit_idx:02d} (내부비트)"

        try:
            from utils.io_manager import IOManager
            mgr = IOManager.instance() if IOManager else None
            if mgr:
                # port 0~15 → IOManager.inputs[0~15] (X00~X0F)
                # port 32~47 → IOManager.inputs[16~31] (X20~X2F)
                if 0 <= port_index < 16:
                    io_idx = port_index
                elif 32 <= port_index < 48:
                    io_idx = port_index - 16
                else:
                    io_idx = port_index
                name = mgr.get_input_name(io_idx)
                return f"X{port_index:02X}: {name}"
        except Exception:
            pass

        return f"X{port_index:02X}"
    
    def _get_mode_name_by_index(self, mode_index):
        """모드 번호로 모드 이름 가져오기 (ModeManager 사용)"""
        default_names = [
            "제품측 취출", "런너측 취출", "주행 대기", "하강 대기",
            "주행도중개방", "복귀도중개방", "안전도어 회피", "안전도어 회피2",
            "낙하측 반전", "주행도중 반전", "취출대기 반전", "고정측 취출",
            "제품 형내개방", "런너 형내개방", "에젝터 연동", "언더컷 취출모드",
            "척1 사용", "척1 감지", "척2 사용", "척2 감지",
            "척3 사용", "척3 감지", "척4 사용", "척4 감지",
            "흡착1 사용", "흡착1 감지", "흡착2 사용", "흡착2 감지",
            "흡착3 사용", "흡착3 감지", "흡착4 사용", "흡착4 감지",
            "2포인트 개방", "공정감시 모드"
        ]
        
        try:
            from utils.mode_manager import ModeManager
            mgr = ModeManager.instance() if ModeManager else None
            
            if mgr:
                name = mgr.get_name(mode_index)
                return f"[{mode_index:02d}] {name}"
            elif mode_index < len(default_names):
                return f"[{mode_index:02d}] {default_names[mode_index]}"
            else:
                return f"[{mode_index:02d}] User Mode {mode_index - 34 + 1}"
        except Exception as e:
            print(f"[SequenceEditor] 모드 이름 조회 실패: {e}")
            if mode_index < len(default_names):
                return f"[{mode_index:02d}] {default_names[mode_index]}"
            else:
                return f"[{mode_index:02d}] User Mode {mode_index - 34 + 1}"
    
    # =========================================================
    # ★ [신규] 화면 중앙 정렬
    # =========================================================
    
    def _center_on_screen(self):
        """다이얼로그를 화면 중앙에 배치"""
        screen = QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            x = (screen_geometry.width() - self.width()) // 2
            y = (screen_geometry.height() - self.height()) // 2
            self.move(x, y)
    
    # =========================================================
    # ★ [신규] 축 설정 로드
    # =========================================================
    
    def _load_enabled_axes(self):
        """
        settings.json에서 연결된 축 정보 로드
        반환: [True, True, True, False, ...] (8개)
        """
        try:
            path = get_settings_path()
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    axis_uses = settings.get("axis_uses", None)
                    
                    if axis_uses and len(axis_uses) == 8:
                        return axis_uses
        except Exception as e:
            print(f"[시퀀스 편집기] 축 설정 로드 실패: {e}")
        
        # 기본값: 전축 활성화
        return [True] * 8
