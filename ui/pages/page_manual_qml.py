"""
수동운전 페이지 QML(GPU) 버전 — PageManual drop-in.

- UI/스크롤: PageManual.qml (Qt Quick = GPU 씬그래프, 키네틱 스크롤)
- 로직 전부 Python. **밸브 작동(PLC R-M-W)은 ValvePanel 에서 한 글자도
  출력 요청은 DT210~213, 실제 출력 모니터는 DT144~147을 사용한다.

main_window: PageManual(plc_client=...) 와 생성자/메서드 호환.
"""
import json
import os

from PySide6.QtCore import (Qt, QObject, Signal, Slot, Property, QTimer,
                            QAbstractListModel, QModelIndex, QByteArray)

from utils.paths import get_settings_path

try:
    from utils.io_manager import IOManager
except ImportError:
    IOManager = None
try:
    from utils.languages import LanguageManager
except ImportError:
    LanguageManager = None

_QML_PATH = os.path.join(os.path.dirname(__file__), "PageManual.qml")
_AXES = ["X", "Y", "Z", "Y2", "Z2", "θ", "R1", "R2"]


# ───────────────────────── 모델 ─────────────────────────
class AxisModel(QAbstractListModel):
    R_NAME = Qt.UserRole + 1
    R_VAL = Qt.UserRole + 2
    R_VIS = Qt.UserRole + 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vals = ["0.000"] * 8
        self._vis = [True] * 8

    def rowCount(self, p=QModelIndex()):
        return 8

    def roleNames(self):
        return {self.R_NAME: QByteArray(b"aname"),
                self.R_VAL: QByteArray(b"avalue"),
                self.R_VIS: QByteArray(b"avisible")}

    def data(self, ix, role):
        i = ix.row()
        if not (0 <= i < 8):
            return None
        if role == self.R_NAME:
            return _AXES[i]
        if role == self.R_VAL:
            return self._vals[i]
        if role == self.R_VIS:
            return self._vis[i]
        return None

    def set_values(self, axis_data):
        for i, v in enumerate(axis_data):
            if i < 8:
                self._vals[i] = f"{v:.3f}"
        if axis_data:
            self.dataChanged.emit(self.index(0, 0), self.index(7, 0),
                                  [self.R_VAL])

    def set_visibility(self, use_mask):
        for i in range(8):
            self._vis[i] = bool((use_mask >> i) & 1)
        self.dataChanged.emit(self.index(0, 0), self.index(7, 0),
                              [self.R_VIS])


class IoModel(QAbstractListModel):
    R_LABEL = Qt.UserRole + 1
    R_ON = Qt.UserRole + 2

    def __init__(self, addrs, parent=None):
        super().__init__(parent)
        self._labels = list(addrs)
        self._on = [False] * len(addrs)

    def rowCount(self, p=QModelIndex()):
        return len(self._labels)

    def roleNames(self):
        return {self.R_LABEL: QByteArray(b"label"),
                self.R_ON: QByteArray(b"on")}

    def data(self, ix, role):
        i = ix.row()
        if not (0 <= i < len(self._labels)):
            return None
        if role == self.R_LABEL:
            return self._labels[i]
        if role == self.R_ON:
            return self._on[i]
        return None

    def set_label(self, i, text):
        if 0 <= i < len(self._labels) and text:
            self._labels[i] = text
            self.dataChanged.emit(self.index(i, 0), self.index(i, 0),
                                  [self.R_LABEL])

    def reset_labels(self, labels):
        self.beginResetModel()
        self._labels = list(labels)
        self._on = [False] * len(self._labels)
        self.endResetModel()

    def update_from_words(self, words):
        # IOList.update_from_words 와 동일 로직 (변경 비트만)
        for word_idx, word_val in enumerate(words):
            for bit_idx in range(16):
                k = word_idx * 16 + bit_idx
                if k < len(self._on):
                    is_on = bool(word_val & (1 << bit_idx))
                    if self._on[k] != is_on:
                        self._on[k] = is_on
                        self.dataChanged.emit(self.index(k, 0),
                                              self.index(k, 0), [self.R_ON])


class ValveModel(QAbstractListModel):
    R_NAME = Qt.UserRole + 1
    R_CHK = Qt.UserRole + 2
    R_MODE = Qt.UserRole + 3
    R_BIT = Qt.UserRole + 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfgs = []          # enabled valve configs (order 정렬됨)
        self._chk = []

    def rowCount(self, p=QModelIndex()):
        return len(self._cfgs)

    def roleNames(self):
        return {self.R_NAME: QByteArray(b"vname"),
                self.R_CHK: QByteArray(b"vchecked"),
                self.R_MODE: QByteArray(b"vmode"),
                self.R_BIT: QByteArray(b"vbit")}

    def data(self, ix, role):
        i = ix.row()
        if not (0 <= i < len(self._cfgs)):
            return None
        c = self._cfgs[i]
        if role == self.R_NAME:
            return c.get("name", f"밸브 {i+1}")
        if role == self.R_CHK:
            return self._chk[i]
        if role == self.R_MODE:
            return c.get("mode", "toggle")
        if role == self.R_BIT:
            return int(c.get("index", i))
        return None

    def reset_configs(self, cfgs):
        self.beginResetModel()
        self._cfgs = cfgs
        self._chk = [False] * len(cfgs)
        self.endResetModel()

    def set_checked_by_bit(self, bit_index, on):
        for i, c in enumerate(self._cfgs):
            if int(c.get("index", -1)) == bit_index and c.get("mode") == "toggle":
                if self._chk[i] != on:
                    self._chk[i] = on
                    self.dataChanged.emit(self.index(i, 0), self.index(i, 0),
                                          [self.R_CHK])
                return


# ───────────────────── 백엔드 (IO/언어) ─────────────────────
class IoBackend(QObject):
    titlesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._in = "입력"
        self._out = "출력"
        if LanguageManager:
            lm = LanguageManager.instance()
            self._in = lm.get_text("lbl_io_input")
            self._out = lm.get_text("lbl_io_output")

    def _get_in(self):
        return self._in

    def _get_out(self):
        return self._out

    inTitle = Property(str, _get_in, notify=titlesChanged)
    outTitle = Property(str, _get_out, notify=titlesChanged)

    def refresh_titles(self):
        if LanguageManager:
            lm = LanguageManager.instance()
            self._in = lm.get_text("lbl_io_input")
            self._out = lm.get_text("lbl_io_output")
            self.titlesChanged.emit()


# ───────────── 백엔드 (밸브) — PLC 로직 VERBATIM ─────────────
class ValveBackend(QObject):
    """ValvePanel 의 밸브 작동 코드를 그대로 복사. UI 터치점만 모델로 교체.
    PLC 프로토콜 라인(read_words/write_words/비트연산/DT주소)은 동일."""
    lockedChanged = Signal()

    def __init__(self, plc_client, model, parent=None):
        super().__init__(parent)
        self.plc_client = plc_client
        self._model = model
        self.valve_configs = []
        self._locked = False

    def _get_locked(self):
        return self._locked
    locked = Property(bool, _get_locked, notify=lockedChanged)

    def set_locked(self, v):
        if self._locked != v:
            self._locked = v
            self.lockedChanged.emit()

    # ----- 설정 로드 (ValvePanel._load_and_create_valves 의 데이터 부분) -----
    def load_configs(self):
        try:
            path = get_settings_path()
            valve_config = []
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    valve_config = settings.get("valve_config", [])
            defaults = self._get_default_valve_config()
            by_index = {int(c.get("index", i)): dict(c)
                        for i, c in enumerate(defaults)}
            if isinstance(valve_config, list):
                for i, config in enumerate(valve_config):
                    if not isinstance(config, dict):
                        continue
                    index = int(config.get("index", i))
                    if index in by_index:
                        by_index[index].update(config)
                        by_index[index]["index"] = index
            valve_config = list(by_index.values())
            valve_config.sort(key=lambda x: x.get("order", 0))
            point_count = (IOManager.instance().point_count(False)
                           if IOManager else 32)
            enabled_valves = [
                v for v in valve_config
                if 0 <= int(v.get("index", -1)) < point_count
                and v.get("enabled", True)
            ]
            self.valve_configs = enabled_valves
            self._model.reset_configs(enabled_valves)
            print(f"[ValvePanel] {len(enabled_valves)}개 밸브 버튼 생성 완료")
        except Exception as e:
            print(f"[ValvePanel] 밸브 설정 로드 실패: {e}")
            self.valve_configs = []
            self._model.reset_configs([])

    def _get_default_valve_config(self):
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
        point_count = (IOManager.instance().point_count(False)
                       if IOManager else 32)
        config = []
        for i in range(point_count):
            if IOManager:
                name = IOManager.instance().get_output_name(i)
            else:
                name = named_y2x[i - 16] if 16 <= i < 32 else (
                    named_y0x[i] if i < 16 else f"출력 {i + 1}"
                )
            config.append({
                "index": i, "name": name, "mode": "toggle",
                "enabled": 16 <= i < 32, "order": i
            })
        return config

    # ----- 아래 4개는 ValvePanel 원본과 동일 (UI 의존 없음) -----
    def _valve_dt_addr(self, bit_index):
        return self.plc_client.ADDR_OUTPUT_BASE + int(bit_index) // 16, int(bit_index) % 16

    def _log_valve_op(self, bit_index, state):
        try:
            from utils.op_history import record as op_record
            name = None
            for cfg in self.valve_configs:
                if cfg.get("index") == bit_index:
                    name = cfg.get("name")
                    break
            label = name or f"밸브 #{bit_index}"
            op_record("VALVE", f"{label} {state}")
        except Exception:
            pass

    @Slot(int, bool)
    def valveToggle(self, bit_index, checked):
        if self._locked:
            return
        if self.plc_client and self.plc_client.is_connected:
            self.plc_client.submit(
                self._write_valve_state, bit_index, bool(checked), True,
                priority=1,
            )
        # 낙관적 표시 (실제 상태는 다음 monitor sync 가 확정)
        self._model.set_checked_by_bit(bit_index, checked)

    @Slot(int)
    def valvePressed(self, bit_index):
        if self._locked:
            return
        if self.plc_client and self.plc_client.is_connected:
            self.plc_client.submit(
                self._write_valve_state, bit_index, True, True, priority=1,
            )

    @Slot(int)
    def valveReleased(self, bit_index):
        if self._locked:
            return
        if self.plc_client and self.plc_client.is_connected:
            self.plc_client.submit(
                self._write_valve_state, bit_index, False, False, priority=1,
            )

    def _write_valve_state(self, bit_index, enabled, log_operation):
        dt_addr, bit_pos = self._valve_dt_addr(bit_index)
        if not self.plc_client.write_bit(0x09, dt_addr, bit_pos, enabled):
            raise ConnectionError(f"valve bit update failed: DT{dt_addr}.{bit_pos}")
        if log_operation:
            self._log_valve_op(bit_index, "ON" if enabled else "OFF")

    def sync_from_outputs(self, outputs):
        # Non-compressed map: DT144=Y00, DT145=Y10, DT146=Y20, DT147=Y30.
        for c in self.valve_configs:
            if c.get("mode") != "toggle":
                continue
            bit_index = c.get("index")
            if bit_index is None:
                continue
            word_idx, bit_pos = divmod(int(bit_index), 16)
            if word_idx >= len(outputs):
                continue
            is_on = bool(outputs[word_idx] & (1 << bit_pos))
            self._model.set_checked_by_bit(bit_index, is_on)


# ───────────────────────── 페이지 ─────────────────────────
class PageManualQml(QObject):
    def __init__(self, plc_client=None, overlay=None):
        super().__init__()
        self.plc_client = plc_client
        self.qml_overlay = overlay
        self._active = False

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
        self._valve_m = ValveModel(self)
        self._io_be = IoBackend(self)
        self._valve_be = ValveBackend(plc_client, self._valve_m, self)

        self._valve_be.load_configs()
        self._last_cfg_mtime = self._cfg_mtime()
        self._apply_io_names()

        if self.plc_client:
            self.plc_client.sig_monitor_data.connect(self._on_monitor_data)
            self.plc_client.sig_connected.connect(self._refresh_axis_visibility)
        if IOManager:
            IOManager.instance().sig_names_changed.connect(self._apply_io_names)
        if LanguageManager:
            LanguageManager.instance().sig_lang_changed.connect(
                self.update_language)

    # ---- IO 이름 ----
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

    # ---- 실시간 monitor ----
    def _on_monitor_data(self, data):
        if not isinstance(data, dict):
            return
        # 잠금 오버레이는 페이지 숨김과 무관하게 갱신 (ValvePanel 원본 동일)
        op_status = data.get('op_status', 0)
        self._valve_be.set_locked(op_status in (1, 2))

        if not self._active:
            return
        if 'axis_pos' in data:
            self._axis.set_values(data['axis_pos'])
        if 'inputs' in data:
            self._io_in.update_from_words(data['inputs'])
        if 'outputs' in data:
            self._io_out.update_from_words(data['outputs'])
            outs = data['outputs']
            if outs and len(outs) >= 2:
                self._valve_be.sync_from_outputs(outs)

    def _refresh_axis_visibility(self):
        try:
            from utils.json_utils import load_json
            uses = (load_json(get_settings_path()) or {}).get("axis_uses", [True] * 8)
            mask = sum((1 << i) for i, enabled in enumerate(uses[:8]) if enabled)
            self._axis.set_visibility(mask)
        except Exception as e:
            print(f"Axis Config Load Error: {e}")

    # ---- 설정 변경 시 밸브 재로드 (ValvePanel.showEvent 동일 취지) ----
    def _cfg_mtime(self):
        try:
            p = get_settings_path()
            return os.path.getmtime(p) if os.path.exists(p) else 0
        except OSError:
            return 0

    def activate(self):
        self._active = True
        m = self._cfg_mtime()
        if m > self._last_cfg_mtime:
            print("[ValvePanel] 설정 파일 변경 감지! 자동 새로고침...")
            self._valve_be.load_configs()
            self._apply_io_names()
            self._last_cfg_mtime = m
        QTimer.singleShot(0, self._refresh_axis_visibility)

    def deactivate(self):
        self._active = False

    # ---- main_window 호환 ----
    def update_language(self, lang_code=None):
        self._io_be.refresh_titles()
        self._apply_io_names()
