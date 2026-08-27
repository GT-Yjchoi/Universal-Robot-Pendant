"""Machine-control backend contract used by the pendant-side step executor."""

from __future__ import annotations

from enum import IntEnum
from typing import Mapping, Protocol


class SignalGroup(IntEnum):
    IO_GROUP_1 = 0
    IO_GROUP_2 = 1
    IO_GROUP_3 = 4
    IO_GROUP_4 = 5

    # Backward-compatible names used by older recipes/tests.
    SYSTEM_IO = IO_GROUP_1
    VALVE_IO = IO_GROUP_2


class ControlBackend(Protocol):
    def read_input(self, group: SignalGroup, index: int) -> bool: ...
    def read_output(self, group: SignalGroup, index: int) -> bool: ...
    def write_output(self, group: SignalGroup, index: int, enabled: bool,
                     pulse_ms: int = 0) -> None: ...
    def move(self, step: Mapping) -> None: ...
    def stop_motion(self) -> None: ...
    def all_outputs_off(self) -> None: ...
    def snapshot(self) -> tuple[int, int]: ...
    def close(self) -> None: ...
