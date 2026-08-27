"""Single-scene Qt Quick entry point for the robot pendant."""

from __future__ import annotations

import faulthandler
import os
import sys

faulthandler.enable()

os.environ.setdefault("QT_IM_MODULE", "ibus")
os.environ.setdefault("GTK_IM_MODULE", "ibus")
os.environ.setdefault("XMODIFIERS", "@im=ibus")
os.environ.setdefault("QT_SCALE_FACTOR", "1")
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from drivers.plc import PLCClient
from ui.qml_controller import PendantController
from utils.paths import get_base_dir


def _load_bundled_fonts(app: QGuiApplication) -> None:
    fonts_dir = os.path.join(get_base_dir(), "assets", "fonts")
    if not os.path.isdir(fonts_dir):
        return
    families = []
    for name in os.listdir(fonts_dir):
        if name.lower().endswith((".ttf", ".otf")):
            font_id = QFontDatabase.addApplicationFont(
                os.path.join(fonts_dir, name)
            )
            if font_id != -1:
                families.extend(QFontDatabase.applicationFontFamilies(font_id))
    if families:
        app.setFont(QFont(families[0], 11))


def _install_screenshot_hook(app: QGuiApplication, window) -> None:
    """Capture the live Qt Quick scene when a local request file is created."""
    if not sys.platform.startswith("linux"):
        return
    request_path = os.environ.get(
        "PENDANT_SCREENSHOT_REQUEST", "/tmp/pendant-screenshot.request"
    )
    output_path = os.environ.get(
        "PENDANT_SCREENSHOT_OUTPUT", "/tmp/pendant-screenshot.png"
    )
    watch_dir = os.path.dirname(request_path) or "/tmp"
    watcher = QFileSystemWatcher(app)
    if not watcher.addPath(watch_dir):
        print(f"[Screenshot] 감시 경로 등록 실패: {watch_dir}")
        return

    def capture_if_requested(_changed_path=""):
        if not os.path.exists(request_path):
            return
        try:
            os.unlink(request_path)
            image = window.grabWindow()
            if image.isNull() or not image.save(output_path, "PNG"):
                print(f"[Screenshot] 캡처 저장 실패: {output_path}")
                return
            print(f"[Screenshot] 저장 완료: {output_path}")
        except Exception as exc:
            print(f"[Screenshot] 캡처 실패: {exc}")

    watcher.directoryChanged.connect(capture_if_requested)
    QTimer.singleShot(0, capture_if_requested)
    app._pendant_screenshot_watcher = watcher


def main() -> int:
    QQuickStyle.setStyle("Fusion")
    app = QGuiApplication(sys.argv)
    _load_bundled_fonts(app)
    app.setOverrideCursor(Qt.BlankCursor)

    try:
        from utils import backlight
        backlight.apply_saved()
    except Exception as exc:
        print(f"[backlight] 시작 시 적용 실패: {exc}")

    plc_client = PLCClient()
    controller = PendantController(plc_client)
    engine = QQmlApplicationEngine()
    context = engine.rootContext()
    for name, value in controller.context_properties().items():
        context.setContextProperty(name, value)

    qml_path = os.path.join(get_base_dir(), "ui", "qml", "PendantMain.qml")
    engine.load(QUrl.fromLocalFile(qml_path))
    if not engine.rootObjects():
        controller.shutdown()
        return 1

    _install_screenshot_hook(app, engine.rootObjects()[0])

    app.aboutToQuit.connect(controller.shutdown)
    smoke_exit_ms = int(os.environ.get("PENDANT_SMOKE_EXIT_MS", "0") or 0)
    if smoke_exit_ms > 0:
        QTimer.singleShot(smoke_exit_ms, app.quit)
    print("[UI] 단일 QQmlApplicationEngine / QQuickWindow 실행")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
