#!/usr/bin/env python3
"""Read-only FASTECH Ezi-IO Ethernet DIO connection test."""

import argparse
import json

from drivers.fastech_ezi_io import EziIOClient, EziIOError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="Ezi-IO IPv4 address")
    parser.add_argument("--port", type=int, default=3001)
    parser.add_argument("--timeout", type=float, default=0.2)
    args = parser.parse_args()

    try:
        with EziIOClient(args.host, args.port, timeout=args.timeout) as client:
            info = client.get_slave_info().rstrip(b"\x00").decode("ascii", errors="replace")
            inputs = client.get_input()
            outputs = client.get_output()
    except EziIOError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps({
        "ok": True,
        "slave_info": info,
        "inputs": inputs.inputs,
        "input_latch": inputs.latch,
        "outputs": outputs.outputs,
        "trigger_running": outputs.trigger_running,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
