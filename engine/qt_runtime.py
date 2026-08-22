"""Qt bridge for the local DIO sequence executor."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .dio_backend import FastechI8O8Backend
from .step_executor import ExecutionStatus, ExecutorState, SequenceExecutor


class LocalDIORuntime(QObject):
    sig_connected = Signal(bool)
    sig_monitor_data = Signal(dict)
    sig_error = Signal(str)
    sig_executor_status = Signal(object)

    def __init__(self, sequences, host="192.168.0.5", parent=None):
        super().__init__(parent)
        self.sequences = sequences
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
            self.stop()
            return
        if not self.is_connected or self.executor is None:
            self.sig_error.emit("Ezi-IO is not connected")
            return
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
        if self.executor is not None:
            self.executor.pause()

    @Slot()
    def resume(self):
        if self.executor is not None:
            self.executor.resume()

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
        if not self.is_connected or self.backend is None:
            return
        try:
            self._emit_monitor(self.backend.read_inputs(), self.backend.read_outputs())
        except Exception as exc:
            self.last_error = str(exc)
            self.sig_error.emit(self.last_error)

    def _emit_monitor(self, inputs, outputs):
        self.sig_monitor_data.emit({
            "inputs": [int(inputs) & 0xFF],
            "outputs": [int(outputs) & 0xFF],
            "op_status": self.current_mode,
            "check_run_status": 1 if self.current_mode == 2 else 0,
            "current_step": self.current_step,
            "sub_seq_idx": 0,
            "local_sequence": self.current_sequence,
            "local_dio": True,
        })

    def close(self):
        self._poll.stop()
        if self.executor is not None:
            try:
                self.executor.close()
            except Exception as exc:
                print(f"[Local DIO] close safety reset failed: {exc}")
        self.executor = None
        self.backend = None
        self.is_connected = False
