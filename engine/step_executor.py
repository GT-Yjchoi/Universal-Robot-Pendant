"""Threaded, interruptible local sequence executor for digital I/O recipes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable, Mapping, Sequence

from .dio_backend import DigitalIOBackend


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
    SUPPORTED_TYPES = {"COMMENT", "OUT", "IN", "TMR", "JMP", "CALL", "END"}

    def __init__(
        self,
        backend: DigitalIOBackend,
        *,
        poll_interval: float = 0.005,
        status_callback: Callable[[ExecutionStatus], None] | None = None,
        safe_off_on_stop: bool = True,
    ) -> None:
        self.backend = backend
        self.poll_interval = max(0.001, float(poll_interval))
        self.status_callback = status_callback
        self.safe_off_on_stop = safe_off_on_stop
        self.state = ExecutorState.IDLE
        self.last_error = ""
        self._stop = threading.Event()
        self._run_gate = threading.Event()
        self._run_gate.set()
        self._thread: threading.Thread | None = None
        self._sequences: Mapping[str, Sequence[dict]] = {}

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, sequences: Mapping[str, Sequence[dict]], sequence: str = "Main") -> None:
        if self.is_running:
            raise RuntimeError("sequence executor is already running")
        if sequence not in sequences:
            raise KeyError(f"sequence not found: {sequence}")
        self._sequences = sequences
        self._stop.clear()
        self._run_gate.set()
        self.last_error = ""
        self.state = ExecutorState.RUNNING
        self._thread = threading.Thread(
            target=self._run, args=(sequence,), name="dio-step-executor", daemon=True
        )
        self._thread.start()

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
            self.backend.all_outputs_off()

    def close(self) -> None:
        try:
            self.stop(wait=True)
        finally:
            self.backend.close()

    def _run(self, sequence: str) -> None:
        try:
            self._execute_sequence(sequence, depth=0)
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
            elif step_type == "OUT":
                channel = self._channel(step)
                delay = float(step.get("delay_time", 0.0)) if step.get("delay_enable") else 0.0
                if delay > 0 and not self._sleep(delay):
                    return
                self.backend.write_output(channel, bool(step.get("on", True)))
                index += 1
            elif step_type == "IN":
                if not self._wait_input(step):
                    return
                index += 1
            elif step_type == "TMR":
                if not self._sleep(max(0.0, float(step.get("time", 0.0)))):
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
                self._execute_sequence(str(step.get("target_seq", "")), depth + 1)
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
        channel = self._channel(step)
        expected = bool(step.get("on", True))
        timeout = None
        if step.get("timeout_enabled"):
            timeout = max(0.0, float(step.get("timeout", step.get("timeout_sec", 0.0))))
        started = time.monotonic()
        while not self._stop.is_set():
            self._wait_if_paused()
            inputs = self.backend.read_inputs()
            if bool(inputs & (1 << channel)) == expected:
                return True
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError(f"IN{channel} wait timed out")
            self._stop.wait(self.poll_interval)
        return False

    def _jump_condition(self, step: Mapping) -> bool:
        if not step.get("condition", False):
            return True
        cond_type = str(step.get("cond_type", "INPUT")).upper()
        if cond_type != "INPUT":
            raise UnsupportedStepError(f"unsupported local JMP condition: {cond_type}")
        channel = int(step.get("cond_port", step.get("port", 0)))
        expected = bool(step.get("cond_on", step.get("on", True)))
        return bool(self.backend.read_inputs() & (1 << channel)) == expected

    def _sleep(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while not self._stop.is_set():
            self._wait_if_paused()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            self._stop.wait(min(self.poll_interval, remaining))
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
            inputs = self.backend.read_inputs()
            outputs = self.backend.read_outputs()
        except Exception:
            inputs = outputs = 0
        self.status_callback(
            ExecutionStatus(self.state, sequence, step_index, step_type, message, inputs, outputs)
        )
