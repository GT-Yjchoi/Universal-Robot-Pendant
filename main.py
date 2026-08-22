import sys
import os
import faulthandler

# segfault 발생 시 C-level 스택 추적 로그 활성화
faulthandler.enable()

# Qt ibus 한글 입력 - QApplication 생성 전에 설정해야 적용됨
os.environ.setdefault("QT_IM_MODULE", "ibus")
os.environ.setdefault("GTK_IM_MODULE", "ibus")
os.environ.setdefault("XMODIFIERS", "@im=ibus")

# 빌드 환경에서 DPI 자동 스케일링으로 인해 하단이 잘리는 것을 방지
os.environ.setdefault("QT_SCALE_FACTOR", "1")
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")

from datetime import datetime
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtCore import Qt, QTimer, QObject, QEvent
from PySide6.QtGui import (QFont, QFontDatabase, QShortcut, QKeySequence,
                           QSurfaceFormat)
from ui.main_window import MainWindow
from ui.theme import APP_STYLESHEET
from utils.plc_client import PLCClient
from utils.paths import get_base_dir


_screenshot_toast = None


def _show_toast(window, msg, ms=1800):
    """화면 하단 중앙에 간단한 알림 라벨을 잠깐 표시."""
    global _screenshot_toast
    if _screenshot_toast is None or _screenshot_toast.parent() is not window:
        lbl = QLabel(window)
        lbl.setStyleSheet(
            "QLabel {"
            " background: rgba(0,0,0,210);"
            " color: white;"
            " font-size: 18px;"
            " font-weight: bold;"
            " padding: 14px 24px;"
            " border-radius: 10px;"
            " border: 2px solid #468CFF;"
            "}"
        )
        lbl.hide()
        _screenshot_toast = lbl
    _screenshot_toast.setText(msg)
    _screenshot_toast.adjustSize()
    x = (window.width() - _screenshot_toast.width()) // 2
    y = window.height() - _screenshot_toast.height() - 40
    _screenshot_toast.move(x, y)
    _screenshot_toast.raise_()
    _screenshot_toast.show()
    QTimer.singleShot(ms, _screenshot_toast.hide)


def _save_screenshot(window):
    """현재 화면을 PNG 로 저장 + 토스트 알림 (사용설명서 캡처용)."""
    out_dir = os.path.join(os.path.expanduser("~"), "screenshots")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"pendant_{ts}.png")
    pix = window.grab()
    if pix.save(path, "PNG"):
        print(f"[Screenshot] 저장: {path}")
        _show_toast(window, f"캡처 완료: {os.path.basename(path)}")
    else:
        print(f"[Screenshot] 저장 실패: {path}")
        _show_toast(window, "캡처 실패")


class _LongPressScreenshot(QObject):
    """화면 우상단 코너를 일정 시간 롱프레스 하면 스크린샷 저장."""
    CORNER_PX = 100       # 우상단 100x100 영역
    DURATION_MS = 3000    # 3초

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.DURATION_MS)
        self._timer.timeout.connect(lambda: _save_screenshot(self._window))

    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.MouseButtonPress:
            try:
                gp = event.globalPosition().toPoint()
            except AttributeError:
                gp = event.globalPos()
            local = self._window.mapFromGlobal(gp)
            w = self._window.width()
            if local.x() >= w - self.CORNER_PX and 0 <= local.y() <= self.CORNER_PX:
                self._timer.start()
        elif et == QEvent.MouseButtonRelease:
            if self._timer.isActive():
                self._timer.stop()
        return False


def _load_bundled_fonts(app: QApplication) -> None:
    fonts_dir = os.path.join(get_base_dir(), "assets", "fonts")
    if not os.path.isdir(fonts_dir):
        return
    families = []
    for name in os.listdir(fonts_dir):
        if name.lower().endswith((".ttf", ".otf")):
            fid = QFontDatabase.addApplicationFont(os.path.join(fonts_dir, name))
            if fid != -1:
                families.extend(QFontDatabase.applicationFontFamilies(fid))
    if families:
        app.setFont(QFont(families[0], 11))


def main():
    # QQuickWidget(QML GPU 페이지)용 OpenGL ES/EGL 설정.
    # QML 씬그래프가 사용할 포맷을 명시해 EGLConfig 매칭을 안정화한다.
    # 일반 QWidget 에는 영향 없음.
    _fmt = QSurfaceFormat()
    _fmt.setRenderableType(QSurfaceFormat.OpenGLES)
    _fmt.setVersion(3, 1)
    _fmt.setRedBufferSize(8)
    _fmt.setGreenBufferSize(8)
    _fmt.setBlueBufferSize(8)
    _fmt.setAlphaBufferSize(0)
    _fmt.setDepthBufferSize(0)
    _fmt.setStencilBufferSize(0)
    QSurfaceFormat.setDefaultFormat(_fmt)

    # 1. 앱 생성
    app = QApplication(sys.argv)

    # 번들된 한글 폰트 로드 (시스템 폰트 설치 불필요)
    _load_bundled_fonts(app)

    # 2. 기본 스타일 'Fusion'으로 설정
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    app.setOverrideCursor(Qt.BlankCursor)

    # 화면 밝기: settings.json 의 저장값을 적용. (이전엔 udev/setup.sh 가
    # 부팅마다 max 로 강제하던 하드코딩 — 제거하고 사용자 설정값 사용.)
    try:
        from utils import backlight
        backlight.apply_saved()
    except Exception as _e:
        print(f"[backlight] 시작 시 적용 실패: {_e}")

    # 4. [NEW] PLC 통신 모듈 생성
    # 프로그램 전체에서 하나만 만들어 공유합니다.
    plc_client = PLCClient()

    # 5. [MODIFIED] 윈도우 생성 시 PLC 클라이언트 전달
    # (ui/main_window.py의 __init__도 이에 맞춰 수정되어 있어야 합니다)
    window = MainWindow(plc_client)

    # weston kiosk-shell: 패널/태스크바가 없고 컴포지터가 단일 클라이언트를
    # 출력 크기에 맞춰 풀스크린으로 띄움. X11 시절의 WindowStaysOnTopHint /
    # 수동 setGeometry 는 Wayland 에서 surface role 을 깨뜨려 창이 안 뜸 →
    # showFullScreen() 만 호출.
    window.showFullScreen()

    # 스크린샷 트리거 — F12 키 + 우상단 100×100 코너 3초 롱프레스
    QShortcut(QKeySequence(Qt.Key_F12), window,
              activated=lambda: _save_screenshot(window))
    _long_press_filter = _LongPressScreenshot(window)
    app.installEventFilter(_long_press_filter)

    # 6. [NEW] 프로그램 종료 시 연결 해제
    app.aboutToQuit.connect(plc_client.disconnect_plc)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
