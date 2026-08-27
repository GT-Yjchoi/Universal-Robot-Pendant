"""Alarm definitions without any QWidget dependencies."""

from utils.json_utils import load_json, save_json
from utils.paths import get_settings_path


USER_ALARMS = {}

STEP_ALARM_DESCRIPTIONS = {
    21: "POS 축 이동 확인 실패 - BUSY 상승을 감지하지 못함",
    22: "패킹 베이스 인덱스 범위 오류",
    50: "병렬 CALL 실패 - 병렬 워커 2개 모두 실행중",
    93: "동기 CALL 스택 오버플로 - 4레벨 초과",
    94: "CALL 사용 불가 - 병렬 워커에서 서브 CALL 금지",
    95: "JMP 타겟 스텝 번호 범위 초과",
    96: "CALL 슬롯 번호 범위 초과",
    97: "실행 슬롯 번호 범위 초과",
    98: "OUT 지연 타이머 슬롯 없음",
    99: "알 수 없는 커맨드",
}


def load_user_alarms(settings_path=None):
    path = settings_path or get_settings_path()
    try:
        saved = (load_json(path) or {}).get("sequence_alarms", {})
        USER_ALARMS.clear()
        USER_ALARMS.update({int(key): value for key, value in saved.items()})
    except (OSError, ValueError, TypeError):
        pass


def save_user_alarms(settings_path=None):
    path = settings_path or get_settings_path()
    settings = load_json(path) or {}
    settings["sequence_alarms"] = {
        str(key): value for key, value in sorted(USER_ALARMS.items())
    }
    save_json(path, settings)


load_user_alarms()
