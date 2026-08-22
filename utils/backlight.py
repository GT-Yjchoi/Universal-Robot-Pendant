"""화면 백라이트 밝기 제어 + settings.json 영구화.

sysfs /sys/class/backlight/<dev>/brightness 를 직접 기록한다(udev 규칙
99-pendant-backlight.rules 가 video 그룹에 쓰기 허용).
밝기값은 패널 무관하게 0~100(%) 으로 settings.json 의 "screen_brightness"
키에 저장하고, 적용 시 max_brightness 로 환산한다.

저장된 사용자 값을 사용하므로 부팅마다 최대 밝기로 고정하지 않는다.
"""
import glob
import os

from utils.paths import get_settings_path
from utils.json_utils import load_json, save_json

_BL_GLOB = "/sys/class/backlight/*"
MIN_PERCENT = 10   # 완전 암전(조작 불가) 방지 하한
SETTINGS_KEY = "screen_brightness"


def _dev():
    ds = sorted(glob.glob(_BL_GLOB))
    return ds[0] if ds else None


def _read_int(path, default=0):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return default


def get_max():
    d = _dev()
    return _read_int(os.path.join(d, "max_brightness"), 255) if d else 255


def _clamp(pct):
    try:
        pct = int(round(float(pct)))
    except (TypeError, ValueError):
        pct = 100
    return max(MIN_PERCENT, min(100, pct))


def get_percent():
    """저장값(settings.json) 우선, 없으면 현재 sysfs 에서 환산해 0~100 반환."""
    try:
        s = load_json(get_settings_path()) or {}
        v = s.get(SETTINGS_KEY)
        if isinstance(v, (int, float)):
            return _clamp(v)
    except Exception:
        pass
    d = _dev()
    if not d:
        return 100
    cur = _read_int(os.path.join(d, "actual_brightness"),
                    _read_int(os.path.join(d, "brightness"), get_max()))
    mx = get_max() or 255
    return _clamp(cur * 100.0 / mx)


def set_percent(pct, persist=True):
    """pct(0~100, 하한 MIN_PERCENT) 적용. 예외를 던지지 않고 bool 반환."""
    pct = _clamp(pct)
    d = _dev()
    ok = False
    if d:
        mx = get_max() or 255
        raw = max(1, int(round(pct * mx / 100.0)))
        try:
            with open(os.path.join(d, "brightness"), "w") as f:
                f.write(str(raw))
            ok = True
        except Exception as e:
            print(f"[backlight] brightness write 실패: {e}")
    if persist:
        try:
            p = get_settings_path()
            s = load_json(p) or {}
            s[SETTINGS_KEY] = pct
            save_json(p, s)
        except Exception as e:
            print(f"[backlight] settings.json 저장 실패: {e}")
    return ok


def apply_saved():
    """앱 시작 시 호출: settings.json 저장값을 sysfs 에 적용(없으면 100%)."""
    set_percent(get_percent(), persist=False)
