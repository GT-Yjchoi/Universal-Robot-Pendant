"""PLC backend public API.

The implementation remains available independently from the selected I/O backend.
Import PLCClient from this module in new application code.
"""

from utils.plc_client import PLCClient

__all__ = ["PLCClient"]
