"""Qt bridges for pendant-side sequence execution."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .dio_backend import FastechI8O8Backend
from .plc_command_backend import FP0HCommandBackend
from .step_executor import ExecutionStatus, ExecutorState, SequenceExecutor


class InputTimeoutRequest:
    def __init__(self, step):
        self.step = dict(step)
        self._event = threading.Event()
        self.accepted = False

    def resolve(self, accepted):
        self.accepted = bool(accepted)
        self._event.set()


class LocalDIORuntime(QObject):
    sig_connected = Signal(bool)
    sig_monitor_data = Signal(dict)
    sig_error = Signal(str)
    sig_executor_status = Signal(object)

    def __init__(self, sequences, host="192.168.0.5", parent=None, position_points=None):
        super().__init__(parent)
        self.sequences = sequences
        self.position_points = position_points if position_points is not None else {}
        self.host = host
        self.backend = None
        self.executor = None
        self.is_connected = False
        self.current_mode = 0
        self.current_sequence = ""
        self.current_step = -1
        self.last_error = ""
        self.sig_executor_status.connect(self._on_executor_status)
        self._poll = QTimer(self)
        self._poll.setInterval(20)
        self._poll.timeout.connect(self._poll_io)
        QTimer.singleShot(0, self.connect_device)

    @Slot()
    def connect_device(self):
        if self.is_connected:
            return
        try:
            self.backend = FastechI8O8Backend(self.host, timeout=0.1)
            self.executor = SequenceExecutor(
                self.backend, poll_interval=0.005,
                status_callback=self.sig_executor_status.emit,
                position_points=self.position_points,
                state_provider=lambda: self.current_mode,
                safe_off_on_stop=True,
            )
            self.is_connected = True
            self.last_error = ""
            self._poll.start()
            self.sig_connected.emit(True)
            self._poll_io()
            print(f"[Local DIO] connected: {self.host}")
        except Exception as exc:
            self.last_error = str(exc)
            self.is_connected = False
            self.sig_connected.emit(False)
            self.sig_error.emit(self.last_error)
            print(f"[Local DIO] connection failed: {exc}")

    @Slot(int)
    def start_mode(self, mode):
        if mode == 0:
            self.stop(); return
        if not self.is_connected or self.executor is None:
            self.sig_error.emit("Ezi-IO is not connected"); return
        try:
            self.current_mode = int(mode)
            self.executor.start(self.sequences, "Main")
            self._poll_io()
        except Exception as exc:
            self.current_mode = 0
            self.last_error = str(exc)
            self.sig_error.emit(self.last_error)

    @Slot()
    def stop(self):
        if self.executor is not None:
            self.executor.stop(wait=False)
        self.current_mode = 0
        self._poll_io()

    @Slot()
    def pause(self):
        if self.executor is not None: self.executor.pause()

    @Slot()
    def resume(self):
        if self.executor is not None: self.executor.resume()

    @Slot(object)
    def _on_executor_status(self, status: ExecutionStatus):
        self.current_sequence = status.sequence
        self.current_step = status.step_index
        if status.state in (ExecutorState.IDLE, ExecutorState.ERROR):
            self.current_mode = 0
        if status.state == ExecutorState.ERROR:
            self.last_error = status.message
            self.sig_error.emit(status.message)
        self._emit_monitor(status.inputs, status.outputs)

    @Slot()
    def _poll_io(self):
        if not self.is_connected or self.backend is None: return
        try:
            self._emit_monitor(self.backend.read_inputs(), self.backend.read_outputs())
        except Exception as exc:
            self.last_error = str(exc); self.sig_error.emit(self.last_error)

    def _emit_monitor(self, inputs, outputs):
        self.sig_monitor_data.emit({
            "inputs": [int(inputs) & 0xFF], "outputs": [int(outputs) & 0xFF],
            "op_status": self.current_mode,
            "check_run_status": 1 if self.current_mode == 2 else 0,
            "current_step": self.current_step, "sub_seq_idx": 0,
            "local_sequence": self.current_sequence, "local_dio": True,
        })

    def close(self):
        self._poll.stop()
        if self.executor is not None:
            try: self.executor.close()
            except Exception as exc: print(f"[Local DIO] close safety reset failed: {exc}")
        self.executor = self.backend = None
        self.is_connected = False


class PLCSequenceRuntime(QObject):
    """Executes recipe control flow on Pi and hardware commands on FP0H."""

    sig_connected = Signal(bool)
    sig_monitor_data = Signal(dict)
    sig_error = Signal(str)
    sig_executor_status = Signal(object)
    sig_timeout_request = Signal(object)
    sig_nonblocking_alarm = Signal(int, str)

    def __init__(self, sequences, plc_client, parent=None, position_points=None,
                 mode_provider=None, packing_config=None):
        super().__init__(parent)
        self.sequences = sequences
        self.position_points = position_points if position_points is not None else {}
        self.packing_config = packing_config if packing_config is not None else {}
        self.plc_client = plc_client
        self.backend = FP0HCommandBackend(plc_client)
        self.executor = SequenceExecutor(
            self.backend, poll_interval=0.005,
            status_callback=self.sig_executor_status.emit,
            position_points=self.position_points,
            position_transform=self._transform_position,
            mode_provider=mode_provider,
            state_provider=lambda: self.current_mode,
            event_callback=self._executor_event,
            safe_off_on_stop=True,
        )
        self.monitor_executor = SequenceExecutor(
            self.backend, poll_interval=0.005,
            position_points=self.position_points,
            state_provider=lambda: self.current_mode,
            safe_off_on_stop=False,
        )
        self.is_connected = bool(plc_client.is_connected)
        self.current_mode = 0
        self.current_sequence = ""
        self.current_step = -1
        self.last_error = ""
        self._last_monitor = {}
        self.sig_executor_status.connect(self._on_executor_status)
        plc_client.sig_connected.connect(self._on_connected)
        plc_client.sig_monitor_data.connect(self._on_plc_monitor)

    def _transform_position(self, step):
        if not step.get("pack_base") or not self.packing_config.get("enabled", False):
            return step
        resolved = dict(step)
        coords = list(resolved.get("coords", (0.0,) * 8))
        while len(coords) < 8:
            coords.append(0.0)
        pack_idx = list(self._last_monitor.get("pack_idx", (0, 0, 0)))
        while len(pack_idx) < 3:
            pack_idx.append(0)
        for axis, key in enumerate(("x", "y", "z")):
            pitch = float(self.packing_config.get(f"{key}_pitch", 0.0))
            direction = 1 if int(self.packing_config.get(f"{key}_dir", 1)) >= 0 else -1
            coords[axis] += int(pack_idx[axis]) * pitch * direction
        resolved["coords"] = coords
        return resolved

    def _executor_event(self, event_name, step):
        action = event_name.partition(":")[2]
        alarm_no = int(step.get("timeout_alarm_no", 0))
        label = str(step.get("name", f"입력 {step.get('port', 0)}"))
        if action == "alarm_go":
            self.sig_nonblocking_alarm.emit(alarm_no, label)
            return None
        if action != "ask":
            return None
        request = InputTimeoutRequest(step)
        self.sig_timeout_request.emit(request)
        while not request._event.wait(0.05):
            if self.executor._stop.is_set():
                return False
        return request.accepted

    @Slot(bool)
    def _on_connected(self, connected):
        self.is_connected = bool(connected)
        self.sig_connected.emit(self.is_connected)

    @Slot(dict)
    def _on_plc_monitor(self, data):
        self._last_monitor = dict(data)
        self._emit_monitor()

    @Slot(int)
    def start_mode(self, mode):
        if int(mode) == 0:
            self.stop(); return
        if not self.is_connected:
            self.sig_error.emit("PLC is not connected"); return
        try:
            self.current_mode = int(mode)
            self._run_monitor_sequence()
            self.executor.start(self.sequences, "Main")
            self._emit_monitor()
        except Exception as exc:
            self.current_mode = 0
            self.last_error = str(exc)
            self.sig_error.emit(self.last_error)

    @Slot()
    def stop(self):
        was_running = self.executor.is_running
        self.current_mode = 0
        if was_running:
            self.executor.stop(wait=False)
        else:
            threading.Thread(target=self._idle_safe_stop, name="plc-idle-stop", daemon=True).start()
        self._emit_monitor()

    def _idle_safe_stop(self):
        try:
            self.backend.all_outputs_off()
        finally:
            self._run_monitor_sequence()

    def _run_monitor_sequence(self):
        if "Monitor" not in self.sequences or self.monitor_executor.is_running:
            return
        try:
            self.monitor_executor.start(self.sequences, "Monitor")
        except Exception as exc:
            self.last_error = str(exc)
            self.sig_error.emit(self.last_error)

    @Slot()
    def pause(self): self.executor.pause()

    @Slot()
    def resume(self): self.executor.resume()

    @Slot()
    def home(self):
        if not self.is_connected:
            self.sig_error.emit("PLC is not connected"); return
        threading.Thread(target=self._home_worker, name="plc-home-command", daemon=True).start()

    def _home_worker(self):
        try:
            self.backend.home()
        except Exception as exc:
            self.last_error = str(exc)
            self.sig_error.emit(self.last_error)

    @Slot(object)
    def _on_executor_status(self, status: ExecutionStatus):
        self.current_sequence = status.sequence
        self.current_step = status.step_index
        if status.state in (ExecutorState.IDLE, ExecutorState.ERROR):
            self.current_mode = 0
        if status.state == ExecutorState.ERROR:
            self.last_error = status.message
            self.sig_error.emit(status.message)
        if status.state == ExecutorState.IDLE:
            self._run_monitor_sequence()
        self._emit_monitor()

    def _emit_monitor(self):
        data = dict(self._last_monitor)
        data.update({
            "op_status": self.current_mode,
            "check_run_status": 1 if self.current_mode == 2 else 0,
            "current_step": self.current_step,
            "local_sequence": self.current_sequence,
            "pendant_sequence": True,
        })
        self.sig_monitor_data.emit(data)

    def close(self):
        try:
            self.monitor_executor.stop(wait=True)
            self.executor.close()
        except Exception as exc:
            print(f"[Pendant Executor] close safety reset failed: {exc}")
