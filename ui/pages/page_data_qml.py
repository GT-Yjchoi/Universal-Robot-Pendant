"""
금형데이터 페이지 QML(GPU) — PageData drop-in.
리스트 2개 GPU 스크롤. 저장포맷(_perform_save)·로드(_on_load_clicked)는
PageData 와 동일 (verbatim). 다이얼로그는 기존 Python 위젯 재사용.
"""
import os
import json
from datetime import datetime

from PySide6.QtCore import (Qt, QObject, Signal, Slot, Property, QUrl,
                            QAbstractListModel, QModelIndex, QByteArray)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget
from PySide6.QtQuickWidgets import QQuickWidget

from utils.paths import get_recipes_dir
from utils.json_utils import save_json
try:
    from utils.mode_manager import ModeManager
except ImportError:
    ModeManager = None
try:
    from utils.languages import LanguageManager
except ImportError:
    LanguageManager = None

_QML_PATH = os.path.join(os.path.dirname(__file__), "PageData.qml")
_R = Qt.UserRole + 1


class StrListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []

    def rowCount(self, p=QModelIndex()):
        return len(self._rows)

    def roleNames(self):
        return {_R: QByteArray(b"display")}

    def data(self, ix, role):
        i = ix.row()
        if role == _R and 0 <= i < len(self._rows):
            return self._rows[i]
        return None

    def reset(self, rows):
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()


class DataBackend(QObject):
    changed = Signal()

    def __init__(self, page):
        super().__init__(page)
        self._p = page

    def _hdr(self):
        lm = LanguageManager.instance() if LanguageManager else None
        return lm.get_text("data_list_header") if lm else " 저장된 파일 목록"

    def _phdr(self):
        lm = LanguageManager.instance() if LanguageManager else None
        return lm.get_text("data_preview_header") if lm else "데이터 미리보기"

    def _info(self):
        return self._p._info_text

    def _sel(self):
        return self._p._sel_index

    def _buttons(self):
        lm = LanguageManager.instance() if LanguageManager else None

        def t(k, fb):
            return ("  " + lm.get_text(k)) if lm else fb
        return [
            {"text": t("btn_load_file", "불러오기\n(LOAD)"), "color": "#64FF64"},
            {"text": t("btn_new_file", "새로만들기\n(NEW)"), "color": "#468CFF"},
            {"text": t("btn_save_file", "저장\n(SAVE)"), "color": "#FFD280"},
            {"text": t("btn_del_file", "파일 삭제\n(DELETE)"), "color": "#FF4646"},
        ]

    listHeader = Property(str, _hdr, notify=changed)
    previewHeader = Property(str, _phdr, notify=changed)
    infoText = Property(str, _info, notify=changed)
    selIndex = Property(int, _sel, notify=changed)
    buttons = Property(list, _buttons, notify=changed)

    @Slot(int)
    def selectFile(self, idx):
        self._p._on_file_selected(idx)

    @Slot(int)
    def btnClicked(self, idx):
        (self._p._on_load_clicked, self._p._on_new_clicked,
         self._p._on_save_clicked, self._p._on_del_clicked)[idx]()


class PageDataQml(QWidget):
    sig_file_loaded = Signal(str)

    def __init__(self, sequence_data=None, position_points=None,
                 timer_library=None, mode_data=None, view_order_data=None,
                 speed_state=None, packing_config=None):
        super().__init__()
        self.sequence_data = sequence_data if sequence_data is not None else {}
        if "Main" not in self.sequence_data:
            self.sequence_data["Main"] = []
        self.position_points = position_points if position_points is not None else {}
        self.timer_library = timer_library if timer_library is not None else {}
        self.mode_data = mode_data if mode_data is not None else []
        self.view_order_data = view_order_data if view_order_data is not None else []
        self.speed_state = speed_state if speed_state is not None else {"speed_level": 10}
        self.packing_config = packing_config if packing_config is not None else {}

        self.save_dir = get_recipes_dir()
        self.current_filename = None
        if not os.path.exists(self.save_dir):
            try:
                os.makedirs(self.save_dir)
            except OSError as e:
                print(f"[PageData] 디렉토리 생성 실패: {e}")

        self._files = []          # filenames (with .json)
        self._sel_index = -1
        self._info_text = ""
        self._file_model = StrListModel(self)
        self._prev_model = StrListModel(self)
        self._be = DataBackend(self)

        self._view = QQuickWidget(self)
        self._view.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self._view.setClearColor(QColor("#16202B"))
        ctx = self._view.rootContext()
        ctx.setContextProperty("fileModel", self._file_model)
        ctx.setContextProperty("previewModel", self._prev_model)
        ctx.setContextProperty("dataBackend", self._be)
        self._view.setSource(QUrl.fromLocalFile(_QML_PATH))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)

        self._refresh_file_list()
        self.update_language()

        if LanguageManager:
            LanguageManager.instance().sig_lang_changed.connect(self.update_language)

    # ---- 호환 메서드 ----
    def set_current_filename(self, filename):
        if filename and filename != "No Data":
            self.current_filename = filename

    def auto_save(self):
        if not self.current_filename or self.current_filename == "No Data":
            return
        filepath = os.path.join(self.save_dir, f"{self.current_filename}.json")
        self._perform_save(filepath, self.current_filename, is_auto=True)

    def update_language(self, lang_code=None):
        lm = LanguageManager.instance() if LanguageManager else None
        if self._sel_index < 0:
            self._info_text = (lm.get_text("data_info_default") if lm
                               else "파일을 선택하면 상세 정보가 표시됩니다.")
        self._be.changed.emit()

    def showEvent(self, event):
        self._refresh_file_list()
        super().showEvent(event)

    # ---- 리스트 (QListWidget → model) ----
    def _refresh_file_list(self):
        self._files = []
        self._sel_index = -1
        self._prev_model.reset([])
        lm = LanguageManager.instance() if LanguageManager else None
        self._info_text = (lm.get_text("data_info_default") if lm
                           else "파일을 선택하세요.")
        if os.path.exists(self.save_dir):
            try:
                files = [f for f in os.listdir(self.save_dir) if f.endswith(".json")]
                files.sort()
                self._files = files
            except OSError:
                pass
        self._file_model.reset([f[:-5] for f in self._files])
        self._be.changed.emit()

    def _cur_item(self):
        """원본 currentItem() 대체. (filename, display) 또는 None."""
        if 0 <= self._sel_index < len(self._files):
            fn = self._files[self._sel_index]
            return fn, fn[:-5]
        return None

    def _on_file_selected(self, idx):
        if not (0 <= idx < len(self._files)):
            return
        self._sel_index = idx
        filename = self._files[idx]
        filepath = os.path.join(self.save_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            steps = []
            info_extra = ""
            if isinstance(data, list):
                info_extra = "(List Type)"
                steps = data
            elif isinstance(data, dict):
                seq_raw = data.get("sequence", [])
                if isinstance(seq_raw, list):
                    steps = seq_raw
                    info_extra = "(Single Seq)"
                elif isinstance(seq_raw, dict):
                    steps = seq_raw.get("Main", [])
                    info_extra = f"(Multi Seq: {len(seq_raw.keys())}개)"
            dt = datetime.fromtimestamp(os.path.getmtime(filepath))
            date_str = dt.strftime('%Y-%m-%d %H:%M')
            self._info_text = f" {filename[:-5]}   |   {info_extra}   |   🕒 {date_str}"
            lines = []
            icons = {"POS": "[P]", "OUT": "[Y]", "IN": "[X]",
                     "TMR": "[T]", "JMP": "[J]", "CALL": "[C]"}
            if steps:
                step_num = 0
                for step in steps:
                    stype = step.get("type", "")
                    if stype == "COMMENT":
                        lines.append(f"// {step.get('text', '')}")
                        continue
                    step_num += 1
                    lines.append(f"[{step_num:02d}]  {icons.get(stype, '?')}  "
                                 f"{step.get('name', 'Unknown')}")
            else:
                lines.append("i (Empty or No Main Sequence)")
            self._prev_model.reset(lines)
        except Exception as e:
            self._info_text = f"X 오류: {e}"
        self._be.changed.emit()

    # ---- 저장 (PageData._perform_save 와 동일 포맷) ----
    def _perform_save(self, filepath, display_name, is_auto=False):
        clean_sequence = {}
        for seq_name, steps in self.sequence_data.items():
            clean_steps = []
            for step in steps:
                s = dict(step)
                if s.get("type") == "POS":
                    s.pop("speeds", None)
                    s.pop("coords", None)
                clean_steps.append(s)
            clean_sequence[seq_name] = clean_steps

        save_data = {
            "version": 1.5,
            "saved_at": str(datetime.now()),
            "sequence": clean_sequence,
            "position_points": self.position_points,
            "timer_library": self.timer_library,
            "mode": self.mode_data,
            "view_order": self.view_order_data,
            "speed_level": int(self.speed_state.get("speed_level", 10)),
            "packing_config": self.packing_config,
            "user_modes": ModeManager.instance().to_dict() if ModeManager else {}
        }
        lm = LanguageManager.instance() if LanguageManager else None
        try:
            save_json(filepath, save_data)
            if not is_auto:
                self._refresh_file_list()
                # 저장한 파일 재선택
                for i, fn in enumerate(self._files):
                    if fn[:-5] == display_name:
                        self._file_model.reset([f[:-5] for f in self._files])
                        self._on_file_selected(i)
                        break
                self.current_filename = display_name
                self.sig_file_loaded.emit(display_name)
                t_done = lm.get_text("title_done") if lm else "완료"
                m_done = lm.get_text("msg_save_done") if lm else "저장되었습니다."
                self.window().qml_overlay.show_message(t_done, m_done)
            else:
                print(f"[AutoSave] Saved {display_name}.json")
        except Exception as e:
            if not is_auto:
                self.window().qml_overlay.show_message("Error", f"Save Failed:\n{e}", error=True)
            else:
                print(f"[AutoSave] Error: {e}")

    def _on_new_clicked(self):
        if "Main" not in self.sequence_data or not isinstance(
                self.sequence_data.get("Main"), list):
            self.sequence_data["Main"] = []
        lm = LanguageManager.instance() if LanguageManager else None
        t_title = lm.get_text("title_new") if lm else "새로 만들기"
        t_msg = lm.get_text("msg_new_confirm") if lm else "데이터를 새로 만듭니다."
        def confirmed(ok):
            if not ok: return
            self.window().qml_overlay.request_text("새 파일 이름 입력", callback=named)
        def named(ok, name):
            if not ok or not name: return
            safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-', '.')).strip()
            if not safe_name: return
            filepath = os.path.join(self.save_dir, f"{safe_name}.json")
            if os.path.exists(filepath):
                title = lm.get_text("title_dup") if lm else "중복 확인"
                body = (lm.get_text("msg_dup_confirm").format(safe_name) if lm else f"'{safe_name}' 중복. 덮어쓸까요?")
                self.window().qml_overlay.request_confirm(
                    title, body, callback=lambda accepted: finalize(filepath, safe_name) if accepted else None,
                )
            else:
                finalize(filepath, safe_name)
        def finalize(filepath, safe_name):
            if "Main" not in self.sequence_data or not self.sequence_data["Main"]:
                self.sequence_data["Main"] = [{
                    "type": "POS", "name": "원점 복귀", "point_name": "원점",
                    "active_axes": [True] * 8, "speeds": [100] * 8}]
            self._perform_save(filepath, safe_name)
        self.window().qml_overlay.request_confirm(t_title, t_msg, callback=confirmed)

    def _on_save_clicked(self):
        lm = LanguageManager.instance() if LanguageManager else None
        if not self.current_filename or self.current_filename == "No Data":
            t_not = lm.get_text("title_notice") if lm else "알림"
            m_not = lm.get_text("msg_no_save_target") if lm else "저장할 대상이 없습니다."
            self.window().qml_overlay.show_message(t_not, m_not)
            return
        t_sav = lm.get_text("title_save") if lm else "저장 확인"
        m_sav = (lm.get_text("msg_save_confirm").format(self.current_filename)
                 if lm else f"[{self.current_filename}] 에 저장?")
        def finished(accepted):
            if not accepted: return
            filepath = os.path.join(self.save_dir, f"{self.current_filename}.json")
            self._perform_save(filepath, self.current_filename)
        self.window().qml_overlay.request_confirm(t_sav, m_sav, callback=finished)

    def _on_load_clicked(self):
        cur = self._cur_item()
        lm = LanguageManager.instance() if LanguageManager else None
        if not cur:
            t_not = lm.get_text("title_notice") if lm else "알림"
            m_not = lm.get_text("msg_no_sel_load") if lm else "파일을 선택해주세요."
            self.window().qml_overlay.show_message(t_not, m_not)
            return
        filename, disp = cur
        filepath = os.path.join(self.save_dir, filename)
        t_load = lm.get_text("title_load") if lm else "불러오기 확인"
        m_load = (lm.get_text("msg_load_confirm").format(disp) if lm
                  else f"'{disp}' 로드?")
        self.window().qml_overlay.request_confirm(
            t_load, m_load,
            callback=lambda accepted: self._perform_load(filepath, disp, lm) if accepted else None,
        )

    def _perform_load(self, filepath, disp, lm):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
            self.sequence_data.clear()
            if isinstance(new_data, list):
                self.sequence_data["Main"] = new_data
            elif isinstance(new_data, dict):
                seq_raw = new_data.get("sequence", [])
                if isinstance(seq_raw, list):
                    self.sequence_data["Main"] = seq_raw
                elif isinstance(seq_raw, dict):
                    self.sequence_data.update(seq_raw)
            if "Main" not in self.sequence_data:
                self.sequence_data["Main"] = []
            self.position_points.clear()
            self.position_points.update(new_data.get("position_points", {}))
            self.timer_library.clear()
            self.timer_library.update(new_data.get("timer_library", {}))
            self.view_order_data.clear()
            self.view_order_data.extend(new_data.get("view_order", []))
            mod = new_data.get("mode", [])
            for i, val in enumerate(mod):
                if i < len(self.mode_data):
                    self.mode_data[i] = val
            try:
                self.speed_state["speed_level"] = max(1, min(10, int(
                    new_data.get("speed_level", 10))))
            except (TypeError, ValueError):
                self.speed_state["speed_level"] = 10
            self.packing_config.clear()
            pc = new_data.get("packing_config", {})
            if isinstance(pc, dict):
                self.packing_config.update(pc)
            self.current_filename = disp
            self.sig_file_loaded.emit(disp)
            if isinstance(new_data, dict):
                user_modes = new_data.get("user_modes")
                if user_modes and ModeManager:
                    ModeManager.instance().load_from_dict(user_modes)
            t_done = lm.get_text("title_done") if lm else "완료"
            m_done = lm.get_text("msg_load_done") if lm else "로드 완료."
            self.window().qml_overlay.show_message(t_done, m_done)
        except Exception as e:
            self.window().qml_overlay.show_message("Error", f"Load Failed:\n{e}", error=True)

    def _on_del_clicked(self):
        cur = self._cur_item()
        lm = LanguageManager.instance() if LanguageManager else None
        if not cur:
            t_not = lm.get_text("title_notice") if lm else "알림"
            m_not = lm.get_text("msg_no_sel_del") if lm else "선택해주세요."
            self.window().qml_overlay.show_message(t_not, m_not)
            return
        filename, deleted_name = cur
        filepath = os.path.join(self.save_dir, filename)
        t_del = lm.get_text("title_del") if lm else "삭제 확인"
        m_del = (lm.get_text("msg_del_confirm").format(deleted_name) if lm
                 else f"'{deleted_name}' 삭제?")
        def finished(accepted):
            if not accepted: return
            try:
                os.remove(filepath)
                self._refresh_file_list()
                self._info_text = (lm.get_text("msg_del_done") if lm else "삭제됨.")
                if self.current_filename == deleted_name:
                    self.current_filename = None
                self._be.changed.emit()
            except Exception as e:
                self.window().qml_overlay.show_message("Error", f"Delete Failed:\n{e}", error=True)
        self.window().qml_overlay.request_confirm(t_del, m_del, callback=finished)
