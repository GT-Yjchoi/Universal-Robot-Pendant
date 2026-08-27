"""Small state bridges exposed to the single QML application engine."""

from PySide6.QtCore import QObject, Property, Signal, Slot


class TopBarBackend(QObject):
    changed = Signal()
    jogRequested = Signal()
    alarmRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False
        self._recipe = "No Data"
        self._mode = "모드: 정지"
        self._mode_color = "#95a5a6"
        self._alarm = ""
        self.op_status = 0

    connected = Property(bool, lambda self: self._connected, notify=changed)
    recipeName = Property(str, lambda self: self._recipe, notify=changed)
    modeText = Property(str, lambda self: self._mode, notify=changed)
    modeColor = Property(str, lambda self: self._mode_color, notify=changed)
    alarmText = Property(str, lambda self: self._alarm, notify=changed)

    @Slot()
    def requestJog(self):
        self.jogRequested.emit()

    @Slot()
    def requestAlarm(self):
        self.alarmRequested.emit()

    @Slot(bool)
    def set_connected(self, connected):
        connected = bool(connected)
        if connected != self._connected:
            self._connected = connected
            self.changed.emit()

    def set_recipe(self, recipe):
        recipe = str(recipe)
        if recipe != self._recipe:
            self._recipe = recipe
            self.changed.emit()

    @Slot(dict)
    def update_monitor(self, data):
        # PLC 모니터 블록에는 DT201(팬던트 소유 운전상태)이 포함되지 않는다.
        # op_status가 없는 입출력 갱신에서는 현재 화면 상태를 유지한다.
        status = int(data.get("op_status", self.op_status))
        alarms = list(data.get("axis_alarms", []))
        if status == 1:
            mode, color = "모드: 자동운전", "#2ecc71"
        elif status == 2:
            mode, color = "모드: 확인운전", "#f1c40f"
        else:
            mode, color = "모드: 정지", "#95a5a6"
        alarm = (
            "[!] 비상정지" if 9 in alarms
            else f"[!] 알람 ({len(alarms)}축)" if alarms
            else ""
        )
        values = (status, mode, color, alarm)
        old = (self.op_status, self._mode, self._mode_color, self._alarm)
        if values != old:
            self.op_status, self._mode, self._mode_color, self._alarm = values
            self.changed.emit()


class NavBackend(QObject):
    changed = Signal()
    selected = Signal(str, int)

    def __init__(self, keys, labels, parent=None):
        super().__init__(parent)
        self._keys = list(keys)
        self._labels = list(labels)
        self._current = 0

    labels = Property(list, lambda self: self._labels, notify=changed)
    currentIndex = Property(int, lambda self: self._current, notify=changed)

    @Slot(int)
    def choose(self, index):
        if 0 <= index < len(self._keys):
            self.selected.emit(self._keys[index], index)

    def set_current(self, index):
        if index != self._current:
            self._current = index
            self.changed.emit()

    def set_labels(self, labels):
        labels = list(labels)
        if labels != self._labels:
            self._labels = labels
            self.changed.emit()
