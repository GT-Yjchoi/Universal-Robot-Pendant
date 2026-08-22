"""Threaded, interruptible local sequence executor for digital I/O recipes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable, Mapping, Sequence

from .dio_backend import DigitalIOBackend
from .control_backend import SignalGroup


class UnsupportedStepError(RuntimeError):
    pass


class ExecutorState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(frozen=True)
class ExecutionStatus:
    state: ExecutorState
    sequence: str = ""
    step_index: int = -1
    step_type: str = ""
    message: str = ""
    inputs: int = 0
    outputs: int = 0


class SequenceExecutor:
    SUPPORTED_TYPES = {"COMMENT", "POS", "OUT", "IN", "TMR", "JMP", "CALL", "DAT", "END"}

    def __init__(
        self,
        backend: DigitalIOBackend,
        *,
        poll_interval: float = 0.005,
        status_callback: Callable[[ExecutionStatus], None] | None = None,
        position_points: Mapping[str, Mapping] | None = None,
        position_transform: Callable[[dict], Mapping] | None = None,
        mode_provider: Callable[[int], bool] | None = None,
        state_provider: Callable[[], int] | None = None,
        event_callback: Callable[[str, Mapping], bool | None] | None = None,
        safe_off_on_stop: bool = True,
    ) -> None:
        self.backend = backend
        self.poll_interval = max(0.001, float(poll_interval))
        self.status_callback = status_callback
        self.position_points = position_points if position_points is not None else {}
        self.position_transform = position_transform
        self.mode_provider = mode_provider
        self.state_provider = state_provider
        self.event_callback = event_callback
        self.safe_off_on_stop = safe_off_on_stop
        self.state = ExecutorState.IDLE
        self.last_error = ""
        self._stop = threading.Event()
        self._run_gate = threading.Event()
        self._run_gate.set()
        self._thread: threading.Thread | None = None
        self._sequences: Mapping[str, Sequence[dict]] = {}
        self._internal_bits = 0
        self._data_words: dict[int, int] = {}
        self._workers: list[threading.Thread] = []
        self._worker_error: Exception | None = None
        self._data_lock = threading.RLock()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, sequences: Mapping[str, Sequence[dict]], sequence: str = "Main") -> None:
        if self.is_running:
            raise RuntimeError("sequence executor is already running")
        if sequence not in sequences:
            raise KeyError(f"sequence not found: {sequence}")
        self.validate_sequences(sequences)
        self._sequences = sequences
        self._stop.clear()
        self._run_gate.set()
        self.last_error = ""
        self._worker_error = None
        self._workers = []
        self.state = ExecutorState.RUNNING
        self._thread = threading.Thread(
            target=self._run, args=(sequence,), name="dio-step-executor", daemon=True
        )
        self._thread.start()

    def validate_sequences(self, sequences: Mapping[str, Sequence[dict]]) -> None:
        errors = []
        for name, steps in sequences.items():
            if not isinstance(steps, Sequence):
                errors.append(f"{name}: step list is invalid")
                continue
            for index, step in enumerate(steps):
                prefix = f"{name}[{index}]"
                if not isinstance(step, Mapping):
                    errors.append(f"{prefix}: step is not an object")
                    continue
                kind = str(step.get("type", "")).upper()
                if kind not in self.SUPPORTED_TYPES:
                    errors.append(f"{prefix}: unsupported type {kind or '(empty)'}")
                    continue
                if kind == "CALL" and str(step.get("target_seq", "")) not in sequences:
                    errors.append(f"{prefix}: missing CALL target {step.get('target_seq', '')}")
                elif kind == "JMP":
                    target = int(step.get("target_idx", step.get("target_step", 0)))
                    if not 0 <= target < len(steps):
                        errors.append(f"{prefix}: JMP target {target} is out of range")
                elif kind == "POS":
                    point_name = str(step.get("point_name", ""))
                    if point_name and point_name not in self.position_points and "coords" not in step:
                        errors.append(f"{prefix}: missing position point {point_name}")
                    point = self.position_points.get(point_name, {})
                    coords = step.get("coords", point.get("coords", ()))
                    if len(coords) < 8:
                        errors.append(f"{prefix}: position requires 8 coordinates")
                    axes = step.get("active_axes", step.get("axes", (True,) * 8))
                    if len(axes) < 8:
                        errors.append(f"{prefix}: position requires 8 axis flags")
                elif kind in ("OUT", "IN") and "dio_channel" not in step:
                    group = int(step.get("out_type" if kind == "OUT" else "in_type", 0))
                    port = int(step.get("port", 0))
                    if group not in (0, 1, 2):
                        errors.append(f"{prefix}: I/O group {group} is invalid")
                    offset = (32 if kind == "IN" and group == 1 and port >= 32 else
                              100 if kind == "IN" and group == 2 and port >= 100 else 0)
                    logical = port - offset
                    limit = 31 if group == 2 else 15
                    if not 0 <= logical <= limit:
                        errors.append(f"{prefix}: I/O port {port} is out of range")
                elif kind == "DAT":
                    address = int(step.get("dat_dt_addr", step.get("dt_addr", 60000)))
                    if not 60000 <= address <= 60099:
                        errors.append(f"{prefix}: DAT address DT{address} is out of range")
        if errors:
            preview = "; ".join(errors[:8])
            if len(errors) > 8:
                preview += f"; ... and {len(errors) - 8} more"
            raise ValueError(f"recipe validation failed: {preview}")

    def pause(self) -> None:
        if self.state == ExecutorState.RUNNING:
            self._run_gate.clear()
            self.state = ExecutorState.PAUSED
            self._emit(message="paused")

    def resume(self) -> None:
        if self.state == ExecutorState.PAUSED:
            self.state = ExecutorState.RUNNING
            self._run_gate.set()
            self._emit(message="resumed")

    def stop(self, *, wait: bool = True) -> None:
        if self.is_running:
            self.state = ExecutorState.STOPPING
            self._stop.set()
            self._run_gate.set()
            if wait and threading.current_thread() is not self._thread:
                self._thread.join(timeout=2.0)
        elif self.safe_off_on_stop:
            if wait:
                self.backend.all_outputs_off()
            else:
                threading.Thread(
                    target=self.backend.all_outputs_off,
                    name="safe-output-off", daemon=True,
                ).start()

    def close(self) -> None:
        try:
            self.stop(wait=True)
        finally:
            self.backend.close()

    def _run(self, sequence: str) -> None:
        try:
            self._execute_sequence(sequence, depth=0)
            for worker in list(self._workers):
                while worker.is_alive() and not self._stop.is_set():
                    worker.join(timeout=self.poll_interval)
            if self._worker_error is not None:
                raise self._worker_error
            if not self._stop.is_set():
                self.state = ExecutorState.IDLE
                self._emit(message="completed")
        except Exception as exc:
            self.last_error = str(exc)
            self.state = ExecutorState.ERROR
            self._emit(message=self.last_error)
        finally:
            if self.safe_off_on_stop:
                try:
                    self.backend.all_outputs_off()
                except Exception as exc:
                    if not self.last_error:
                        self.last_error = f"safe output reset failed: {exc}"
                        self.state = ExecutorState.ERROR
            if self.state == ExecutorState.STOPPING:
                self.state = ExecutorState.IDLE
                self._emit(message="stopped")

    def _execute_sequence(self, name: str, depth: int) -> None:
        if depth > 16:
            raise RuntimeError("CALL depth exceeded 16")
        steps = self._sequences.get(name)
        if steps is None:
            raise RuntimeError(f"CALL target does not exist: {name}")
        index = 0
        jump_guard = 0
        while index < len(steps) and not self._stop.is_set():
            self._wait_if_paused()
            step = steps[index]
            step_type = str(step.get("type", "")).upper()
            if step_type not in self.SUPPORTED_TYPES:
                raise UnsupportedStepError(f"unsupported local DIO step: {step_type or '(empty)'}")
            monitor_index = sum(
                1 for prior in steps[:index] if str(prior.get("type", "")).upper() != "COMMENT"
            )
            self._emit(name, monitor_index, step_type)

            if step_type == "COMMENT":
                index += 1
            elif step_type == "POS":
                move = getattr(self.backend, "move", None)
                if move is None:
                    raise UnsupportedStepError("backend does not support POS")
                move(self._resolve_position(step))
                index += 1
            elif step_type == "OUT":
                delay = float(step.get("delay_time", 0.0)) if step.get("delay_enable") else 0.0
                if delay > 0 and not self._sleep(delay):
                    return
                self._write_step_output(step)
                index += 1
            elif step_type == "IN":
                if not self._wait_input(step):
                    return
                index += 1
            elif step_type == "TMR":
                if step.get("tmr_mode") == "hold":
                    if not self._wait_held_input(step):
                        return
                elif not self._sleep(max(0.0, float(step.get("time", 0.0)))):
                    return
                index += 1
            elif step_type == "JMP":
                if self._jump_condition(step):
                    target = int(step.get("target_idx", step.get("target_step", 0)))
                    if not 0 <= target < len(steps):
                        raise RuntimeError(f"JMP target out of range: {target}")
                    index = target
                    jump_guard += 1
                    if jump_guard > 1_000_000:
                        raise RuntimeError("JMP guard exceeded")
                else:
                    index += 1
            elif step_type == "CALL":
                target = str(step.get("target_seq", ""))
                if step.get("parallel"):
                    worker = threading.Thread(
                        target=self._parallel_sequence,
                        args=(target, depth + 1),
                        name=f"pendant-call-{target}", daemon=True,
                    )
                    self._workers.append(worker)
                    worker.start()
                else:
                    self._execute_sequence(target, depth + 1)
                index += 1
            elif step_type == "DAT":
                self._execute_dat(step)
                index += 1
            elif step_type == "END":
                return

    @staticmethod
    def _channel(step: Mapping) -> int:
        channel = int(step.get("dio_channel", step.get("port", 0)))
        if not 0 <= channel <= 7:
            raise RuntimeError(f"DIO channel out of range: {channel}")
        return channel

    def _wait_input(self, step: Mapping) -> bool:
        expected = bool(step.get("on", True))
        timeout = None
        if step.get("timeout_enabled"):
            timeout = max(0.0, float(step.get("timeout", step.get("timeout_sec", 0.0))))
        started = time.monotonic()
        while not self._stop.is_set():
            if not self._run_gate.is_set():
                paused_at = time.monotonic()
                self._wait_if_paused()
                started += time.monotonic() - paused_at
            if self._read_step_input(step) == expected:
                return True
            if timeout is not None and time.monotonic() - started >= timeout:
                action = str(step.get("timeout_action", "continue"))
                if self.event_callback is not None:
                    decision = self.event_callback(f"input_timeout:{action}", step)
                    if decision is True:
                        return True
                    if decision is False:
                        raise TimeoutError(f"input wait cancelled: port={step.get('port', 0)}")
                if action == "alarm_go":
                    return True
                if action == "ask":
                    raise TimeoutError(
                        f"input wait timed out (alarm {step.get('timeout_alarm_no', 0)}): "
                        f"port={step.get('port', 0)}"
                    )
                started = time.monotonic()
            self._stop.wait(self.poll_interval)
        return False

    def _wait_held_input(self, step: Mapping) -> bool:
        """Wait until the selected signal continuously matches for the timer duration."""
        seconds = max(0.0, float(step.get("time", 0.0)))
        expected = bool(step.get("on", True))
        matched_since: float | None = None
        while not self._stop.is_set():
            if not self._run_gate.is_set():
                paused_at = time.monotonic()
                self._wait_if_paused()
                if matched_since is not None:
                    matched_since += time.monotonic() - paused_at
            now = time.monotonic()
            if self._read_step_input(step) == expected:
                matched_since = now if matched_since is None else matched_since
                if now - matched_since >= seconds:
                    return True
            else:
                matched_since = None
            self._stop.wait(self.poll_interval)
        return False

    def _jump_condition(self, step: Mapping) -> bool:
        if not step.get("condition", False):
            return True
        cond_type = str(step.get("cond_type", "INPUT")).upper()
        expected = bool(step.get("cond_on", step.get("on", True)))
        value = int(step.get("cond_value", step.get("cond_port", step.get("port", 0))))
        if cond_type in ("INPUT", "PORT"):
            probe = {"port": value, "in_type": 0}
            return self._read_step_input(probe) == expected
        if cond_type == "VALVE":
            probe = {"port": value, "in_type": 1}
            return self._read_step_input(probe) == expected
        if cond_type in ("BIT", "INTERNAL"):
            probe = {"port": value, "in_type": 2}
            return self._read_step_input(probe) == expected
        if cond_type == "MODE":
            if self.mode_provider is None:
                raise UnsupportedStepError("mode condition requires runtime mode provider")
            return bool(self.mode_provider(value)) == expected
        if cond_type == "STATE":
            if self.state_provider is None:
                raise UnsupportedStepError("state condition requires runtime state provider")
            return (int(self.state_provider()) == value) == expected
        if cond_type in ("DTCMP", "DT", "DATA"):
            address = int(step.get("cmp_dt_addr", step.get("dt_addr", step.get("cond_addr", 60000))))
            with self._data_lock:
                left = self._data_words.get(address, 0)
            right = int(step.get("cmp_const", step.get("dt_const", step.get("cond_value", 0))))
            op = int(step.get("cmp_op", step.get("dt_op", step.get("cond_op", 0))))
            return ((left == right), (left != right), (left > right), (left >= right),
                    (left < right), (left <= right))[max(0, min(5, op))]
        raise UnsupportedStepError(f"unsupported local JMP condition: {cond_type}")

    def _write_step_output(self, step: Mapping) -> None:
        if "dio_channel" in step:
            self.backend.write_output(self._channel(step), bool(step.get("on", True)))
            return
        kind = int(step.get("out_type", 0))
        index = int(step.get("port", 0))
        enabled = bool(step.get("on", True))
        if kind == 2:
            if not 0 <= index < 32:
                raise RuntimeError(f"internal output bit out of range: {index}")
            with self._data_lock:
                if enabled:
                    self._internal_bits |= 1 << index
                else:
                    self._internal_bits &= ~(1 << index)
            return
        writer = getattr(self.backend, "write_output", None)
        if writer is None:
            raise UnsupportedStepError("backend does not support physical outputs")
        pulse_ms = int(round(float(step.get("pulse_time", 0.0)) * 1000))
        writer(SignalGroup(kind), index, enabled, pulse_ms)

    def _read_step_input(self, step: Mapping) -> bool:
        if "dio_channel" in step:
            return bool(self.backend.read_inputs() & (1 << self._channel(step)))
        kind = int(step.get("in_type", 0))
        port = int(step.get("port", 0))
        if kind == 2:
            index = port - 100 if port >= 100 else port
            if not 0 <= index < 32:
                raise RuntimeError(f"internal input bit out of range: {index}")
            with self._data_lock:
                return bool(self._internal_bits & (1 << index))
        if kind == 3:
            raise UnsupportedStepError("mode input requires runtime mode provider")
        index = port - 32 if kind == 1 and port >= 32 else port
        reader = getattr(self.backend, "read_input", None)
        if reader is None:
            raise UnsupportedStepError("backend does not support typed inputs")
        return bool(reader(SignalGroup(kind), index))

    def _execute_dat(self, step: Mapping) -> None:
        address = int(step.get("dat_dt_addr", step.get("dt_addr", step.get("address", 60000))))
        if not 60000 <= address <= 60099:
            raise RuntimeError(f"DAT address out of pendant pool: DT{address}")
        value = int(step.get("dat_const", step.get("value", step.get("constant", step.get("operand", 0)))))
        op = int(step.get("dat_op", step.get("op", step.get("operation", 0))))
        if op not in (0, 1, 2):
            raise RuntimeError(f"unsupported DAT operation: {op}")
        with self._data_lock:
            current = self._data_words.get(address, 0)
            result = value if op == 0 else current + value if op == 1 else current - value
            self._data_words[address] = max(-32768, min(32767, result))

    def _resolve_position(self, step: Mapping) -> dict:
        resolved = dict(step)
        point_name = str(step.get("point_name", ""))
        point = self.position_points.get(point_name) if point_name else None
        if point_name and point is None:
            raise RuntimeError(f"position point does not exist: {point_name}")
        if point:
            resolved.update({k: v for k, v in point.items() if k not in resolved})
            # Coordinates/speeds belong to the point library.  A step may only
            # override them explicitly for backwards-compatible recipes.
            resolved["coords"] = list(step.get("coords", point.get("coords", (0.0,) * 8)))
            resolved["speeds"] = list(step.get("speeds", point.get("speeds", (100,) * 8)))
        resolved["active_axes"] = list(
            step.get("active_axes", step.get("axes", resolved.get("active_axes", (True,) * 8)))
        )
        if self.position_transform is not None:
            resolved = dict(self.position_transform(resolved))
        return resolved

    def _parallel_sequence(self, name: str, depth: int) -> None:
        try:
            self._execute_sequence(name, depth)
        except Exception as exc:
            self._worker_error = exc
            self._stop.set()

    def _sleep(self, seconds: float) -> bool:
        remaining = max(0.0, float(seconds))
        previous = time.monotonic()
        while not self._stop.is_set():
            if not self._run_gate.is_set():
                self._wait_if_paused()
                previous = time.monotonic()
                continue
            if remaining <= 0:
                return True
            self._stop.wait(min(self.poll_interval, remaining))
            now = time.monotonic()
            remaining -= now - previous
            previous = now
        return False

    def _wait_if_paused(self) -> None:
        while not self._run_gate.wait(self.poll_interval):
            if self._stop.is_set():
                return

    def _emit(
        self,
        sequence: str = "",
        step_index: int = -1,
        step_type: str = "",
        message: str = "",
    ) -> None:
        if self.status_callback is None:
            return
        try:
            snapshot = getattr(self.backend, "snapshot", None)
            if snapshot is not None:
                inputs, outputs = snapshot()
            else:
                inputs = self.backend.read_inputs()
                outputs = self.backend.read_outputs()
        except Exception:
            inputs = outputs = 0
        self.status_callback(
            ExecutionStatus(self.state, sequence, step_index, step_type, message, inputs, outputs)
        )
