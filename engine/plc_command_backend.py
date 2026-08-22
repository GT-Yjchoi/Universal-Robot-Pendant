"""FP0H command-mailbox backend for pendant-side recipe execution.

The request sequence at DT342 is the commit word.  PLC code must copy it to
DT350 only after finishing or rejecting the command.  This makes retries and
late TCP responses idempotent.
"""

from __future__ import annotations

from enum import IntEnum
import threading
import time
from typing import Mapping

from .control_backend import SignalGroup


class PlcCommand(IntEnum):
    OUTPUT_SET = 1
    OUTPUT_PULSE = 2
    OUTPUTS_OFF = 3
    MOVE_ABSOLUTE = 10
    HOME = 11
    STOP = 12
    RESET = 13


class PlcCommandError(RuntimeError):
    pass


class FP0HCommandBackend:
    REQUEST_ADDR = 300
    REQUEST_WORDS = 43       # DT300..DT342; DT342 is commit sequence
    REQUEST_SEQ_OFFSET = 42
    STATUS_ADDR = 350        # ack_seq, state, error, command, detail
    STATUS_WORDS = 5
    STATUS_BUSY = 1
    STATUS_DONE = 2
    STATUS_ERROR = 3

    def __init__(self, plc_client, *, timeout: float = 30.0, poll_interval: float = 0.005):
        self.plc = plc_client
        self.timeout = float(timeout)
        self.poll_interval = max(0.001, float(poll_interval))
        self._sequence = 0
        self._command_lock = threading.Lock()

    @staticmethod
    def _word(value: int) -> int:
        return int(value) & 0xFFFF

    @staticmethod
    def _put_dint(words: list[int], offset: int, value: int) -> None:
        value = int(value) & 0xFFFFFFFF
        words[offset] = value & 0xFFFF
        words[offset + 1] = value >> 16

    def _connected(self) -> None:
        if not self.plc or not self.plc.is_connected:
            raise ConnectionError("PLC is not connected")

    def _execute(self, command: PlcCommand, *, group=0, index=0, value=0,
                 duration_ms=0, axis_mask=0, flags=0, positions=None,
                 speeds=None, acceleration=0, deceleration=0) -> None:
        self._connected()
        with self._command_lock:
            self._sequence = (self._sequence % 65535) + 1
            sequence = self._sequence
            words = [0] * self.REQUEST_WORDS
            words[0] = int(command)
            words[1] = self._word(group)
            words[2] = self._word(index)
            words[3] = self._word(value)
            self._put_dint(words, 4, duration_ms)
            words[6] = self._word(axis_mask)
            words[7] = self._word(flags)
            for axis, position in enumerate(list(positions or ())[:8]):
                self._put_dint(words, 8 + axis * 2, round(float(position) * 1000))
            for axis, speed in enumerate(list(speeds or ())[:8]):
                words[24 + axis] = self._word(round(float(speed)))
            words[32] = self._word(acceleration)
            words[33] = self._word(deceleration)
            words[self.REQUEST_SEQ_OFFSET] = sequence
            if not self.plc.write_words(0x09, self.REQUEST_ADDR, words):
                raise ConnectionError("PLC command mailbox write failed")

            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                status = self.plc.read_words(0x09, self.STATUS_ADDR, self.STATUS_WORDS)
                if status and status[0] == sequence:
                    if status[1] == self.STATUS_DONE:
                        return
                    if status[1] == self.STATUS_ERROR:
                        raise PlcCommandError(
                            f"PLC command {int(command)} failed: error={status[2]} detail={status[4]}"
                        )
                time.sleep(self.poll_interval)
            raise TimeoutError(f"PLC command {int(command)} timed out (sequence={sequence})")

    def _monitor_words(self, key: str) -> list[int]:
        values = self.plc._last_monitor_data.get(key, [])
        return list(values) if isinstance(values, (list, tuple)) else []

    @staticmethod
    def _bit(words: list[int], absolute_index: int) -> bool:
        word, bit = divmod(absolute_index, 16)
        return word < len(words) and bool(int(words[word]) & (1 << bit))

    def read_input(self, group: SignalGroup, index: int) -> bool:
        absolute = int(index) + (32 if group == SignalGroup.VALVE_IO else 0)
        return self._bit(self._monitor_words("inputs"), absolute)

    def read_output(self, group: SignalGroup, index: int) -> bool:
        absolute = int(index) + (32 if group == SignalGroup.VALVE_IO else 0)
        return self._bit(self._monitor_words("outputs"), absolute)

    def write_output(self, group: SignalGroup, index: int, enabled: bool,
                     pulse_ms: int = 0) -> None:
        command = PlcCommand.OUTPUT_PULSE if pulse_ms > 0 else PlcCommand.OUTPUT_SET
        self._execute(command, group=int(group), index=index, value=int(enabled),
                      duration_ms=pulse_ms)

    def move(self, step: Mapping) -> None:
        coords = list(step.get("coords", (0.0,) * 8))
        speeds = list(step.get("speeds", (100,) * 8))
        axes = list(step.get("active_axes", step.get("axes", (True,) * 8)))
        axis_mask = sum((1 << index) for index, enabled in enumerate(axes[:8]) if enabled)
        flags = int(step.get("exec_mode", 0))
        if not bool(step.get("wait_completion", True)):
            flags |= 0x0001
        self._execute(PlcCommand.MOVE_ABSOLUTE, axis_mask=axis_mask, flags=flags,
                      positions=coords, speeds=speeds,
                      acceleration=step.get("acceleration", 0),
                      deceleration=step.get("deceleration", 0))

    def stop_motion(self) -> None:
        self._execute(PlcCommand.STOP)

    def home(self) -> None:
        self._execute(PlcCommand.HOME)

    def all_outputs_off(self) -> None:
        if not self.plc or not self.plc.is_connected:
            return
        self._execute(PlcCommand.OUTPUTS_OFF)

    def snapshot(self) -> tuple[int, int]:
        ins = self._monitor_words("inputs")
        outs = self._monitor_words("outputs")
        return (
            sum((int(word) & 0xFFFF) << (16 * i) for i, word in enumerate(ins)),
            sum((int(word) & 0xFFFF) << (16 * i) for i, word in enumerate(outs)),
        )

    def close(self) -> None:
        pass
