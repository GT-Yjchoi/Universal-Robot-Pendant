"""Digital I/O backend abstractions and FASTECH implementation."""

from __future__ import annotations

from typing import Protocol

from drivers.fastech_ezi_io import EziIOClient
from .control_backend import SignalGroup


class DigitalIOBackend(Protocol):
    input_count: int
    output_count: int

    def read_inputs(self) -> int: ...
    def read_outputs(self) -> int: ...
    def write_output(self, channel: int, enabled: bool) -> None: ...
    def all_outputs_off(self) -> None: ...
    def close(self) -> None: ...


class FastechI8O8Backend:
    input_count = 8
    output_count = 8

    def __init__(self, host: str, *, timeout: float = 0.1) -> None:
        self.client = EziIOClient(
            host,
            timeout=timeout,
            allow_writes=True,
            output_offset=8,
            output_count=8,
        )
        self.client.connect()
        try:
            self.client.get_slave_info()  # UDP connect alone does not prove reachability.
        except Exception:
            self.client.close()
            raise

    def read_inputs(self) -> int:
        return self.client.get_input().inputs & 0xFF

    def read_outputs(self) -> int:
        return self.client.logical_outputs()

    def write_output(self, channel: int, enabled: bool) -> None:
        self.client.set_channel(channel, enabled)

    def all_outputs_off(self) -> None:
        first_error = None
        try:
            self.client.run_trigger(stop_mask=0xFF << 8)
        except Exception as exc:
            first_error = exc
        try:
            self.client.set_output(reset_mask=0xFF << 8)
        except Exception:
            if first_error is not None:
                raise first_error
            raise

    def reset_outputs(self, indices) -> None:
        mask = sum(1 << int(index) for index in indices if 0 <= int(index) < 8)
        if mask:
            self.client.set_output(reset_mask=mask << 8)

    def close(self) -> None:
        self.client.close()

    def read_input(self, group: SignalGroup, index: int) -> bool:
        if group != SignalGroup.SYSTEM_IO:
            return False
        return bool(self.read_inputs() & (1 << index))

    def read_output(self, group: SignalGroup, index: int) -> bool:
        if group != SignalGroup.SYSTEM_IO:
            return False
        return bool(self.read_outputs() & (1 << index))

    def snapshot(self) -> tuple[int, int]:
        return self.read_inputs(), self.read_outputs()

    def move(self, step) -> None:
        raise RuntimeError("Ezi-IO backend does not support servo positioning")

    def stop_motion(self) -> None:
        pass
