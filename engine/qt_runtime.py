"""Qt bridges for pendant-side sequence execution."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .dio_backend import FastechI8O8Backend
from .plc_command_backend import FP0HCommandBackend
from .step_executor import ExecutionStatus, ExecutorState, SequenceExecutor
from utils.variable_store import VariableStore, MAX_DATA, PLC_DATA_START
from utils.io_manager import IOManager


class InputTimeoutRequest:
    def __init__(self, step):
        self.step = dict(step)
        self._event = threading.Event()
        self.decision = "stop"

    def resolve(self, accepted):
        self.decision = "reset" if bool(accepted) else "stop"
        self._event.set()


class LocalDIORuntime(QObject):
    sig_connected = Signal(bool)
    sig_monitor_data = Signal(dict)
    sig_error = Signal(str)
    sig_executor_status = Signal(object)

    def __init__(self, sequences, host="192.168.0.5", parent=None, position_points=None,
                 variable_store=None, alarm_provider=None):
        super().__init__(parent)
        self.sequences = sequences
        self.position_points = position_points if position_points is not None else {}
        self.variable_store = variable_store or VariableStore()
        self.host = host
        self.backend = None
        self.executor = None
        self.is_connected = False
        self.current_mode = 0
        self.current_sequence = ""
        self.current_step = -1
        self.current_execution_id = 0
        self.current_event_message = ""
        self.last_error = ""
        self._external_alarm_provider = alarm_provider
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
                alarm_provider=self._alarm_active,
                safe_off_on_stop=True,
                output_stop_callback=self._apply_output_stop_policy,
                variable_store=self.variable_store,
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

    def _alarm_active(self):
        external = False
        if self._external_alarm_provider is not None:
            try:
                external = bool(self._external_alarm_provider())
            except Exception:
                external = False
        return external or bool(self.last_error)

    def _apply_output_stop_policy(self):
        if self.backend is not None:
            self.backend.reset_outputs(IOManager.instance().reset_output_indices())

    @Slot(int)
    def start_mode(self, mode):
        if mode == 0:
            self.stop(); return
        if int(mode) == 2:
            self.prepare_check_mode(); return
        if not self.is_connected or self.executor is None:
            self.sig_error.emit("Ezi-IO is not connected"); return
        try:
            self.current_mode = int(mode)
            self.variable_store.reset_auto()
            self.executor.start(self.sequences, "Main")
            self._poll_io()
        except Exception as exc:
            self.current_mode = 0
            self.last_error = str(exc)
            self.sig_error.emit(self.last_error)

    @Slot()
    def prepare_check_mode(self):
        """Enter check-run mode without starting the Main sequence."""
        if not self.is_connected or self.executor is None:
            self.sig_error.emit("Ezi-IO is not connected"); return
        if self.executor.is_running:
            return
        self.current_mode = 2
        self._poll_io()

    @Slot()
    def start_check(self):
        """Start a prepared check run, or resume it when paused."""
        if self.current_mode != 2 or not self.is_connected or self.executor is None:
            return
        try:
            if self.executor.state == ExecutorState.PAUSED:
                self.executor.resume()
            elif not self.executor.is_running:
                self.variable_store.reset_auto()
                self.executor.start(self.sequences, "Main")
                self._poll_io()
        except Exception as exc:
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
        self.current_execution_id = status.execution_id
        self.current_event_message = status.message
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
        check_state = 0
        if self.current_mode == 2:
            if self.executor.state == ExecutorState.RUNNING:
                check_state = 1
            elif self.executor.state == ExecutorState.PAUSED:
                check_state = 2
        self.sig_monitor_data.emit({
            "inputs": [int(inputs) & 0xFF], "outputs": [int(outputs) & 0xFF],
            "op_status": self.current_mode,
            "check_run_status": check_state,
            "current_step": self.current_step, "sub_seq_idx": 0,
            "local_sequence": self.current_sequence, "local_dio": True,
            "local_execution_id": self.current_execution_id,
            "local_event_message": self.current_event_message,
            "local_execution_source": "main",
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
    sig_monitor_executor_status = Signal(object)
    sig_timeout_request = Signal(object)
    sig_nonblocking_alarm = Signal(int, str)

    def __init__(self, sequences, plc_client, parent=None, position_points=None,
                 mode_provider=None, packing_config=None, variable_store=None,
                 alarm_provider=None):
        super().__init__(parent)
        self.sequences = sequences
        self.position_points = position_points if position_points is not None else {}
        self.packing_config = packing_config if packing_config is not None else {}
        self.plc_client = plc_client
        self.variable_store = variable_store or VariableStore()
        self.backend = FP0HCommandBackend(plc_client)
        self._last_monitor = {}
        self._last_monitor_at = 0.0
        self._external_alarm_provider = alarm_provider
        self.executor = SequenceExecutor(
            self.backend, poll_interval=0.005,
            status_callback=self.sig_executor_status.emit,
            position_points=self.position_points,
            position_transform=self._transform_position,
            position_provider=self._axis_positions_for_condition,
            mode_provider=mode_provider,
            state_provider=lambda: self.current_mode,
            alarm_provider=self._alarm_active,
            event_callback=self._executor_event,
            safe_off_on_stop=True,
            output_stop_callback=self._apply_output_stop_policy,
            variable_store=self.variable_store,
        )
        self.monitor_executor = SequenceExecutor(
            self.backend, poll_interval=0.005,
            status_callback=self.sig_monitor_executor_status.emit,
            position_points=self.position_points,
            position_transform=self._transform_position,
            position_provider=self._axis_positions_for_condition,
            mode_provider=mode_provider,
            state_provider=lambda: self.current_mode,
            alarm_provider=self._alarm_active,
            safe_off_on_stop=False,
            variable_store=self.variable_store,
        )
        self.is_connected = bool(plc_client.is_connected)
        self.current_mode = 0
        self.current_sequence = ""
        self.current_step = -1
        self.current_execution_id = 0
        self.current_event_message = ""
        self.last_error = ""
        self._last_monitor_error = ""
        self._timeout_alarm_lock = threading.Lock()
        self._pending_timeout_alarms = 0
        self.sig_executor_status.connect(self._on_executor_status)
        self.sig_monitor_executor_status.connect(self._on_monitor_executor_status)
        plc_client.sig_connected.connect(self._on_connected)
        plc_client.sig_monitor_data.connect(self._on_plc_monitor)
        self._monitor_restart_timer = QTimer(self)
        self._monitor_restart_timer.setSingleShot(True)
        self._monitor_restart_timer.timeout.connect(self._run_monitor_sequence)
        self._publish_sequence = 0
        self._publish_full = True
        self._last_publish_status = None
        self._publish_timer = QTimer(self)
        self._publish_timer.setInterval(100)
        self._publish_timer.timeout.connect(self._publish_variables)
        self._publish_timer.start()
        if self.is_connected:
            self._schedule_monitor_sequence(0)

    def _alarm_active(self):
        external = False
        if self._external_alarm_provider is not None:
            try:
                external = bool(self._external_alarm_provider())
            except Exception:
                external = False
        axis_alarms = self._last_monitor.get("axis_alarms", [])
        error_codes = self._last_monitor.get("axis_error_codes", [])
        step_alarm = int(self._last_monitor.get("step_alarm_id", 0) or 0)
        with self._timeout_alarm_lock:
            pending_timeout_alarm = self._pending_timeout_alarms > 0
        return (
            external
            or pending_timeout_alarm
            or bool(axis_alarms)
            or any(int(code) != 0 for code in error_codes)
            or step_alarm != 0
        )

    @staticmethod
    def _dint_words(value):
        value = int(value) & 0xFFFFFFFF
        return [value & 0xFFFF, (value >> 16) & 0xFFFF]

    def _publish_status_word(self):
        status = 0x0001 if self.is_connected else 0
        if self.current_mode in (1, 2):
            status |= 0x0002
        if self.executor.state == ExecutorState.PAUSED:
            status |= 0x0004
        if self.executor.state == ExecutorState.ERROR:
            status |= 0x0008
        return status

    @Slot()
    def _publish_variables(self):
        if not self.is_connected:
            return
        if self._publish_full:
            self.variable_store.mark_all_dirty()
        bits_dirty, bit_words, data_values = self.variable_store.export_snapshot()
        status_word = self._publish_status_word()
        if (not self._publish_full and not bits_dirty and not data_values
                and status_word == self._last_publish_status):
            return
        priority = 30  # Motion, stop and output commands stay ahead of telemetry.
        if bits_dirty:
            self.plc_client.submit(
                self.plc_client.write_words, 0x09, 504, bit_words,
                priority=priority,
            )
        if self._publish_full or len(data_values) > 8:
            words = [0] * (MAX_DATA * 2)
            for address, value in data_values.items():
                offset = int(address) - PLC_DATA_START
                if 0 <= offset <= len(words) - 2:
                    words[offset:offset + 2] = self._dint_words(value)
            self.plc_client.submit(
                self.plc_client.write_words, 0x09, PLC_DATA_START, words,
                priority=priority,
            )
        else:
            for address, value in sorted(data_values.items()):
                self.plc_client.submit(
                    self.plc_client.write_words, 0x09, int(address),
                    self._dint_words(value), priority=priority,
                )
        self._publish_sequence = (self._publish_sequence % 65535) + 1
        self.plc_client.submit(
            self.plc_client.write_words, 0x09, 500,
            [2, self._publish_sequence, status_word, 0],
            priority=priority,
        )
        self._publish_full = False
        self._last_publish_status = status_word

    def _transform_position(self, step):
        if not step.get("pack_base") or not self.packing_config.get("enabled", False):
            return step
        resolved = dict(step)
        coords = list(resolved.get("coords", (0.0,) * 8))
        while len(coords) < 8:
            coords.append(0.0)
        pack_idx = list(self.packing_config.get("current_indices", (0, 0, 0)))
        while len(pack_idx) < 3:
            pack_idx.append(0)
        for axis, key in enumerate(("x", "y", "z")):
            pitch = float(self.packing_config.get(f"{key}_pitch", 0.0))
            direction = 1 if int(self.packing_config.get(f"{key}_dir", 1)) >= 0 else -1
            coords[axis] += int(pack_idx[axis]) * pitch * direction
        resolved["coords"] = coords
        return resolved

    def _axis_positions_for_condition(self):
        if (not self.is_connected or not self._last_monitor_at
                or time.monotonic() - self._last_monitor_at > 0.5):
            raise RuntimeError("PLC 실제 축 위치 데이터가 없거나 갱신이 중단되었습니다.")
        positions = self._last_monitor.get("axis_pos")
        if not isinstance(positions, list) or len(positions) < 8:
            raise RuntimeError("PLC 실제 축 위치 데이터가 올바르지 않습니다.")
        return list(positions[:8])

    def _executor_event(self, event_name, step):
        action = event_name.partition(":")[2]
        alarm_no = int(step.get("timeout_alarm_no", 0))
        label = str(step.get("name", f"입력 {step.get('port', 0)}"))
        if action == "alarm_go":
            self.sig_nonblocking_alarm.emit(alarm_no, label)
            return None
        if action != "continue":
            return None
        request = InputTimeoutRequest(step)
        # "알람 후 진행여부 선택" is an actual active alarm while its
        # decision popup is pending.  Monitor JMP(알람발생) must see it even
        # though this UI uses the shared confirm popup instead of AlarmOverlay.
        with self._timeout_alarm_lock:
            self._pending_timeout_alarms += 1
        try:
            self.sig_timeout_request.emit(request)
            while not request._event.wait(0.05):
                if self.executor._stop.is_set():
                    return False
            return request.decision
        finally:
            with self._timeout_alarm_lock:
                self._pending_timeout_alarms = max(
                    0, self._pending_timeout_alarms - 1
                )

    @Slot(bool)
    def _on_connected(self, connected):
        self.is_connected = bool(connected)
        self.sig_connected.emit(self.is_connected)
        if self.is_connected:
            self._last_monitor_error = ""
            self._publish_full = True
            self.variable_store.mark_all_dirty()
            self.plc_client.submit(
                self.plc_client.reset_axis_jog, priority=-30,
            )
            self.plc_client.submit(
                self.plc_client.send_operation_state, self.current_mode,
                priority=-10,
            )
            self._schedule_monitor_sequence(0)
        else:
            self._monitor_restart_timer.stop()
            self.monitor_executor.stop(wait=False)

    @Slot(dict)
    def _on_plc_monitor(self, data):
        self._last_monitor = dict(data)
        self._last_monitor_at = time.monotonic()
        self._emit_monitor()

    @Slot(int)
    def start_mode(self, mode):
        if int(mode) == 0:
            self.stop(); return
        if int(mode) == 2:
            self.prepare_check_mode(); return
        if not self.is_connected:
            self.sig_error.emit("PLC is not connected"); return
        try:
            self.current_mode = int(mode)
            self.variable_store.reset_auto()
            self.plc_client.submit(
                self.plc_client.send_axis_stop, False, priority=-20,
            )
            self.plc_client.submit(
                self.plc_client.send_operation_state, self.current_mode,
                priority=-10,
            )
            self._run_monitor_sequence()
            self.executor.start(self.sequences, "Main")
            self._emit_monitor()
        except Exception as exc:
            self.current_mode = 0
            self.plc_client.submit(
                self.plc_client.send_operation_state, 0, priority=-10,
            )
            self.last_error = str(exc)
            self.sig_error.emit(self.last_error)

    @Slot()
    def prepare_check_mode(self):
        """Select check-run mode while keeping the Main sequence stopped."""
        if not self.is_connected:
            self.sig_error.emit("PLC is not connected"); return
        if self.executor.is_running:
            return
        self.current_mode = 2
        self.plc_client.submit(
            self.plc_client.send_operation_state, self.current_mode,
            priority=-10,
        )
        self._run_monitor_sequence()
        self._emit_monitor()

    @Slot()
    def start_check(self):
        """Start a prepared check run, or resume the paused executor."""
        if self.current_mode != 2 or not self.is_connected:
            return
        try:
            if self.executor.state == ExecutorState.PAUSED:
                self.executor.resume()
                return
            if self.executor.is_running:
                return
            self.variable_store.reset_auto()
            self.plc_client.submit(
                self.plc_client.send_axis_stop, False, priority=-20,
            )
            self.plc_client.submit(
                self.plc_client.send_operation_state, self.current_mode,
                priority=-10,
            )
            self._run_monitor_sequence()
            self.executor.start(self.sequences, "Main")
            self._emit_monitor()
        except Exception as exc:
            self.last_error = str(exc)
            self.sig_error.emit(self.last_error)

    @Slot()
    def stop(self):
        was_running = self.executor.is_running
        self.current_mode = 0
        if self.is_connected:
            self.plc_client.submit(
                self.plc_client.send_axis_stop, True, priority=-20,
            )
            self.plc_client.submit(
                self.plc_client.send_operation_state, 0, priority=-10,
            )
        if was_running:
            self.executor.stop(wait=False)
        else:
            threading.Thread(target=self._idle_safe_stop, name="plc-idle-stop", daemon=True).start()
        self._emit_monitor()

    def _idle_safe_stop(self):
        try:
            self._apply_output_stop_policy()
        finally:
            self._run_monitor_sequence()

    def _apply_output_stop_policy(self):
        self.backend.reset_outputs(IOManager.instance().reset_output_indices())

    def _run_monitor_sequence(self):
        steps = self.sequences.get("Monitor")
        if (not self.is_connected or not isinstance(steps, list) or not steps
                or self.monitor_executor.is_running):
            return
        position_path = self._monitor_position_path()
        if position_path:
            message = (
                "Monitor 프로그램에서는 위치이동(POS)을 실행할 수 없습니다. "
                f"경로: {' → '.join(position_path)}"
            )
            self.last_error = message
            if message != self._last_monitor_error:
                self._last_monitor_error = message
                self.sig_error.emit(message)
            self._schedule_monitor_sequence(1000)
            return
        try:
            self.monitor_executor.start(self.sequences, "Monitor")
        except Exception as exc:
            self.last_error = str(exc)
            if self.last_error != self._last_monitor_error:
                self._last_monitor_error = self.last_error
                self.sig_error.emit(self.last_error)
            self._schedule_monitor_sequence(1000)

    def _monitor_position_path(self):
        def walk(sequence_name, path):
            if sequence_name in path:
                return None
            next_path = path + [sequence_name]
            steps = self.sequences.get(sequence_name, [])
            if not isinstance(steps, list):
                return None
            for step in steps:
                kind = str(step.get("type", "")).upper()
                if kind == "POS":
                    return next_path
                if kind == "CALL":
                    found = walk(str(step.get("target_seq", "")), next_path)
                    if found:
                        return found
            return None
        return walk("Monitor", [])

    def _schedule_monitor_sequence(self, delay_ms=100):
        steps = self.sequences.get("Monitor")
        if not self.is_connected or not isinstance(steps, list) or not steps:
            return
        self._monitor_restart_timer.start(max(0, int(delay_ms)))

    @Slot(object)
    def _on_monitor_executor_status(self, status: ExecutionStatus):
        # Monitor itself remains hidden, but a normal Sub called by Monitor is
        # still shown in the all-program execution monitor.
        if status.sequence and status.sequence != "Monitor":
            self.sig_monitor_data.emit({
                "op_status": self.current_mode,
                "current_step": status.step_index,
                "local_sequence": status.sequence,
                "local_execution_id": status.execution_id,
                "local_event_message": status.message,
                "local_execution_source": "monitor",
                "pendant_sequence": True,
                "background_sequence": True,
            })
        if status.state == ExecutorState.ERROR:
            self.last_error = status.message
            if self.last_error != self._last_monitor_error:
                self._last_monitor_error = self.last_error
                self.sig_error.emit(self.last_error)
            self._schedule_monitor_sequence(1000)
            return
        if status.state == ExecutorState.IDLE:
            self._last_monitor_error = ""
            self._schedule_monitor_sequence(100)

    @Slot()
    def refresh_monitor_sequence(self):
        """Apply an edited Monitor program without coupling it to Main mode."""
        self._last_monitor_error = ""
        self._monitor_restart_timer.stop()
        if self.monitor_executor.is_running:
            self.monitor_executor.stop(wait=False)
        self._schedule_monitor_sequence(100)

    @Slot()
    def pause(self): self.executor.pause()

    @Slot()
    def resume(self): self.executor.resume()

    @Slot()
    def home(self):
        if not self.is_connected:
            self.sig_error.emit("PLC is not connected"); return
        threading.Thread(target=self._home_worker, name="plc-home-command", daemon=True).start()

    @Slot()
    def reset(self):
        if not self.is_connected:
            self.sig_error.emit("PLC is not connected"); return
        threading.Thread(target=self._reset_worker, name="plc-reset-command", daemon=True).start()

    def _home_worker(self):
        try:
            self.backend.home()
        except Exception as exc:
            self.last_error = str(exc)
            self.sig_error.emit(self.last_error)

    def _reset_worker(self):
        try:
            self.backend.reset()
        except Exception as exc:
            self.last_error = str(exc)
            self.sig_error.emit(self.last_error)

    def _advance_packing_index(self):
        if not self.packing_config.get("enabled", False):
            return
        axes = ("x", "y", "z")
        orders = (
            ("x", "y", "z"), ("x", "z", "y"), ("y", "x", "z"),
            ("y", "z", "x"), ("z", "x", "y"), ("z", "y", "x"),
        )
        values = list(self.packing_config.get("current_indices", (0, 0, 0)))[:3]
        while len(values) < 3:
            values.append(0)
        current = dict(zip(axes, (max(0, int(v)) for v in values)))
        order = orders[int(self.packing_config.get("stack_order", 0)) % len(orders)]
        for axis in order:
            current[axis] += 1
            count = max(1, int(self.packing_config.get(f"{axis}_count", 1)))
            if current[axis] < count:
                break
            current[axis] = 0
        self.packing_config["current_indices"] = [current[axis] for axis in axes]

    @Slot(object)
    def _on_executor_status(self, status: ExecutionStatus):
        self.current_sequence = status.sequence
        self.current_step = status.step_index
        self.current_execution_id = status.execution_id
        self.current_event_message = status.message
        if status.state == ExecutorState.IDLE and status.message == "completed":
            self._advance_packing_index()
        if status.state in (ExecutorState.IDLE, ExecutorState.ERROR):
            self.current_mode = 0
            if self.is_connected:
                if status.state == ExecutorState.ERROR:
                    self.plc_client.submit(
                        self.plc_client.send_axis_stop, True, priority=-20,
                    )
                self.plc_client.submit(
                    self.plc_client.send_operation_state, 0, priority=-10,
                )
        if status.state == ExecutorState.ERROR:
            self.last_error = status.message
            self.sig_error.emit(status.message)
        if status.state == ExecutorState.IDLE:
            self._run_monitor_sequence()
        self._emit_monitor()

    def _emit_monitor(self):
        data = dict(self._last_monitor)
        check_state = 0
        if self.current_mode == 2:
            if self.executor.state == ExecutorState.RUNNING:
                check_state = 1
            elif self.executor.state == ExecutorState.PAUSED:
                check_state = 2
        data.update({
            "op_status": self.current_mode,
            "check_run_status": check_state,
            "current_step": self.current_step,
            "local_sequence": self.current_sequence,
            "pendant_sequence": True,
            "local_execution_id": self.current_execution_id,
            "local_event_message": self.current_event_message,
            "local_execution_source": "main",
        })
        self.sig_monitor_data.emit(data)

    def close(self):
        self._publish_timer.stop()
        self._monitor_restart_timer.stop()
        try:
            self.monitor_executor.stop(wait=True)
            self.executor.close()
        except Exception as exc:
            print(f"[Pendant Executor] close safety reset failed: {exc}")
