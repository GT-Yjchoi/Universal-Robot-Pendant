import random
from PySide6.QtCore import Qt, Signal, QEventLoop, QTimer
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QDialog, QFrame,
    QSizePolicy, QScrollArea, QScroller, QGridLayout,
    QScrollerProperties, QStyledItemDelegate, QInputDialog, QMessageBox,
    QGraphicsColorizeEffect
)

from widgets.glass_card import GlassCard
from ui.widgets.valve_tile import ValvePanel
from ui.dialogs.sequence_editor_qml import SequenceEditorQmlDialog
from ui.widgets.custom_inputs import TouchComboBox
from utils.languages import LanguageManager

# =========================================================================
# [기존 유지] 오버레이 방식 숫자 키패드
# =========================================================================
class NumberInputOverlay(QWidget):
    def __init__(self, current_val_str, precision=0, parent=None):
        super().__init__(parent)
        # QQuickWidget(QML) 위 자식 오버레이 첫입력 가로채임 방지 —
        # top-level 프레임리스 모달 (feedback-qquickwidget-overlay-input)
        self._bg_pixmap = parent.window().grab() if parent else None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog
                            | Qt.WindowStaysOnTopHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowState(Qt.WindowFullScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)

        self.precision = precision
        self.result_val = None
        self._event_loop = None
        
        layout = QVBoxLayout(self); layout.setAlignment(Qt.AlignCenter)
        container = QFrame(); container.setFixedSize(320, 450)
        container.setStyleSheet("QFrame { background-color: #1A1F2B; border: 2px solid #468CFF; border-radius: 12px; } QLabel { color: #FFD700; font-size: 28px; font-weight: bold; background: rgba(0,0,0,0.3); border: 1px solid #444; border-radius: 6px; padding: 5px; } QPushButton { background-color: #34495E; color: white; font-size: 22px; font-weight: bold; border: none; border-radius: 6px; } QPushButton:pressed { background-color: #468CFF; } QPushButton#btnCancel { background-color: #582F2F; border: 1px solid #C0392B; } QPushButton#btnOk { background-color: #2980B9; border: 1px solid #3498DB; }")
        
        vbox = QVBoxLayout(container); vbox.setSpacing(10); vbox.setContentsMargins(20, 20, 20, 20)
        self.display = QLabel(current_val_str); self.display.setAlignment(Qt.AlignRight | Qt.AlignVCenter); self.display.setFixedHeight(60); vbox.addWidget(self.display)
        
        grid = QGridLayout(); grid.setSpacing(8)
        keys = [('7',0,0),('8',0,1),('9',0,2),('4',1,0),('5',1,1),('6',1,2),('1',2,0),('2',2,1),('3',2,2),('0',3,0),('.',3,1),('←',3,2)]
        for text, r, c in keys:
            btn = QPushButton(text); btn.setFixedSize(80, 60); btn.setAttribute(Qt.WA_AcceptTouchEvents, True)
            if text == '.':
                if self.precision == 0: btn.setEnabled(False)
                btn.clicked.connect(self._on_dot)
            elif text == '←': btn.clicked.connect(self._on_backspace)
            else: btn.clicked.connect(lambda _, t=text: self._on_digit(t))
            grid.addWidget(btn, r, c)
        vbox.addLayout(grid)
        
        hbox = QHBoxLayout()
        btn_cancel = QPushButton("취소"); btn_cancel.setObjectName("btnCancel"); btn_cancel.setFixedHeight(50); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("확인"); btn_ok.setObjectName("btnOk"); btn_ok.setFixedHeight(50); btn_ok.clicked.connect(self.accept)
        hbox.addWidget(btn_cancel); hbox.addWidget(btn_ok); vbox.addLayout(hbox)
        layout.addWidget(container); self.first_input = True

    def _on_digit(self, digit):
        if self.first_input: self.display.setText(digit); self.first_input = False
        else: self.display.setText(self.display.text() + digit) if self.display.text() != "0" else self.display.setText(digit)
    def _on_dot(self):
        if self.first_input: self.display.setText("0."); self.first_input = False
        elif "." not in self.display.text(): self.display.setText(self.display.text() + ".")
    def _on_backspace(self):
        cur = self.display.text()
        self.display.setText(cur[:-1] if len(cur) > 1 else "0"); self.first_input = (len(cur) <= 1)
    def accept(self): self.result_val = self.display.text(); self._quit()
    def reject(self): self.result_val = None; self._quit()
    def _quit(self):
        if self._event_loop: self._event_loop.quit()
        self.close(); self.deleteLater()
    def paintEvent(self, event):
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        if self._bg_pixmap: p.drawPixmap(0, 0, self._bg_pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 180))
    def exec(self):
        self.show(); self.raise_(); self.activateWindow()
        self._event_loop = QEventLoop(); self._event_loop.exec(); return self.result_val

# =========================================================================
# [NEW] 자동운전 중 기억위치 미세조정 오버레이
# 값 라벨 클릭 시 열림. -1 / -0.1 / +0.1 / +1 버튼으로 즉시 가감산,
# on_adjust(delta) 콜백으로 호출자에게 델타 전달.
# 호출자는 범위검증·저장·PLC전송 후 set_value() 로 표시값만 갱신.
# =========================================================================
class FineAdjustOverlay(QWidget):
    def __init__(self, axis_name, initial_val, on_adjust, parent=None):
        super().__init__(parent)
        # QQuickWidget(QML) 위 자식 오버레이 첫입력 가로채임 방지 (top-level 모달)
        self._bg_pixmap = parent.window().grab() if parent else None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog
                            | Qt.WindowStaysOnTopHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowState(Qt.WindowFullScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)

        self._on_adjust = on_adjust  # callback(delta)
        self._event_loop = None

        layout = QVBoxLayout(self); layout.setAlignment(Qt.AlignCenter)
        container = QFrame(); container.setFixedSize(540, 280)
        container.setStyleSheet("""
            QFrame { background-color: #1A1F2B; border: 2px solid #468CFF; border-radius: 14px; }
            QLabel#title { color: #468CFF; font-size: 22px; font-weight: bold; background: transparent; border: none; }
            QLabel#value { color: #64FFDA; font-size: 40px; font-weight: 900; background: rgba(0,0,0,0.3);
                           border: 1px solid #555; border-radius: 8px; padding: 8px; }
            QPushButton { background: rgba(70,140,255,0.25); border: 1px solid #468CFF; border-radius: 8px;
                          color: white; font-size: 22px; font-weight: 900; }
            QPushButton:pressed { background: rgba(70,140,255,0.55); }
            QPushButton#close { background: #582F2F; border: 1px solid #C0392B; font-size: 18px; }
            QPushButton#close:pressed { background: #C0392B; }
        """)

        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(20, 16, 20, 16)
        vbox.setSpacing(12)

        lbl_title = QLabel(f"{axis_name}축 기억위치 미세조정"); lbl_title.setObjectName("title")
        lbl_title.setAlignment(Qt.AlignCenter)
        vbox.addWidget(lbl_title)

        self.lbl_value = QLabel(f"{initial_val:.3f} mm"); self.lbl_value.setObjectName("value")
        self.lbl_value.setAlignment(Qt.AlignCenter)
        self.lbl_value.setFixedHeight(72)
        vbox.addWidget(self.lbl_value)

        h = QHBoxLayout(); h.setSpacing(10)
        for delta in (-1.0, -0.1, 0.1, 1.0):
            btn = QPushButton(f"{delta:+g}"); btn.setFixedHeight(60)
            btn.clicked.connect(lambda _, d=delta: self._on_adjust(d))
            h.addWidget(btn)
        vbox.addLayout(h)

        btn_close = QPushButton("닫기"); btn_close.setObjectName("close"); btn_close.setFixedHeight(44)
        btn_close.clicked.connect(self._quit)
        vbox.addWidget(btn_close)

        layout.addWidget(container)

    def set_value(self, val):
        """호출자가 조정 후 갱신된 값 반영용."""
        self.lbl_value.setText(f"{val:.3f} mm")

    def _quit(self):
        if self._event_loop: self._event_loop.quit()
        self.close(); self.deleteLater()

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        if self._bg_pixmap: p.drawPixmap(0, 0, self._bg_pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 180))

    def exec(self):
        self.show(); self.raise_(); self.activateWindow()
        self._event_loop = QEventLoop(); self._event_loop.exec()


# -------------------------------------------------------------------------
# [Helper Classes]
# -------------------------------------------------------------------------
class ClickableLabel(QLabel):
    clicked = Signal(int, str) 
    def __init__(self, row_idx, col_type, text="", parent=None):
        super().__init__(text, parent); self.row_idx = row_idx; self.col_type = col_type; self.setCursor(Qt.PointingHandCursor)
    def mousePressEvent(self, event): self.clicked.emit(self.row_idx, self.col_type); super().mousePressEvent(event)

class PositionOrderDialog(QDialog):
    def __init__(self, current_names, parent=None):
        super().__init__(parent); self.name_list = list(current_names)
        # weston kiosk-shell 은 toplevel 을 풀스크린 강제 → resize() 무시되어
        # 레이아웃이 화면을 벗어남. OverlayDialog 와 동일하게 풀스크린 반투명
        # 백드롭 + 중앙 고정크기 content_frame 패턴으로.
        self._bg_pixmap = parent.window().grab() if parent else None
        self.setWindowTitle("위치 목록 순서 변경"); self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setWindowState(Qt.WindowFullScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        outer = QVBoxLayout(self); outer.setAlignment(Qt.AlignCenter)
        cf = QFrame(); cf.setObjectName("OrderCF"); cf.setFixedSize(520, 660)
        cf.setStyleSheet("QFrame#OrderCF { background: rgba(20, 30, 40, 250); border: 2px solid rgba(70, 140, 255, 120); border-radius: 12px; } QLabel { color: white; font-size: 18px; font-weight: bold; background: transparent; border: none; } QListWidget { background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; font-size: 18px; color: #EEE; } QListWidget::item { height: 50px; padding-left: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); } QListWidget::item:selected { background: rgba(70, 140, 255, 0.4); border: 1px solid #468CFF; color: white; } QPushButton { background: rgba(255,255,255,0.1); border: 1px solid gray; border-radius: 6px; color: white; height: 50px; font-size: 16px; font-weight: bold; } QPushButton:pressed { background: rgba(255,255,255,0.3); }")
        outer.addWidget(cf)
        layout = QVBoxLayout(cf); layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(QLabel("위치 명칭 보기 순서 변경")); layout.addWidget(QLabel("※ 실제 동작 순서는 변경되지 않습니다. (화면 표시용)"))
        self.list_widget = QListWidget()
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        QScroller.grabGesture(self.list_widget.viewport(), QScroller.TouchGesture)
        QScroller.grabGesture(self.list_widget.viewport(), QScroller.LeftMouseButtonGesture)
        layout.addWidget(self.list_widget); self._load_list()
        btn_layout = QHBoxLayout(); btn_up = QPushButton("▲ 위로"); btn_down = QPushButton("▼ 아래로"); btn_ok = QPushButton("적용 (Apply)"); btn_ok.setStyleSheet("background: rgba(70,140,255,0.4); border: 1px solid #468CFF;"); btn_cancel = QPushButton("취소")
        btn_up.clicked.connect(self._move_up); btn_down.clicked.connect(self._move_down); btn_ok.clicked.connect(self.accept); btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_up); btn_layout.addWidget(btn_down); btn_layout.addWidget(btn_cancel); btn_layout.addWidget(btn_ok); layout.addLayout(btn_layout)
    def paintEvent(self, e):
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        if self._bg_pixmap: p.drawPixmap(0, 0, self._bg_pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 150))
    def showEvent(self, e): super().showEvent(e); self.activateWindow(); self.raise_(); self.setFocus()
    def _load_list(self):
        self.list_widget.clear()
        for name in self.name_list: self.list_widget.addItem(QListWidgetItem(f"[P] {name}"))
    def _move_up(self):
        r = self.list_widget.currentRow(); 
        if r <= 0: return
        self.name_list[r], self.name_list[r-1] = self.name_list[r-1], self.name_list[r]; self._load_list(); self.list_widget.setCurrentRow(r - 1)
    def _move_down(self):
        r = self.list_widget.currentRow(); 
        if r < 0 or r >= self.list_widget.count() - 1: return
        self.name_list[r], self.name_list[r+1] = self.name_list[r+1], self.name_list[r]; self._load_list(); self.list_widget.setCurrentRow(r + 1)
    def get_ordered_names(self): return self.name_list

# -------------------------------------------------------------------------
# [PointNameCardOverlay] 위치 포인트 선택 네임카드 오버레이
# -------------------------------------------------------------------------
class PointNameCardOverlay(QWidget):
    point_selected = Signal(str)

    def __init__(self, ordered_points, current_point, parent=None):
        super().__init__(parent)
        # QQuickWidget(QML) 위 자식 오버레이 첫입력 가로채임 방지 (top-level 모달)
        self._bg_pixmap = parent.window().grab() if parent else None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog
                            | Qt.WindowStaysOnTopHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowState(Qt.WindowFullScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        popup = QFrame()
        popup.setFixedSize(520, 440)
        popup.setStyleSheet("QFrame { background-color: #1A1F2B; border: 2px solid #468CFF; border-radius: 14px; } QLabel { background: transparent; border: none; }")

        vbox = QVBoxLayout(popup)
        vbox.setContentsMargins(20, 16, 20, 20)
        vbox.setSpacing(12)

        # 제목 + 닫기
        title_row = QHBoxLayout()
        title_lbl = QLabel("[P] 위치 포인트 선택")
        title_lbl.setStyleSheet("color: #64FFDA; font-size: 20px; font-weight: bold;")
        btn_close = QPushButton("X")
        btn_close.setFixedSize(32, 32)
        btn_close.setStyleSheet("QPushButton { background: transparent; color: #FF4646; font-size: 16px; font-weight: bold; border: none; } QPushButton:hover { color: white; }")
        btn_close.clicked.connect(self.close)
        title_row.addWidget(title_lbl, 1)
        title_row.addWidget(btn_close)
        vbox.addLayout(title_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: rgba(255,255,255,0.2); border: none; max-height: 1px;")
        vbox.addWidget(sep)

        # 카드 그리드 (스크롤 가능)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        QScroller.grabGesture(scroll.viewport(), QScroller.TouchGesture)

        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_widget)
        grid.setSpacing(10)
        grid.setContentsMargins(4, 4, 4, 4)

        COLS = 2
        for i, name in enumerate(ordered_points):
            is_cur = (name == current_point)
            card = QPushButton(name)
            card.setFixedHeight(56)
            card.setCursor(Qt.PointingHandCursor)
            if is_cur:
                card.setStyleSheet("QPushButton { background-color: rgba(70,140,255,0.5); border: 2px solid #468CFF; border-radius: 8px; color: white; font-size: 18px; font-weight: bold; } QPushButton:pressed { background-color: rgba(70,140,255,0.8); }")
            else:
                card.setStyleSheet("QPushButton { background-color: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; color: #EEE; font-size: 18px; } QPushButton:hover { background-color: rgba(255,255,255,0.15); border: 1px solid #468CFF; } QPushButton:pressed { background-color: rgba(70,140,255,0.3); }")
            card.clicked.connect(lambda _, n=name: self._on_card(n))
            grid.addWidget(card, i // COLS, i % COLS)

        scroll.setWidget(grid_widget)
        vbox.addWidget(scroll, 1)
        layout.addWidget(popup)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        if self._bg_pixmap: p.drawPixmap(0, 0, self._bg_pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 180))

    def _on_card(self, name):
        self.point_selected.emit(name)
        self.close()

    def mousePressEvent(self, event):
        # 팝업 밖 클릭 시 닫기
        self.close()
        event.accept()

class ClickableListWidget(QListWidget):
    empty_clicked = Signal() 
    def __init__(self, parent=None):
        super().__init__(parent); self.setVerticalScrollMode(QListWidget.ScrollPerPixel); self.setFocusPolicy(Qt.NoFocus); self.setCursor(Qt.PointingHandCursor)
    def mousePressEvent(self, event):
        if self.count() == 0: self.empty_clicked.emit()
        super().mousePressEvent(event)

class CenterDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index): super().initStyleOption(option, index); option.displayAlignment = Qt.AlignCenter

class StepHighlightDelegate(QStyledItemDelegate):
    """현재 실행 중인 시퀀스 스텝을 하이라이트하는 delegate"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighted_row = -1

    def paint(self, painter, option, index):
        if index.row() == self.highlighted_row:
            painter.save()
            painter.fillRect(option.rect, QColor(0, 229, 255, 70))
            painter.restore()
        super().paint(painter, option, index)

# -------------------------------------------------------------------------
# [PagePosition Class]
# -------------------------------------------------------------------------
class PagePosition(GlassCard):
    sig_sequence_changed = Signal()

    def __init__(self, sequence_data=None, position_points=None, view_order_data=None, mode_data=None, timer_library=None, plc_client=None):
        super().__init__("")
        if hasattr(self, 'title_label'): self.title_label.hide()
        if self.layout(): self.layout().setContentsMargins(10, 5, 10, 10)

        self.plc_client = plc_client
        if self.plc_client:
            self.plc_client.sig_monitor_data.connect(self._update_realtime_values)

        self.raw_sequence_ref = sequence_data if sequence_data is not None else []
        self.position_points = position_points if position_points is not None else {}
        self.view_order_data = view_order_data if view_order_data is not None else []
        self.mode_data = mode_data if mode_data is not None else []
        self.timer_library = timer_library if timer_library is not None else {}
        
        self.sequences = {}
        if isinstance(self.raw_sequence_ref, list): self.sequences["Main"] = self.raw_sequence_ref
        elif isinstance(self.raw_sequence_ref, dict): self.sequences = self.raw_sequence_ref
        else: self.sequences["Main"] = []
            
        if "Main" not in self.sequences: self.sequences["Main"] = []
        self.current_seq_key = "Main" 

        self._init_points_from_sequence()
        self.lbl_saved_vals = []
        self.lbl_speed_vals = []
        self.lbl_curr_vals = []

        # [NEW] 축 행(Row) 숨김 제어를 위한 리스트
        self.axis_rows = []
        self._current_op_status = 0  # 0=정지, 1=자동, 2=확인

        self._init_ui()
        self._refresh_ui()

    def _init_points_from_sequence(self):
        for seq_list in self.sequences.values():
            for step in seq_list:
                if step.get("type") == "POS":
                    p_name = step.get("point_name", step.get("name", "Point"))
                    if not p_name: p_name = "Point_1"
                    if p_name not in self.position_points:
                        coords = step.get("coords", [0.0]*8)
                        speeds = step.get("speeds", [100.0]*8)
                        self.position_points[p_name] = {"coords": list(coords), "speeds": list(speeds)}

    def _init_ui(self):
        main_layout = QHBoxLayout()
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # [LEFT Panel]
        left_layout = QVBoxLayout()
        left_layout.setSpacing(8) 
        
        nav_layout = QHBoxLayout(); nav_layout.setSpacing(10)
        _nav_btn_style = ("QPushButton { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3); "
                          "border-radius: 6px; color: white; font-size: 18px; font-weight: bold; } "
                          "QPushButton:hover { background: rgba(255,255,255,0.18); border: 1px solid #468CFF; } "
                          "QPushButton:pressed { background: rgba(70,140,255,0.3); } "
                          "QPushButton:disabled { background: rgba(255,255,255,0.03); "
                          "border: 1px solid rgba(255,255,255,0.08); color: rgba(255,255,255,0.2); }")
        self.btn_prev = QPushButton("◀"); self.btn_prev.setFixedSize(45, 42); self.btn_prev.setStyleSheet(_nav_btn_style); self.btn_prev.clicked.connect(self._on_prev_point)
        # 내부 상태 관리용 (숨김)
        self.point_combo = TouchComboBox(); self.point_combo.setVisible(False); self.point_combo.setItemDelegate(CenterDelegate()); self.point_combo.currentIndexChanged.connect(self._on_combo_changed)
        # 표시용 버튼 - 클릭하면 네임카드 오버레이 팝업
        self.point_name_btn = QPushButton("위치 없음"); self.point_name_btn.setFixedHeight(42); self.point_name_btn.setCursor(Qt.PointingHandCursor)
        self.point_name_btn.setStyleSheet("QPushButton { background: rgba(255,255,255,0.1); border: 1px solid rgba(100,200,255,0.4); border-radius: 6px; color: white; font-size: 18px; font-weight: bold; } QPushButton:hover { background: rgba(70,140,255,0.2); border: 1px solid #468CFF; } QPushButton:pressed { background: rgba(70,140,255,0.3); } QPushButton:disabled { color: rgba(255,255,255,0.3); border: 1px solid rgba(255,255,255,0.1); }")
        self.point_name_btn.clicked.connect(self._show_name_card_overlay)
        self.btn_next = QPushButton("▶"); self.btn_next.setFixedSize(45, 42); self.btn_next.setStyleSheet(_nav_btn_style); self.btn_next.clicked.connect(self._on_next_point)
        self.btn_reorder = QPushButton("☰"); self.btn_reorder.setFixedSize(45, 42); self.btn_reorder.setStyleSheet("background: rgba(255,255,255,0.1); border: 1px solid gray; border-radius: 6px; font-size: 22px; color: white;"); self.btn_reorder.clicked.connect(self._on_reorder_clicked)

        nav_layout.addWidget(self.btn_prev); nav_layout.addWidget(self.point_name_btn, 1); nav_layout.addWidget(self.btn_reorder); nav_layout.addWidget(self.btn_next)
        left_layout.addLayout(nav_layout)

        data_frame = QFrame(); data_frame.setStyleSheet("background: rgba(0,0,0,0.15); border-radius: 10px;")
        grid = QGridLayout(data_frame); grid.setContentsMargins(10, 10, 10, 10); grid.setHorizontalSpacing(10); grid.setVerticalSpacing(10) 
        
        # [수정] 헤더 폰트 확대 (16px) + 명시적 투명 배경/무테두리 (박스 겹침 방지)
        headers = ["축", "현재위치", "기억위치", "속도%"]
        for c, h in enumerate(headers):
            lbl = QLabel(h); lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                "color: rgba(255,255,255,0.6); font-size: 16px; font-weight: bold;"
                "background: transparent; border: none;"
            )
            grid.addWidget(lbl, 0, c)
        grid.setColumnStretch(0, 0); grid.setColumnStretch(1, 5); grid.setColumnStretch(2, 5); grid.setColumnStretch(3, 2)

        axis_names = ["X", "Y", "Z", "Y2", "Z2", "θ", "R1", "R2"]
        
        def create_val_label(color, default_text, is_current=False, row_idx=0, val_type=None):
            box = QFrame(); bg_color = "rgba(255,255,255,0.12)" if is_current else "rgba(255,255,255,0.05)"; border_color = "rgba(100,255,218,0.5)" if is_current else "rgba(255,255,255,0.15)"
            # [수정] 박스 높이 확대 (45px)
            box.setStyleSheet(f"background: {bg_color}; border: 1px solid {border_color}; border-radius: 6px;"); box.setMinimumHeight(45); box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            h = QHBoxLayout(box); h.setContentsMargins(4, 2, 4, 2)
            if val_type: lbl = ClickableLabel(row_idx, val_type, default_text); lbl.clicked.connect(self._on_value_clicked) 
            else: lbl = QLabel(default_text)
            # [수정] 값 폰트 확대 (22px)
            lbl.setAlignment(Qt.AlignCenter); lbl.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: bold; border: none; background: transparent;")
            h.addWidget(lbl); return box, lbl

        for r, axis in enumerate(axis_names, start=1):
            row_idx = r - 1
            # [수정] 축 이름 폰트 확대 (20px) 및 높이 조정
            lbl_axis = QLabel(axis); lbl_axis.setAlignment(Qt.AlignCenter); 
            lbl_axis.setStyleSheet("background: rgba(255,255,255,0.1); border-radius: 4px; color: #DDD; font-weight: bold; font-size: 20px;")
            lbl_axis.setMinimumHeight(45)
            
            grid.addWidget(lbl_axis, r, 0)
            
            box_cur, lbl_cur = create_val_label("#FFFFFF", "0.00", is_current=True); grid.addWidget(box_cur, r, 1); self.lbl_curr_vals.append(lbl_cur)
            box_sav, lbl_sav = create_val_label("#64FFDA", "0.00", row_idx=row_idx, val_type="coords"); grid.addWidget(box_sav, r, 2); self.lbl_saved_vals.append(lbl_sav)
            box_spd, lbl_spd = create_val_label("#FFD280", "100", row_idx=row_idx, val_type="speed"); grid.addWidget(box_spd, r, 3); self.lbl_speed_vals.append(lbl_spd); grid.setRowStretch(r, 1)

            # [NEW] 숨김 제어를 위해 행별 위젯 저장
            self.axis_rows.append([lbl_axis, box_cur, box_sav, box_spd])

        data_scroll = QScrollArea()
        data_scroll.setWidget(data_frame)
        data_scroll.setWidgetResizable(True)
        data_scroll.setFrameShape(QFrame.NoFrame)
        data_scroll.setStyleSheet("background: transparent;")
        data_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        data_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        QScroller.grabGesture(data_scroll.viewport(), QScroller.TouchGesture)
        left_layout.addWidget(data_scroll, 1)
        self.btn_teach = QPushButton("현재 위치 기억 (TEACH)"); self.btn_teach.setProperty("class", "AutoControlBtn"); self.btn_teach.setProperty("variant", "start"); self.btn_teach.setMinimumHeight(55); self.btn_teach.setCursor(Qt.PointingHandCursor); self.btn_teach.clicked.connect(self._on_teach_clicked)
        self._teach_gray_effect = QGraphicsColorizeEffect(self.btn_teach)
        self._teach_gray_effect.setColor(QColor(160, 160, 160))
        self._teach_gray_effect.setStrength(1.0)
        self._teach_gray_effect.setEnabled(False)
        self.btn_teach.setGraphicsEffect(self._teach_gray_effect)
        left_layout.addWidget(self.btn_teach)

        left_widget = QWidget(); left_widget.setLayout(left_layout)
        
        # [MIDDLE Panel]
        mid_layout = QVBoxLayout(); mid_layout.setSpacing(10)
        seq_select_layout = QHBoxLayout(); mid_title = QLabel("동작 순서"); mid_title.setProperty("class", "PosPanelTitle"); seq_select_layout.addWidget(mid_title)
        self.seq_selector = TouchComboBox(); self.seq_selector.setMinimumWidth(120); self.seq_selector.setFixedHeight(40)
        self.seq_selector.setStyleSheet(
            "QComboBox { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3); "
            "border-radius: 4px; color: white; font-weight: bold; padding-left: 10px; font-size: 16px; }"
            "QComboBox QAbstractItemView { background: #141E28; color: white; "
            "selection-background-color: #468CFF; font-size: 20px; font-weight: bold; padding: 5px; outline: none; }"
            "QComboBox QAbstractItemView::item { min-height: 42px; padding-left: 12px; }"
            "QComboBox QAbstractItemView::item:hover { background: transparent; color: white; }"
            "QComboBox QAbstractItemView::item:selected { background: #468CFF; color: white; }"
        )
        self.seq_selector.currentIndexChanged.connect(self._on_seq_selector_changed)
        seq_select_layout.addWidget(self.seq_selector); mid_layout.addLayout(seq_select_layout)
        
        self.preview_list = ClickableListWidget(); self.preview_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.preview_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_list.setStyleSheet("QListWidget { background: rgba(0,0,0,0.2); border: 2px solid rgba(255,255,255,0.1); border-radius: 8px; outline: none; } QListWidget::item { height: 40px; padding-left: 8px; color: #BBB; font-size: 14px; border-bottom: 1px solid rgba(255,255,255,0.05); }")
        self._step_delegate = StepHighlightDelegate(self.preview_list)
        self.preview_list.setItemDelegate(self._step_delegate)
        QScroller.grabGesture(self.preview_list.viewport(), QScroller.TouchGesture); QScroller.grabGesture(self.preview_list.viewport(), QScroller.LeftMouseButtonGesture)
        self.preview_list.itemClicked.connect(self._open_sequence_editor); self.preview_list.empty_clicked.connect(self._open_sequence_editor)
        mid_layout.addWidget(self.preview_list, 1); mid_widget = QWidget(); mid_widget.setLayout(mid_layout)
        
        # [RIGHT Panel]
        self.valve_panel = ValvePanel(self.plc_client)
        
        # [LAYOUT]
        main_layout.addWidget(left_widget, 4)
        main_layout.addWidget(mid_widget, 4)
        main_layout.addWidget(self.valve_panel, 2)
        self.body.addLayout(main_layout)

    def showEvent(self, event):
        self._refresh_ui()
        # 페이지 진입 시 항상 첫 번째 포인트로 이동
        if self.point_combo.isEnabled() and self.point_combo.count() > 0:
            self.point_combo.setCurrentIndex(0)
        super().showEvent(event)
        # 화면 보일 때마다 사용 축 / 런너암 버튼 확인
        QTimer.singleShot(0, self._check_axis_visibility)

    def _check_axis_visibility(self):
        """PLC에서 축 사용 설정을 읽어 미사용 축 숨김"""
        if not self.plc_client or not self.plc_client.is_connected: return
        try:
            data = self.plc_client.read_words(0x09, self.plc_client.AXIS_PARAM_ADDR, 1)
            if data:
                use_mask = data[0]
                for i, widgets in enumerate(self.axis_rows):
                    is_used = bool((use_mask >> i) & 1)
                    for w in widgets:
                        w.setVisible(is_used)
        except Exception as e:
            print(f"[Position] 축 표시 갱신 실패: {e}")

    def _refresh_ui(self):
        self.seq_selector.blockSignals(True)
        self.seq_selector.clear()
        
        keys = sorted([k for k in self.sequences.keys() if k != "Main"])
        all_keys = ["Main"] + keys
        self.seq_selector.addItems(all_keys)
        
        idx = self.seq_selector.findText(self.current_seq_key)
        if idx >= 0: self.seq_selector.setCurrentIndex(idx)
        else: self.seq_selector.setCurrentIndex(0)
        self.seq_selector.blockSignals(False)

        self._sync_points_combobox()
        self._update_preview_list()
        self._on_combo_changed(self.point_combo.currentIndex())

    def _on_seq_selector_changed(self, idx):
        key = self.seq_selector.currentText()
        if key in self.sequences:
            self.current_seq_key = key
            self._update_preview_list()

    def _open_sequence_editor(self):
        dlg = SequenceEditorQmlDialog(
            sequence_data=self.sequences,
            position_points=self.position_points,
            timer_library=self.timer_library,
            plc_client=self.plc_client,
            mode_data=self.mode_data,
            parent=self
        )
        if dlg.exec() == QDialog.Accepted:
            new_seqs = dlg.get_sequence_data()
            new_points = dlg.get_position_points()
            
            self.sequences.clear()
            self.sequences.update(new_seqs)
            
            if isinstance(self.raw_sequence_ref, list):
                self.raw_sequence_ref.clear()
                if "Main" in self.sequences:
                    self.raw_sequence_ref.extend(self.sequences["Main"])
            
            self.position_points.clear()
            self.position_points.update(new_points)
            
            self._refresh_ui()
            self.sig_sequence_changed.emit()

    def _update_realtime_values(self, data):
        if not self.isVisible(): return
        if isinstance(data, dict):
            axis_data = data.get('axis_pos', [])
        else:
            axis_data = data

        for i, val in enumerate(axis_data):
            if i < len(self.lbl_curr_vals):
                self.lbl_curr_vals[i].setText(f"{val:.3f}")

        # 현재 실행 중인 스텝 하이라이트 (자동운전 중일 때만)
        op_status = data.get('op_status', 0) if isinstance(data, dict) else 0
        current_step = data.get('current_step', -1) if isinstance(data, dict) else -1

        # 현재 운전 상태 추적 (기억위치 클릭 시 오버레이 분기용)
        self._current_op_status = op_status
        self._update_teach_button_state()

        # op_status: 1=자동, 2=확인운전 → 시퀀스 실행 중
        if op_status in (1, 2):
            # 현재 실행 중인 슬롯으로 드롭다운 자동 전환 (동작순서 추종)
            current_slot = data.get('sub_seq_idx', 0) if isinstance(data, dict) else 0
            target_name = self._get_seq_name_by_slot(current_slot)
            if target_name and target_name != self.current_seq_key and target_name in self.sequences:
                idx = self.seq_selector.findText(target_name)
                if idx >= 0:
                    self.seq_selector.blockSignals(True)
                    self.seq_selector.setCurrentIndex(idx)
                    self.seq_selector.blockSignals(False)
                self.current_seq_key = target_name
                self._update_preview_list()
                self._last_highlighted_step = None   # 하이라이트 재계산 유도
            self._highlight_step(current_step)
        else:
            self._highlight_step(-1)

    def _get_seq_name_by_slot(self, slot_id):
        """PLC 슬롯 번호 → 시퀀스 이름 매핑 (page_timer._sync_steps_time와 동일 규칙)"""
        MONITOR_KEY = "Monitor"
        if slot_id == 0:
            return "Main"
        if slot_id == 39:
            return MONITOR_KEY if MONITOR_KEY in self.sequences else None
        reserved = {"Main", MONITOR_KEY}
        subs = sorted([k for k in self.sequences.keys() if k not in reserved])
        idx = slot_id - 1
        if 0 <= idx < len(subs):
            return subs[idx]
        return None

    def _highlight_step(self, step_idx):
        """preview_list에서 현재 실행 중인 스텝을 하이라이트.
        step_idx는 PLC 기준(COMMENT 제외) 인덱스이므로 리스트 행으로 변환한다."""
        list_row = -1
        if step_idx >= 0:
            n = 0
            for i, s in enumerate(self.sequences.get(self.current_seq_key, [])):
                if s.get("type") == "COMMENT":
                    continue
                if n == step_idx:
                    list_row = i
                    break
                n += 1

        if getattr(self, '_last_highlighted_step', None) == list_row:
            return
        self._last_highlighted_step = list_row

        self._step_delegate.highlighted_row = list_row
        self.preview_list.viewport().update()

        # 자동 스크롤: 현재 스텝이 보이도록
        if 0 <= list_row < self.preview_list.count():
            self.preview_list.scrollToItem(
                self.preview_list.item(list_row),
                QListWidget.PositionAtCenter
            )

    def _show_name_card_overlay(self):
        if not self.point_combo.isEnabled() or self.point_combo.count() == 0:
            return
        ordered = [self.point_combo.itemText(i) for i in range(self.point_combo.count())]
        current = self.point_combo.currentText()
        overlay = PointNameCardOverlay(ordered, current, parent=self)
        overlay.point_selected.connect(self._on_point_selected_from_card)
        overlay.show()
        overlay.raise_()

    def _on_point_selected_from_card(self, name):
        idx = self.point_combo.findText(name)
        if idx >= 0:
            self.point_combo.setCurrentIndex(idx)

    def _on_reorder_clicked(self):
        dlg = PositionOrderDialog(self.view_order_data, self)
        if dlg.exec() == QDialog.Accepted:
            new_order = dlg.get_ordered_names()
            self.view_order_data.clear()
            self.view_order_data.extend(new_order)
            self._sync_points_combobox()
            self._on_combo_changed(0)
            self.sig_sequence_changed.emit()

    def _get_mode_name(self, idx):
        default_names = [
            "제품측 취출", "런너측 취출", "주행 대기", "하강 대기",
            "주행도중개방", "복귀도중개방", "안전도어 회피", "안전도어 회피2",
            "낙하측 반전", "주행도중 반전", "취출대기 반전", "고정측 취출",
            "제품 형내개방", "런너 형내개방", "에젝터 연동", "언더컷 취출모드",
            "척1 사용", "척1 감지", "척2 사용", "척2 감지",
            "척3 사용", "척3 감지", "척4 사용", "척4 감지",
            "흡착1 사용", "흡착1 감지", "흡착2 사용", "흡착2 감지",
            "흡착3 사용", "흡착3 감지", "흡착4 사용", "흡착4 감지",
            "2포인트 개방", "공정감시 모드",
        ]
        try:
            from utils.mode_manager import ModeManager
            mgr = ModeManager.instance()
            if mgr:
                return mgr.get_name(idx)
        except Exception:
            pass
        return default_names[idx] if idx < len(default_names) else f"User Mode {idx - 33}"

    def _is_point_visible(self, name):
        """포인트의 visible_mode 조건에 따라 현재 표시 여부 반환"""
        vm = self.position_points.get(name, {}).get("visible_mode", -1)
        # 구버전 int 형식 하위 호환
        if isinstance(vm, int):
            if vm < 0:
                return True
            return bool(self.mode_data[vm]) if self.mode_data and vm < len(self.mode_data) else False
        # 신규 list 형식: 빈 리스트 = 항상 표시, 아니면 OR 조건
        if not vm:
            return True
        return any(bool(self.mode_data[i]) for i in vm if self.mode_data and i < len(self.mode_data))

    def _sync_points_combobox(self):
        current_text = self.point_combo.currentText()
        self.point_combo.blockSignals(True)
        self.point_combo.clear()
        all_points = sorted(list(self.position_points.keys()))
        # view_order 동기화 (실제 표시 목록 업데이트)
        valid_custom = [n for n in self.view_order_data if n in all_points]
        new_names = [n for n in all_points if n not in valid_custom]
        self.view_order_data.clear(); self.view_order_data.extend(valid_custom + new_names)
        # 모드 조건 필터링
        visible_points = [n for n in self.view_order_data if self._is_point_visible(n)]
        if not visible_points:
            self.point_combo.addItem("위치 없음"); self.point_combo.setEnabled(False)
            self.point_name_btn.setText("위치 없음"); self.point_name_btn.setEnabled(False)
        else:
            self.point_name_btn.setEnabled(True)
            self.point_combo.setEnabled(True); self.point_combo.addItems(visible_points)
            idx = self.point_combo.findText(current_text)
            self.point_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.point_combo.blockSignals(False)

    def _update_preview_list(self):
        self._last_highlighted_step = None  # 리스트 갱신 시 하이라이트 초기화
        self.preview_list.clear()
        current_steps = self.sequences.get(self.current_seq_key, [])
        step_num = 0
        for step in current_steps:
            stype = step.get("type", "")
            if stype == "COMMENT":
                item = QListWidgetItem(f"// {step.get('text', '')}")
                item.setForeground(QBrush(QColor("#FFD700")))
                self.preview_list.addItem(item)
                continue
            step_num += 1
            name = step.get("name", "Unknown")
            if stype == "POS":
                p_name = step.get("point_name", "")
                if p_name and p_name != name:
                    name = f"{name}  ({p_name})"
            elif stype == "CALL":
                tgt = step.get("target_seq", "")
                if tgt:
                    name = f"{name}  ({tgt})"
            elif stype == "OUT":
                out_type = int(step.get("out_type", 0))
                port = int(step.get("port", 0))
                on_val = step.get("on", step.get("on_off", False))
                port_name = self._out_port_name(out_type, port)
                name = f"{name}  ({port_name} {'ON' if on_val else 'OFF'})"
            elif stype == "IN":
                port = int(step.get("port", step.get("io_index", 0)))
                on_val = step.get("on", step.get("on_off", True))
                port_name = self._in_port_name(port)
                name = f"{name}  ({port_name} {'ON' if on_val else 'OFF'})"
            elif stype == "JMP":
                tgt_idx = int(step.get("target_idx", 0))
                tgt_name = self._jmp_target_name(current_steps, tgt_idx)
                if tgt_name:
                    name = f"{name}  ({tgt_name})"
            elif stype == "TMR":
                ref = step.get("timer_ref", "")
                if ref:
                    name = f"{name}  ({ref})"
            self.preview_list.addItem(f"[{step_num:02d}] {name}")

    def _out_port_name(self, out_type, bit_index):
        """OUT 스텝 포트 표시 이름. IOManager + 내부비트 사용자 정의 반영."""
        try:
            from utils.io_manager import IOManager
            mgr = IOManager.instance()
            if out_type == 0:
                return f"Y{bit_index:02X}: {mgr.get_output_name(bit_index)}"
            elif out_type == 1:
                return f"Y{0x20+bit_index:02X}: {mgr.get_output_name(16+bit_index)}"
        except Exception:
            pass
        if out_type == 0:
            return f"Y{bit_index:02X}"
        if out_type == 1:
            return f"Y{0x20+bit_index:02X}"
        # 내부비트 (out_type == 2)
        try:
            from utils.internal_bit_names import get_name
            nm = get_name(f"M{bit_index:02d}")
            if nm:
                return f"M{bit_index:02d}: {nm}"
        except Exception:
            pass
        return f"M{bit_index:02d}"

    def _in_port_name(self, port_index):
        """IN 스텝 포트 표시 이름."""
        # 내부비트
        if 100 <= port_index <= 131:
            bit_idx = port_index - 100
            try:
                from utils.internal_bit_names import get_name
                nm = get_name(f"M{bit_idx:02d}")
                if nm:
                    return f"M{bit_idx:02d}: {nm}"
            except Exception:
                pass
            return f"M{bit_idx:02d}"
        # 시스템/밸브 입력
        try:
            from utils.io_manager import IOManager
            mgr = IOManager.instance()
            if 0 <= port_index < 16:
                return f"X{port_index:02X}: {mgr.get_input_name(port_index)}"
            if 32 <= port_index < 48:
                return f"X{port_index:02X}: {mgr.get_input_name(port_index - 16)}"
        except Exception:
            pass
        return f"X{port_index:02X}" if port_index < 100 else f"포트{port_index}"

    def _jmp_target_name(self, current_steps, target_idx):
        """현재 시퀀스에서 COMMENT 제외 target_idx 번째 스텝의 name 반환."""
        n = 0
        for step in current_steps:
            if step.get("type") == "COMMENT":
                continue
            if n == target_idx:
                return step.get("name", f"스텝{target_idx}")
            n += 1
        return f"스텝{target_idx}"

    def _on_prev_point(self):
        idx = self.point_combo.currentIndex()
        if idx > 0: self.point_combo.setCurrentIndex(idx - 1)

    def _on_next_point(self):
        idx = self.point_combo.currentIndex()
        if idx < self.point_combo.count() - 1: self.point_combo.setCurrentIndex(idx + 1)

    def _on_combo_changed(self, idx):
        count = self.point_combo.count()
        self.btn_prev.setEnabled(idx > 0); self.btn_next.setEnabled(idx < count - 1)
        selected_point = self.point_combo.currentText()
        if not self.point_combo.isEnabled() or not selected_point or selected_point == "위치 없음":
            self.point_name_btn.setText("위치 없음")
            self._clear_display(); return
        self.point_name_btn.setText(selected_point)

        if selected_point in self.position_points:
            data = self.position_points[selected_point]
            coords = data.get("coords", [0.0]*8)
            speeds = data.get("speeds", [100.0]*8)
            for i in range(8):
                val = coords[i] if i < len(coords) else 0.0
                spd = speeds[i] if i < len(speeds) else 100.0
                self.lbl_saved_vals[i].setText(f"{val:.3f}")
                self.lbl_speed_vals[i].setText(f"{spd:.0f}")
        else: self._clear_display()

    def _on_value_clicked(self, row_idx, col_type):
        if not self.point_combo.isEnabled(): return
        selected_point = self.point_combo.currentText()
        if selected_point not in self.position_points: return

        # [NEW] 자동/확인운전 중 기억위치는 미세조정 오버레이로 분기
        if col_type == "coords" and self._current_op_status in (1, 2):
            self._open_fine_adjust_overlay(selected_point, row_idx)
            return

        current_val_str = ""
        if col_type == "coords": current_val_str = self.lbl_saved_vals[row_idx].text()
        elif col_type == "speed": current_val_str = self.lbl_speed_vals[row_idx].text()
            
        prec = 3 if col_type == "coords" else 0
        dlg = NumberInputOverlay(current_val_str, prec, parent=self.window())
        new_val_str = dlg.exec()
        if new_val_str is None: return

        try: new_val = float(new_val_str)
        except ValueError: return

        # 속도: 1~100 % 는 기존대로 클램프
        if col_type == "speed":
            try:
                old_speed = int(float(self.lbl_speed_vals[row_idx].text()))
            except Exception:
                old_speed = 0
            new_val = max(1, min(100, int(new_val)))
        elif col_type == "coords":
            # 기억위치: 0 ~ 스트로크 한계(mm) 검증. 벗어나면 팝업 후 중단
            from utils.axis_limits import get_axis_strokes
            stroke = get_axis_strokes()[row_idx] if 0 <= row_idx < 8 else 1000.0
            if new_val < 0.0 or new_val > stroke:
                try:
                    from ui.dialogs.sequence_utils import DarkMessageDialog
                    DarkMessageDialog(
                        "입력 범위 초과",
                        f"스트로크 한계를 벗어났습니다.\n허용 범위: 0 ~ {stroke:.3f} mm\n입력값: {new_val:.3f} mm",
                        is_error=True, parent=self.window()
                    ).exec()
                except Exception as e:
                    print(f"[Position] 범위초과 팝업 실패: {e}")
                return

        if col_type == "coords":
            self.position_points[selected_point]["coords"][row_idx] = new_val
            for seq in self.sequences.values():
                for step in seq:
                    if step.get("type") == "POS":
                        p_name = step.get("point_name", step.get("name"))
                        if p_name == selected_point:
                            if "coords" in step: step["coords"][row_idx] = new_val

        elif col_type == "speed":
            if "speeds" not in self.position_points[selected_point]:
                self.position_points[selected_point]["speeds"] = [100]*8
            self.position_points[selected_point]["speeds"][row_idx] = new_val

        if self.plc_client and self.plc_client.is_connected:
            try:
                sorted_names = sorted(list(self.position_points.keys()))
                point_idx = sorted_names.index(selected_point)
                base_addr = self.plc_client.POINT_BASE_ADDR + (point_idx * self.plc_client.POINT_SIZE)
                if col_type == "coords":
                    target_addr = base_addr + 2 + (row_idx * 2)
                    send_val = int(new_val * 1000)
                    self.plc_client.write_dint(0x09, target_addr, send_val)
                elif col_type == "speed":
                    target_addr = base_addr + 18 + row_idx
                    send_val = int(new_val)
                    self.plc_client.write_words(0x09, target_addr, [send_val])
            except Exception as e:
                print(f"[Position] PLC 시퀀스 값 전송 실패: {e}")

        self._on_combo_changed(self.point_combo.currentIndex())
        self.sig_sequence_changed.emit()

        # 조작 이력 기록
        try:
            from utils.op_history import record as op_record
            axis_names = ["X", "Y", "Z", "Y2", "Z2", "θ", "R1", "R2"]
            axis = axis_names[row_idx] if 0 <= row_idx < 8 else f"축{row_idx+1}"
            if col_type == "coords":
                op_record("POS", f"{selected_point} {axis}축 기억위치 변경 → {new_val:.3f} mm")
            elif col_type == "speed":
                op_record("SPEED", f"{selected_point} {axis}축 속도 {old_speed} → {new_val} %")
        except Exception: pass

    def _open_fine_adjust_overlay(self, selected_point, row_idx):
        """자동/확인운전 중 기억위치 미세조정 오버레이 열기."""
        coords = self.position_points[selected_point].setdefault("coords", [0.0]*8)
        cur = coords[row_idx] if row_idx < len(coords) else 0.0
        axis_names = ["X", "Y", "Z", "Y2", "Z2", "θ", "R1", "R2"]
        axis_name = axis_names[row_idx] if 0 <= row_idx < 8 else f"{row_idx+1}"

        overlay = FineAdjustOverlay(axis_name, cur, on_adjust=None, parent=self)

        def _apply(delta):
            # 콜백 안에서 overlay 와 row_idx, selected_point 캡쳐
            self._apply_fine_adjust(selected_point, row_idx, delta, overlay)

        overlay._on_adjust = _apply
        overlay.exec()

    def _apply_fine_adjust(self, selected_point, row_idx, delta, overlay):
        """미세조정 버튼 1회 클릭 처리: 범위검증 → 저장 → PLC전송 → UI 갱신."""
        if selected_point not in self.position_points: return
        coords = self.position_points[selected_point].setdefault("coords", [0.0]*8)
        cur = coords[row_idx] if row_idx < len(coords) else 0.0
        new_val = round(cur + delta, 3)

        from utils.axis_limits import get_axis_strokes
        stroke = get_axis_strokes()[row_idx] if 0 <= row_idx < 8 else 1000.0
        if new_val < 0.0 or new_val > stroke:
            from ui.dialogs.sequence_utils import DarkMessageDialog
            DarkMessageDialog(
                "입력 범위 초과",
                f"스트로크 한계를 벗어났습니다.\n허용 범위: 0 ~ {stroke:.3f} mm\n입력값: {new_val:.3f} mm",
                is_error=True, parent=self.window()
            ).exec()
            return

        coords[row_idx] = new_val
        # 시퀀스 스텝의 coords 도 동기화
        for seq in self.sequences.values():
            for step in seq:
                if step.get("type") == "POS":
                    p_name = step.get("point_name", step.get("name"))
                    if p_name == selected_point and "coords" in step:
                        step["coords"][row_idx] = new_val

        # PLC 즉시 전송
        if self.plc_client and self.plc_client.is_connected:
            try:
                sorted_names = sorted(list(self.position_points.keys()))
                point_idx = sorted_names.index(selected_point)
                base_addr = self.plc_client.POINT_BASE_ADDR + (point_idx * self.plc_client.POINT_SIZE)
                target_addr = base_addr + 2 + (row_idx * 2)
                self.plc_client.write_dint(0x09, target_addr, int(new_val * 1000))
            except Exception as e:
                print(f"[Position] 미세조정 PLC 전송 실패: {e}")

        # UI 갱신
        self.lbl_saved_vals[row_idx].setText(f"{new_val:.3f}")
        if overlay is not None:
            overlay.set_value(new_val)
        self.sig_sequence_changed.emit()

        # 조작 이력 (자동 중 미세조정)
        try:
            from utils.op_history import record as op_record
            axis_names = ["X", "Y", "Z", "Y2", "Z2", "θ", "R1", "R2"]
            axis = axis_names[row_idx] if 0 <= row_idx < 8 else f"축{row_idx+1}"
            op_record("POS", f"(자동중) {selected_point} {axis}축 미세조정 {delta:+g} → {new_val:.3f} mm")
        except Exception: pass

    def _clear_display(self):
        for i in range(8):
            self.lbl_saved_vals[i].setText("---"); self.lbl_speed_vals[i].setText("-")

    def _update_teach_button_state(self):
        is_auto = self._current_op_status in (1, 2)
        if self.btn_teach.isEnabled() == (not is_auto):
            return
        self.btn_teach.setEnabled(not is_auto)
        self._teach_gray_effect.setEnabled(is_auto)

    def _on_teach_clicked(self):
        if self._current_op_status in (1, 2): return
        if not self.point_combo.isEnabled(): return
        target_point_name = self.point_combo.currentText()
        if target_point_name not in self.position_points: return

        new_coords = []
        for lbl in self.lbl_curr_vals:
            try: val = float(lbl.text())
            except ValueError: val = 0.0
            new_coords.append(val)
        
        self.position_points[target_point_name]["coords"] = list(new_coords)
        
        for seq in self.sequences.values():
            for step in seq:
                if step.get("type") == "POS":
                    p_name = step.get("point_name", step.get("name"))
                    if p_name == target_point_name: step["coords"] = list(new_coords)
        
        if self.plc_client and self.plc_client.is_connected:
            try:
                sorted_names = sorted(list(self.position_points.keys()))
                point_idx = sorted_names.index(target_point_name)
                base_addr = self.plc_client.POINT_BASE_ADDR + (point_idx * self.plc_client.POINT_SIZE)
                for i, val in enumerate(new_coords):
                    target_addr = base_addr + 2 + (i * 2)
                    send_val = int(val * 1000)
                    self.plc_client.write_dint(0x09, target_addr, send_val)
            except Exception as e:
                print(f"[Position] PLC 포지션 값 전송 실패: {e}")

        self._on_combo_changed(self.point_combo.currentIndex())
        self.sig_sequence_changed.emit()

        # 티칭 후 자동으로 다음 포인트로 이동
        next_idx = self.point_combo.currentIndex() + 1
        if next_idx < self.point_combo.count():
            self.point_combo.setCurrentIndex(next_idx)

