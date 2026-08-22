#!/usr/bin/env python3
"""Destructive output test for an unconnected Ezi-IO I8O8 module."""

import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drivers.fastech_ezi_io import EziIOClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    args = parser.parse_args()

    mask = 0xFF
    with EziIOClient(args.host, timeout=0.5, allow_writes=True) as client:
        try:
            client.set_output(reset_mask=mask)
            for channel in range(8):
                bit = 1 << channel
                client.set_channel(channel, True)
                state_on = client.get_output().outputs & mask
                print(f"OUT{channel}: ON  readback=0x{state_on:02X}")
                if state_on != bit:
                    raise RuntimeError(f"OUT{channel} ON readback mismatch")
                time.sleep(0.1)
                client.set_channel(channel, False)
                state_off = client.get_output().outputs & mask
                print(f"OUT{channel}: OFF readback=0x{state_off:02X}")
                if state_off != 0:
                    raise RuntimeError(f"OUT{channel} OFF readback mismatch")

            client.set_output(set_mask=mask)
            all_on = client.get_output().outputs & mask
            print(f"ALL: ON  readback=0x{all_on:02X}")
            client.set_output(reset_mask=mask)
            all_off = client.get_output().outputs & mask
            print(f"ALL: OFF readback=0x{all_off:02X}")
            if all_on != mask or all_off != 0:
                raise RuntimeError("all-output readback mismatch")

            client.configure_trigger(0, period_ms=20, on_ms=10, count=3)
            client.run_trigger(run_mask=1)
            time.sleep(0.1)
            trigger_state = client.get_output()
            print(
                "TRIGGER0: 10ms ON / 20ms period / 3 count, "
                f"output=0x{trigger_state.outputs & mask:02X}, "
                f"running=0x{trigger_state.trigger_running & mask:02X}"
            )
        finally:
            client.run_trigger(stop_mask=mask)
            client.set_output(reset_mask=mask)
            final = client.get_output()
            print(f"SAFE OFF: output=0x{final.outputs & mask:02X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
