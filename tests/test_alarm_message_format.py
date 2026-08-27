import unittest

from ui.alarm_catalog import USER_ALARMS
from ui.qml_controller import _format_user_alarm


class AlarmMessageFormatTests(unittest.TestCase):
    def test_configured_user_alarm_includes_number_and_message(self):
        previous = dict(USER_ALARMS)
        try:
            USER_ALARMS[1] = "안전문 입력을 확인하세요"
            self.assertEqual(
                _format_user_alarm(1),
                "A-001: 안전문 입력을 확인하세요",
            )
        finally:
            USER_ALARMS.clear()
            USER_ALARMS.update(previous)

    def test_missing_user_alarm_has_clear_fallback(self):
        previous = dict(USER_ALARMS)
        try:
            USER_ALARMS.pop(999, None)
            self.assertEqual(_format_user_alarm(999), "A-999: 사용자 알람 #999")
        finally:
            USER_ALARMS.clear()
            USER_ALARMS.update(previous)


if __name__ == "__main__":
    unittest.main()
