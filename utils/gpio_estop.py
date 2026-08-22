"""
GPIO 비상정지 모니터 (ODROID-M1S)

배선:
    3.3V ──[3kΩ]──┬── 물리핀 15 (=DTS PIN_15)
                  │
               [NC버튼]
                  │
                 GND

M1S 핀 매핑:
    물리핀 15  →  /dev/gpiochip0 line 18  (DTS 라벨 "PIN_15")
    `gpioinfo /dev/gpiochip0 | grep PIN_15` 로 검증 가능.

동작:
    - 정상: line LOW  (0V)   → DT213 = 0
    - 비상: line HIGH (3.3V) → DT213 = 1

방식: QTimer 폴링 (20ms 주기) + lgpio 사용
"""

import sys
import os
from PySide6.QtCore import QObject, Signal, QTimer

ESTOP_CHIP   = 0    # /dev/gpiochip0
ESTOP_PIN    = 18   # gpiochip0 line 18 = 40핀 헤더 물리핀 15 (M1S)
POLL_MS      = 20   # 폴링 주기 (ms)
DEBOUNCE_CNT = 3    # 연속 N회 같은 값 → 상태 확정 (20ms × 3 = 60ms)

# 시스템 Python dist-packages 경로 추가 (lgpio가 시스템에만 깔린 경우)
_SYS_DIST = "/usr/lib/python3/dist-packages"
if _SYS_DIST not in sys.path:
    sys.path.insert(0, _SYS_DIST)

_GPIO_ENABLED = os.environ.get("PENDANT_GPIO_ESTOP", "1").strip().lower() \
    not in {"0", "false", "no", "off"}

try:
    if not _GPIO_ENABLED:
        raise RuntimeError("PENDANT_GPIO_ESTOP 환경변수로 비활성화됨")
    import lgpio
    _h = lgpio.gpiochip_open(ESTOP_CHIP)
    lgpio.gpio_claim_input(_h, ESTOP_PIN, lgpio.SET_PULL_UP)
    _GPIO_AVAILABLE = True
    print(f"[GPIO E-Stop] lgpio 초기화 완료 (gpiochip{ESTOP_CHIP} line {ESTOP_PIN}, 물리핀 15)")
except Exception as e:
    _GPIO_AVAILABLE = False
    _h = None
    print(f"[GPIO E-Stop] lgpio 초기화 실패: {e}")


class GpioEstop(QObject):
    """
    QTimer 폴링으로 GPIO22를 감시해 소프트 비상정지 신호를 발행.

    sig_estop(bool):
        True  → 비상정지 발동  (GPIO LOW)
        False → 비상정지 해제  (GPIO HIGH)
    """
    sig_estop = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._pending_level = None
        self._pending_count = 0

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)

    def start(self):
        if not _GPIO_AVAILABLE:
            print("[GPIO E-Stop] GPIO 사용 불가 — 비상정지 비활성")
            return
        self._timer.start()
        print(f"[GPIO E-Stop] GPIO{ESTOP_PIN} 폴링 시작 ({POLL_MS}ms 주기)")

    def stop(self):
        self._timer.stop()
        if _GPIO_AVAILABLE and _h is not None:
            try:
                lgpio.gpio_free(_h, ESTOP_PIN)
                lgpio.gpiochip_close(_h)
            except Exception:
                pass
        print(f"[GPIO E-Stop] GPIO{ESTOP_PIN} 폴링 종료")

    def _poll(self):
        try:
            level = lgpio.gpio_read(_h, ESTOP_PIN)
        except Exception:
            return

        is_estop = (level == 1)  # HIGH = 비상정지

        if is_estop == self._pending_level:
            self._pending_count += 1
        else:
            self._pending_level = is_estop
            self._pending_count = 1

        if self._pending_count >= DEBOUNCE_CNT and is_estop != self._active:
            self._active = is_estop
            self.sig_estop.emit(is_estop)
            print(f"[GPIO E-Stop] {'🔴 비상정지 발동' if is_estop else '🟢 비상정지 해제'}")

    @property
    def is_active(self):
        return self._active
