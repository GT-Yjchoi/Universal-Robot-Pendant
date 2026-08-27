"""Threaded, interruptible local sequence executor for digital I/O recipes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
import itertools
from typing import Callable, Mapping, Sequence

from .dio_backend import DigitalIOBackend
from .control_backend import SignalGroup
from utils.variable_store import VariableStore, MAX_BITS, MAX_DATA


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
    execution_id: int = 0


class SequenceExecutor:
    SUPPORTED_TYPES = {
        "COMMENT", "POS", "WPOS", "OUT", "IN", "TMR", "JMP", "CALL", "DAT", "END",
    }

    def __init__(
        self,
        backend: DigitalIOBackend,
        *,
        poll_interval: float = 0.005,
        status_callback: Callable[[ExecutionStatus], None] | None = None,
        position_points: Mapping[str, Mapping] | None = None,
        position_transform: Callable[[dict], Mapping] | None = None,
        position_provider: Callable[[], Sequence[float] | None] | None = None,
        mode_provider: Callable[[int], bool] | None = None,
        state_provider: Callable[[], int] | None = None,
        alarm_provider: Callable[[], bool] | None = None,
        event_callback: Callable[[str, Mapping], bool | None] | None = None,
        safe_off_on_stop: bool = True,
        output_stop_callback: Callable[[], None] | None = None,
        variable_store: VariableStore | None = None,
    ) -> None:
        self.backend = backend
        self.poll_interval = max(0.001, float(poll_interval))
        self.status_callback = status_callback
        self.position_points = position_points if position_points is not None else {}
        self.position_transform = position_transform
        self.position_provider = position_provider
        self.mode_provider = mode_provider
        self.state_provider = state_provider
        self.alarm_provider = alarm_provider
        self.event_callback = event_callback
        self.safe_off_on_stop = safe_off_on_stop
        self.output_stop_callback = output_stop_callback
        self.variable_store = variable_store or VariableStore()
        self.state = ExecutorState.IDLE
        self.last_error = ""
        self._stop = threading.Event()
        self._run_gate = threading.Event()
        self._run_gate.set()
        self._thread: threading.Thread | None = None
        self._sequences: Mapping[str, Sequence[dict]] = {}
        self._workers: list[threading.Thread] = []
        self._worker_error: Exception | None = None
        self._execution_ids = itertools.count(1)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, sequences: Mapping[str, Sequence[dict]], sequence: str = "Main") -> None:
        if self.is_running:
            raise RuntimeError("sequence executor is already running")
        if sequence not in sequences:
            raise KeyError(f"sequence not found: {sequence}")
        self.variable_store.ensure_legacy_references(sequences)
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
                    if step.get("condition", False) and str(
                            step.get("cond_type", "INPUT")
                    ).upper() in (
                            "POSITION", "POINT", "AXISPOS"):
                        point_name = str(step.get("cond_point_name", ""))
                        if not point_name or point_name not in self.position_points:
                            errors.append(f"{prefix}: missing JMP position point {point_name}")
                        axes = step.get("cond_position_axes", (True,) * 8)
                        if not isinstance(axes, Sequence) or len(axes) < 8:
                            errors.append(f"{prefix}: JMP position condition requires 8 axis flags")
                        elif not any(bool(axis) for axis in axes[:8]):
                            errors.append(f"{prefix}: JMP position condition requires an active axis")
                        if float(step.get("cond_position_tolerance", 0.1)) < 0:
                            errors.append(f"{prefix}: JMP position tolerance cannot be negative")
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
                elif kind == "WPOS":
                    point_name = str(step.get("point_name", ""))
                    if not point_name or point_name not in self.position_points:
                        errors.append(f"{prefix}: missing WPOS position point {point_name}")
                    axes = step.get("active_axes", (True,) * 8)
                    if not isinstance(axes, Sequence) or len(axes) < 8:
                        errors.append(f"{prefix}: WPOS requires 8 axis flags")
                    elif not any(bool(axis) for axis in axes[:8]):
                        errors.append(f"{prefix}: WPOS requires an active axis")
                    if float(step.get("position_tolerance", 0.1)) < 0:
                        errors.append(f"{prefix}: WPOS tolerance cannot be negative")
                    if float(step.get("timeout", 5.0)) <= 0:
                        errors.append(f"{prefix}: WPOS timeout must be greater than zero")
                elif kind in ("OUT", "IN") and "dio_channel" not in step:
                    group = int(step.get("out_type" if kind == "OUT" else "in_type", 0))
                    port = int(step.get("port", 0))
                    if group not in (0, 1, 2, 4, 5):
                        errors.append(f"{prefix}: I/O group {group} is invalid")
                    offset = (32 if kind == "IN" and group == 1 and port >= 32 else
                              100 if kind == "IN" and group == 2 and port >= 100 else 0)
                    logical = port - offset
                    limit = MAX_BITS - 1 if group == 2 else 15
                    if not 0 <= logical <= limit:
                        errors.append(f"{prefix}: I/O port {port} is out of range")
                elif kind == "DAT":
                    address = int(step.get("dat_dt_addr", step.get("dt_addr", 60000)))
                    data_id = int(step.get("data_id", address - 60000))
                    if not 0 <= data_id < MAX_DATA:
                        errors.append(f"{prefix}: data variable {data_id} is out of range")
                    if str(step.get("dat_mode", "constant")) == "data":
                        left_id = int(step.get("dat_left_data_id", -1))
                        right_id = int(step.get("dat_right_data_id", -1))
                        if not 0 <= left_id < MAX_DATA:
                            errors.append(f"{prefix}: left data variable {left_id} is out of range")
                        if not 0 <= right_id < MAX_DATA:
                            errors.append(f"{prefix}: right data variable {right_id} is out of range")
                        math_op = int(step.get("dat_math_op", 0))
                        if math_op not in (0, 1, 2, 3):
                            errors.append(f"{prefix}: data math operation {math_op} is invalid")
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
                self._apply_output_stop()
            else:
                threading.Thread(
                    target=self._apply_output_stop,
                    name="safe-output-off", daemon=True,
                ).start()

    def _apply_output_stop(self) -> None:
        if self.output_stop_callback is not None:
            self.output_stop_callback()
        else:
            self.backend.all_outputs_off()

    def close(self) -> None:
        try:
            self.stop(wait=True)
        finally:
            self.backend.close()

    def _run(self, sequence: str) -> None:
        try:
            self._execute_sequence(sequence, depth=0,
                                   execution_id=next(self._execution_ids))
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
                    self._apply_output_stop()
                except Exception as exc:
                    if not self.last_error:
                        self.last_error = f"safe output reset failed: {exc}"
                        self.state = ExecutorState.ERROR
            if self.state == ExecutorState.STOPPING:
                self.state = ExecutorState.IDLE
                self._emit(message="stopped")

    def _execute_sequence(self, name: str, depth: int,
                          execution_id: int) -> None:
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
            self._emit(name, monitor_index, step_type,
                       execution_id=execution_id)

            if step_type == "COMMENT":
                index += 1
            elif step_type == "POS":
                move = getattr(self.backend, "move", None)
                if move is None:
                    raise UnsupportedStepError("backend does not support POS")
                move(self._resolve_position(step))
                index += 1
            elif step_type == "WPOS":
                if not self._wait_position(step):
                    return
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
                    child_execution_id = next(self._execution_ids)
                    worker = threading.Thread(
                        target=self._parallel_sequence,
                        args=(target, depth + 1, child_execution_id),
                        name=f"pendant-call-{target}", daemon=True,
                    )
                    self._workers.append(worker)
                    worker.start()
                else:
                    child_execution_id = next(self._execution_ids)
                    self._execute_sequence(target, depth + 1,
                                           child_execution_id)
                    self._emit(target, -1, "", message="sequence_completed",
                               execution_id=child_execution_id)
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
        timeup_enabled = bool(step.get("timeup_enabled", False))
        timeup_seconds = max(
            0.0, float(step.get("timeup_time", step.get("hold_time", 0.0)))
        )
        timeout = None
        if step.get("timeout_enabled"):
            timeout = max(0.0, float(step.get("timeout", step.get("timeout_sec", 5.0))))
        started = time.monotonic()
        matched_since: float | None = None
        while not self._stop.is_set():
            if not self._run_gate.is_set():
                paused_at = time.monotonic()
                self._wait_if_paused()
                paused_for = time.monotonic() - paused_at
                started += paused_for
                if matched_since is not None:
                    matched_since += paused_for
            now = time.monotonic()
            if self._read_step_input(step) == expected:
                if not timeup_enabled:
                    return True
                matched_since = now if matched_since is None else matched_since
                if now - matched_since >= timeup_seconds:
                    return True
            else:
                # The time-up condition is continuous: any mismatch restarts it.
                matched_since = None
            if timeout is not None and now - started >= timeout:
                action = str(step.get("timeout_action", "continue"))
                if self.event_callback is not None:
                    decision = self.event_callback(f"input_timeout:{action}", step)
                    if decision is True or decision == "proceed":
                        return True
                    if decision is False or decision == "stop":
                        self.stop(wait=False)
                        return False
                    if decision in ("reset", "retry"):
                        started = time.monotonic()
                        matched_since = None
                        continue
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

    def _position_matches(self, point_name, axes, tolerance):
        if self.position_provider is None:
            raise UnsupportedStepError(
                "position condition requires actual axis position provider"
            )
        point = self.position_points.get(str(point_name))
        if point is None:
            raise RuntimeError(f"position point not found: {point_name}")
        actual = self.position_provider()
        if actual is None or len(actual) < 8:
            raise RuntimeError("actual axis position is unavailable")
        target = list(point.get("coords", ()))
        if len(target) < 8:
            raise RuntimeError(f"position point requires 8 coordinates: {point_name}")
        axes = list(axes)
        if len(axes) < 8 or not any(bool(axis) for axis in axes[:8]):
            raise RuntimeError("position comparison requires at least one active axis")
        tolerance = max(0.0, float(tolerance))
        return all(
            abs(float(actual[index]) - float(target[index])) <= tolerance
            for index in range(8) if bool(axes[index])
        )

    def _wait_position(self, step: Mapping) -> bool:
        point_name = str(step.get("point_name", ""))
        axes = step.get("active_axes", (True,) * 8)
        tolerance = max(0.0, float(step.get("position_tolerance", 0.1)))
        timeout = max(0.001, float(step.get("timeout", 5.0)))
        started = time.monotonic()
        while not self._stop.is_set():
            if not self._run_gate.is_set():
                paused_at = time.monotonic()
                self._wait_if_paused()
                started += time.monotonic() - paused_at
            if self._position_matches(point_name, axes, tolerance):
                return True
            if time.monotonic() - started >= timeout:
                raise TimeoutError(
                    f"WPOS 위치 도달 타임아웃: {point_name} "
                    f"(허용오차 ±{tolerance:.3f}, 제한 {timeout:.3f}초)"
                )
            self._stop.wait(self.poll_interval)
        return False

    def _jump_condition(self, step: Mapping) -> bool:
        if not step.get("condition", False):
            return True
        cond_type = str(step.get("cond_type", "INPUT")).upper()
        expected = bool(step.get("cond_on", step.get("on", True)))
        value = int(step.get("cond_value", step.get("cond_port", step.get("port", 0))))
        if cond_type in ("INPUT", "PORT"):
            probe = {"port": value, "in_type": int(step.get("cond_io_type", 0))}
            return self._read_step_input(probe) == expected
        if cond_type == "VALVE":
            probe = {"port": value, "in_type": 1}
            return self._read_step_input(probe) == expected
        if cond_type in ("BIT", "INTERNAL"):
            bit_id = int(step.get("cond_bit_id", value - 100 if value >= 100 else value))
            probe = {"port": bit_id, "bit_id": bit_id, "in_type": 2}
            return self._read_step_input(probe) == expected
        if cond_type == "MODE":
            if self.mode_provider is None:
                raise UnsupportedStepError("mode condition requires runtime mode provider")
            return bool(self.mode_provider(value)) == expected
        if cond_type == "STATE":
            if value == 3:
                if self.alarm_provider is None:
                    raise UnsupportedStepError("alarm condition requires alarm provider")
                return bool(self.alarm_provider()) == expected
            if self.state_provider is None:
                raise UnsupportedStepError("state condition requires runtime state provider")
            return (int(self.state_provider()) == value) == expected
        if cond_type in ("DTCMP", "DT", "DATA"):
            address = int(step.get("cmp_dt_addr", step.get("dt_addr", step.get("cond_addr", 60000))))
            data_id = int(step.get("cmp_data_id", address - 60000))
            left = self.variable_store.get_data(data_id)
            right = int(step.get("cmp_const", step.get("dt_const", step.get("cond_value", 0))))
            op = int(step.get("cmp_op", step.get("dt_op", step.get("cond_op", 0))))
            return ((left == right), (left != right), (left > right), (left >= right),
                    (left < right), (left <= right))[max(0, min(5, op))]
        if cond_type in ("POSITION", "POINT", "AXISPOS"):
            point_name = str(step.get("cond_point_name", ""))
            axes = list(step.get("cond_position_axes", (True,) * 8))
            tolerance = max(0.0, float(step.get("cond_position_tolerance", 0.1)))
            matched = self._position_matches(point_name, axes, tolerance)
            return matched == expected
        raise UnsupportedStepError(f"unsupported local JMP condition: {cond_type}")

    def _write_step_output(self, step: Mapping) -> None:
        if "dio_channel" in step:
            self.backend.write_output(self._channel(step), bool(step.get("on", True)))
            return
        kind = int(step.get("out_type", 0))
        index = int(step.get("bit_id", step.get("port", 0))) if kind == 2 \
            else int(step.get("port", 0))
        enabled = bool(step.get("on", True))
        if kind == 2:
            if not 0 <= index < MAX_BITS:
                raise RuntimeError(f"internal output bit out of range: {index}")
            self.variable_store.set_bit(index, enabled)
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
            index = int(step.get("bit_id", port - 100 if port >= 100 else port))
            if not 0 <= index < MAX_BITS:
                raise RuntimeError(f"internal input bit out of range: {index}")
            return self.variable_store.get_bit(index)
        if kind == 3:
            raise UnsupportedStepError("mode input requires runtime mode provider")
        # Old group-2 recipes stored X20 as port 32..47.  New configurable
        # groups store a local bit index 0..15 for every physical group.
        index = port - 32 if kind == 1 and port >= 32 else port
        reader = getattr(self.backend, "read_input", None)
        if reader is None:
            raise UnsupportedStepError("backend does not support typed inputs")
        return bool(reader(SignalGroup(kind), index))

    def _execute_dat(self, step: Mapping) -> None:
        address = int(step.get("dat_dt_addr", step.get("dt_addr", step.get("address", 60000))))
        data_id = int(step.get("data_id", address - 60000))
        if not 0 <= data_id < MAX_DATA:
            raise RuntimeError(f"data variable out of range: {data_id}")
        if str(step.get("dat_mode", "constant")) == "data":
            left_id = int(step.get("dat_left_data_id", -1))
            right_id = int(step.get("dat_right_data_id", -1))
            if not 0 <= left_id < MAX_DATA:
                raise RuntimeError(f"left data variable out of range: {left_id}")
            if not 0 <= right_id < MAX_DATA:
                raise RuntimeError(f"right data variable out of range: {right_id}")
            math_op = int(step.get("dat_math_op", 0))
            try:
                self.variable_store.calculate_data(
                    data_id, left_id, math_op, right_id,
                )
            except ZeroDivisionError as exc:
                raise RuntimeError(str(exc)) from exc
            return
        value = int(step.get("dat_const", step.get("value", step.get("constant", step.get("operand", 0)))))
        op = int(step.get("dat_op", step.get("op", step.get("operation", 0))))
        if op not in (0, 1, 2):
            raise RuntimeError(f"unsupported DAT operation: {op}")
        self.variable_store.operate_data(data_id, op, value)

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

    def _parallel_sequence(self, name: str, depth: int,
                           execution_id: int) -> None:
        try:
            self._execute_sequence(name, depth, execution_id)
        except Exception as exc:
            self._worker_error = exc
            self._stop.set()
        finally:
            self._emit(name, -1, "", message="sequence_completed",
                       execution_id=execution_id)

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
        execution_id: int = 0,
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
            ExecutionStatus(self.state, sequence, step_index, step_type,
                            message, inputs, outputs, execution_id)
        )
