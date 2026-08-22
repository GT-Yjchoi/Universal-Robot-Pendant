#!/usr/bin/env python3
"""Measure PLC DT word-read round-trip latency without changing PLC state."""

from __future__ import annotations

import argparse
import socket
import statistics
import struct
import time


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * ratio))
    return ordered[index]


def recv_frame(sock: socket.socket) -> bytes:
    header = bytearray()
    while len(header) < 12:
        chunk = sock.recv(12 - len(header))
        if not chunk:
            raise ConnectionError("PLC closed the TCP connection")
        header.extend(chunk)
    body_length = struct.unpack_from("<H", header, 2)[0]
    body = bytearray()
    while len(body) < body_length:
        chunk = sock.recv(body_length - len(body))
        if not chunk:
            raise ConnectionError("PLC closed the TCP connection mid-frame")
        body.extend(chunk)
    return bytes(body)


def read_dt(sock: socket.socket, address: int, count: int = 1) -> tuple[list[int], float]:
    body = struct.pack("<BBBHH", 0x80, 0x51, 0x09, address, count)
    packet = (
        b"\x10\x00"
        + struct.pack("<H", len(body))
        + b"\x02\x00\x02\x00\x00\x00"
        + bytes((0x01, 0x01))
        + body
    )
    started = time.perf_counter_ns()
    sock.sendall(packet)
    response = recv_frame(sock)
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    if len(response) < 3 + count * 2:
        raise ValueError(f"short PLC response: {response.hex(' ')}")
    values = list(struct.unpack_from(f"<{count}H", response, 3))
    return values, elapsed_ms


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=60001)
    parser.add_argument("--address", type=int, default=100)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--delay-ms", type=float, default=0.0)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    connect_started = time.perf_counter_ns()
    sock.connect((args.host, args.port))
    connect_ms = (time.perf_counter_ns() - connect_started) / 1_000_000
    try:
        first_value, _ = read_dt(sock, args.address, args.count)
        samples = []
        for _ in range(args.samples):
            if args.delay_ms:
                time.sleep(args.delay_ms / 1000)
            samples.append(read_dt(sock, args.address, args.count)[1])
    finally:
        sock.close()

    print(
        f"host={args.host}:{args.port} DT{args.address} "
        f"count={args.count} first={first_value[0]}"
    )
    print(f"connect={connect_ms:.3f} ms samples={len(samples)} delay={args.delay_ms:.3f}ms")
    print(
        "rtt_ms "
        f"min={min(samples):.3f} median={statistics.median(samples):.3f} "
        f"mean={statistics.fmean(samples):.3f} p95={percentile(samples, 0.95):.3f} "
        f"p99={percentile(samples, 0.99):.3f} max={max(samples):.3f}"
    )
    print(f"sequential_reads_per_sec={1000 / statistics.fmean(samples):.1f}")


if __name__ == "__main__":
    main()
