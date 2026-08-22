"""
PoC: 동작모드 페이지 QML(GPU) 버전.

- UI: PageMode.qml (Qt Quick GridView = GPU 씬그래프 + 키네틱 스크롤)
- 로직: 기존 PageMode 와 동일 (인터록 mandatory/exclusive, PLC 송신,
  ModeManager 이름, op_history) — 전부 Python 유지.
- main_window 의 PageMode 와 생성자/메서드 호환 (drop-in).

QWidget 스택에 QQuickWidget 으로 임베드 → 기존 앱에 점진 이식 가능.
"""
import json
import os

from PySide6.QtCore import (Qt, QObject, Signal, Slot, QUrl,
                            QAbstractListModel, QModelIndex, QByteArray)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget
from PySide6.QtQuickWidgets import QQuickWidget

from utils.json_utils import load_json, save_json
from utils.paths import get_settings_path as _get_settings_path

try:
    from utils.mode_manager import ModeManager
except ImportError:
    ModeManager = None
TOTAL_SLOTS = 44
_QML_PATH = os.path.join(os.path.dirname(__file__), "PageMode.qml")

_R_NAME = Qt.UserRole + 1
_R_CHECKED = Qt.UserRole + 2


class ModeTileModel(QAbstractListModel):
    """44 슬롯 (name, checked) — QML GridView 모델."""

    def __init__(self, mode_data, name_fn, parent=None):
        super().__init__(parent)
        self._mode = mode_data
        self._name_fn = name_fn

    def rowCount(self, parent=QModelIndex()):
        return TOTAL_SLOTS

    def roleNames(self):
        return {_R_NAME: QByteArray(b"name"),
                _R_CHECKED: QByteArray(b"checked")}

    def data(self, index, role):
        i = index.row()
        if not (0 <= i < TOTAL_SLOTS):
            return None
        if role == _R_NAME:
            return self._name_fn(i)
        if role == _R_CHECKED:
            return bool(self._mode[i]) if i < len(self._mode) else False
        return None

    def refresh_row(self, i):
        ix = self.index(i, 0)
        self.dataChanged.emit(ix, ix, [_R_NAME, _R_CHECKED])

    def refresh_all(self):
        if TOTAL_SLOTS:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(TOTAL_SLOTS - 1, 0),
                                  [_R_NAME, _R_CHECKED])


class ModeBackend(QObject):
    """QML → Python: 토글/롱프레스. 인터록·PLC 로직은 PageMode 와 동일."""

    def __init__(self, page):
        super().__init__(page)
        self._p = page

    @Slot(int)
    def toggle(self, idx):
        self._p._toggle_mode(idx)

    @Slot(int)
    def longPress(self, idx):
        self._p._rename_mode(idx)


class PageModeQml(QWidget):
    """PageMode 의 QML(GPU) 드롭인 대체. 생성자/메서드 호환."""

    _SETTINGS_PATH = _get_settings_path()

    def __init__(self, mode_data=None, plc_client=None):
        super().__init__()
        self.plc_client = plc_client
        self.mode_data = mode_data if mode_data is not None else []
        if len(self.mode_data) < TOTAL_SLOTS:
            self.mode_data.extend([False] * (TOTAL_SLOTS - len(self.mode_data)))

        (self.interlock_groups, self.interlock_mandatory,
         self.interlock_exclusive) = self._load_interlock_groups()

        self._model = ModeTileModel(self.mode_data, self._get_mode_name, self)
        self._backend = ModeBackend(self)

        self._view = QQuickWidget(self)
        self._view.setResizeMode(QQuickWidget.SizeRootObjectToView)
        # QQuickWidget 기본 clear color = 흰색. 반투명 글래스 QML 루트가
        # 그 위에 깔리면 뿌옇게 됨 → 테마 #Root 다크로 맞춰 합성.
        self._view.setClearColor(QColor("#16202B"))
        ctx = self._view.rootContext()
        ctx.setContextProperty("modeModel", self._model)
        ctx.setContextProperty("backend", self._backend)
        self._view.setSource(QUrl.fromLocalFile(_QML_PATH))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)

        if ModeManager:
            ModeManager.instance().sig_names_changed.connect(self.refresh_ui)

    # ---- 로직 (PageMode 와 동일) ------------------------------------
    def _get_mode_name(self, idx):
        if ModeManager:
            return ModeManager.instance().get_name(idx)
        return f"Mode {idx + 1}"

    def _toggle_mode(self, idx):
        if not (0 <= idx < TOTAL_SLOTS):
            return
        checked = not bool(self.mode_data[idx])
        self.mode_data[idx] = checked
        name = self._get_mode_name(idx)
        try:
            from utils.op_history import record as op_record
            op_record("MODE", f"{name} {'ON' if checked else 'OFF'}")
        except Exception:
            pass

        grp = self.interlock_groups[idx] if idx < len(self.interlock_groups) else 0
        if grp > 0:
            is_mandatory = (self.interlock_mandatory[grp]
                            if grp < len(self.interlock_mandatory) else False)
            if not checked and is_mandatory:
                on_count = sum(1 for i, g in enumerate(self.interlock_groups)
                               if g == grp and self.mode_data[i])
                if on_count == 0:
                    self.mode_data[idx] = True
                    self._model.refresh_row(idx)
                    overlay = getattr(self.window(), "qml_overlay", None)
                    if overlay:
                        overlay.show_message(
                            "설정 불가",
                            "이 그룹은 필수 항목입니다.\n최소 하나는 반드시 켜져 있어야 합니다.",
                            error=True,
                        )
                    return
            is_exclusive = (self.interlock_exclusive[grp]
                            if grp < len(self.interlock_exclusive) else False)
            if checked and is_exclusive:
                for other in range(TOTAL_SLOTS):
                    if other == idx:
                        continue
                    og = (self.interlock_groups[other]
                          if other < len(self.interlock_groups) else 0)
                    if og == grp and self.mode_data[other]:
                        self.mode_data[other] = False
                        self._model.refresh_row(other)

        self._model.refresh_row(idx)
        if self.plc_client and self.plc_client.is_connected:
            self.plc_client.submit(self.plc_client.send_mode_settings, list(self.mode_data))

    def _rename_mode(self, idx):
        if not ModeManager:
            return
        current = ModeManager.instance().get_name(idx)
        overlay = getattr(self.window(), "qml_overlay", None)
        if overlay:
            overlay.request_text(
                "모드 이름 변경", current,
                callback=lambda accepted, value: (
                    ModeManager.instance().set_name(idx, value.strip())
                    if accepted and value.strip() else None
                ),
            )

    # ---- 인터록 (PageMode 와 동일) ----------------------------------
    def _load_interlock_groups(self):
        try:
            with open(self._SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            groups = data.get("interlock_groups", [0] * TOTAL_SLOTS)
            if len(groups) < TOTAL_SLOTS:
                groups += [0] * (TOTAL_SLOTS - len(groups))
            mandatory = data.get("interlock_mandatory", [False] * 9)
            if len(mandatory) < 9:
                mandatory += [False] * (9 - len(mandatory))
            exclusive = data.get("interlock_exclusive", [True] * 9)
            if len(exclusive) < 9:
                exclusive += [True] * (9 - len(exclusive))
            return groups[:TOTAL_SLOTS], mandatory[:9], exclusive[:9]
        except Exception:
            return [0] * TOTAL_SLOTS, [False] * 9, [True] * 9

    # ---- main_window 호환 메서드 -----------------------------------
    def refresh_ui(self):
        self._model.refresh_all()

    def update_language(self, lang_code=None):
        self._model.refresh_all()

    def showEvent(self, event):
        (self.interlock_groups, self.interlock_mandatory,
         self.interlock_exclusive) = self._load_interlock_groups()
        super().showEvent(event)
