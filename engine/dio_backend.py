"""Digital I/O backend abstractions and FASTECH implementation."""

from __future__ import annotations

from typing import Protocol

from drivers.fastech_ezi_io import EziIOClient


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

    def close(self) -> None:
        self.client.close()
