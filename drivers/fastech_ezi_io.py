"""FASTECH Ezi-IO Plus-E Ethernet DIO protocol driver.

Implements the manufacturer's UDP protocol directly, without the Windows-only DLL.
Output-changing commands are locked unless ``allow_writes=True`` is explicitly set.
"""

from __future__ import annotations

from dataclasses import dataclass
import socket
import struct
import threading


class EziIOError(RuntimeError):
    """Base Ezi-IO communication error."""


class EziIOTimeout(EziIOError):
    """The module did not reply before the configured timeout."""


class EziIOProtocolError(EziIOError):
    """A malformed or unsuccessful protocol response was received."""


class EziIOWriteLocked(EziIOError):
    """An output command was attempted while writes were locked."""


@dataclass(frozen=True)
class InputState:
    inputs: int
    latch: int


@dataclass(frozen=True)
class OutputState:
    outputs: int
    trigger_running: int


class EziIOClient:
    DEFAULT_PORT = 3001

    GET_SLAVE_INFO = 0x01
    GET_INPUT = 0xC0
    CLEAR_LATCH = 0xC1
    GET_OUTPUT = 0xC5
    SET_OUTPUT = 0xC6
    SET_TRIGGER = 0xC7
    SET_RUN_STOP = 0xC8

    _STATUS_TEXT = {
        0x80: "unknown frame type",
        0x81: "invalid data or ROM access",
        0x82: "invalid received frame",
        0xAA: "CRC error",
    }

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        timeout: float = 0.1,
        allow_writes: bool = False,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self.allow_writes = bool(allow_writes)
        self._socket: socket.socket | None = None
        self._sync = 0
        self._lock = threading.Lock()

    def connect(self) -> None:
        if self._socket is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        sock.connect((self.host, self.port))
        self._socket = sock

    def close(self) -> None:
        sock, self._socket = self._socket, None
        if sock is not None:
            sock.close()

    def __enter__(self) -> "EziIOClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _next_sync(self) -> int:
        self._sync = (self._sync + 1) & 0xFF
        return self._sync

    @staticmethod
    def _frame(sync: int, frame_type: int, data: bytes = b"") -> bytes:
        length = 3 + len(data)  # sync + reserved + frame type + data
        if length > 255:
            raise ValueError("Ezi-IO frame data is too large")
        return bytes((0xAA, length, sync, 0x00, frame_type)) + data

    def _request(self, frame_type: int, data: bytes = b"") -> bytes:
        with self._lock:
            if self._socket is None:
                self.connect()
            sync = self._next_sync()
            packet = self._frame(sync, frame_type, data)
            try:
                assert self._socket is not None
                self._socket.send(packet)
                response = self._socket.recv(512)
            except socket.timeout as exc:
                raise EziIOTimeout(f"no reply from {self.host}:{self.port}") from exc

        if len(response) < 6 or response[0] != 0xAA:
            raise EziIOProtocolError("invalid response header")
        expected_size = response[1] + 2
        if len(response) != expected_size:
            raise EziIOProtocolError(
                f"response length mismatch: expected {expected_size}, got {len(response)}"
            )
        if response[2] != sync or response[4] != frame_type:
            raise EziIOProtocolError("response sync or frame type mismatch")
        status = response[5]
        if status != 0:
            message = self._STATUS_TEXT.get(status, "unknown communication error")
            raise EziIOProtocolError(f"module error 0x{status:02X}: {message}")
        return response[6:]

    def _require_writes(self) -> None:
        if not self.allow_writes:
            raise EziIOWriteLocked("output writes are locked; set allow_writes=True explicitly")

    def get_slave_info(self) -> bytes:
        return self._request(self.GET_SLAVE_INFO)

    def get_input(self) -> InputState:
        data = self._request(self.GET_INPUT)
        if len(data) != 8:
            raise EziIOProtocolError(f"GET_INPUT returned {len(data)} data bytes")
        inputs, latch = struct.unpack(">II", data)
        return InputState(inputs=inputs, latch=latch)

    def clear_latch(self, mask: int) -> None:
        self._require_writes()
        self._request(self.CLEAR_LATCH, struct.pack(">I", mask & 0xFFFFFFFF))

    def get_output(self) -> OutputState:
        data = self._request(self.GET_OUTPUT)
        if len(data) != 8:
            raise EziIOProtocolError(f"GET_OUTPUT returned {len(data)} data bytes")
        outputs, running = struct.unpack(">II", data)
        return OutputState(outputs=outputs, trigger_running=running)

    def set_output(self, *, set_mask: int = 0, reset_mask: int = 0) -> None:
        self._require_writes()
        payload = struct.pack(">II", set_mask & 0xFFFFFFFF, reset_mask & 0xFFFFFFFF)
        self._request(self.SET_OUTPUT, payload)

    def set_channel(self, channel: int, enabled: bool) -> None:
        if not 0 <= channel <= 31:
            raise ValueError("channel must be in range 0..31")
        mask = 1 << channel
        self.set_output(set_mask=mask if enabled else 0, reset_mask=0 if enabled else mask)

    def configure_trigger(self, channel: int, *, period_ms: int, on_ms: int, count: int) -> None:
        self._require_writes()
        if not 0 <= channel <= 15:
            raise ValueError("trigger channel must be in range 0..15")
        if not 1 <= on_ms < period_ms <= 65535:
            raise ValueError("require 1 <= on_ms < period_ms <= 65535")
        if not 1 <= count <= 0xFFFFFFFF:
            raise ValueError("count must be in range 1..4294967295")
        payload = struct.pack(">BHHHHI", channel, period_ms, 0, on_ms, 0, count)
        self._request(self.SET_TRIGGER, payload)

    def run_trigger(self, *, run_mask: int = 0, stop_mask: int = 0) -> None:
        self._require_writes()
        payload = struct.pack(">II", run_mask & 0xFFFFFFFF, stop_mask & 0xFFFFFFFF)
        self._request(self.SET_RUN_STOP, payload)
