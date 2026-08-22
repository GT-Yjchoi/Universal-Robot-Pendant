#!/usr/bin/env python3
"""Diagnose whether PLC latency is per request, TCP connection, or controller-wide."""

from __future__ import annotations

import argparse
import socket
import statistics
import struct
import threading
import time


def packet(address: int = 100) -> bytes:
    body = struct.pack("<BBBHH", 0x80, 0x51, 0x09, address, 1)
    return (
        b"\x10\x00" + struct.pack("<H", len(body))
        + b"\x02\x00\x02\x00\x00\x00\x01\x01" + body
    )


def connect(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.connect((host, port))
    return sock


def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("PLC closed connection")
        data.extend(chunk)
    return bytes(data)


def recv_frame(sock: socket.socket) -> bytes:
    header = recv_exact(sock, 12)
    return recv_exact(sock, struct.unpack_from("<H", header, 2)[0])


def pipeline(host: str, port: int, count: int) -> None:
    sock = connect(host, port)
    request = packet()
    started = time.perf_counter_ns()
    sock.sendall(request * count)
    arrivals = []
    for _ in range(count):
        recv_frame(sock)
        arrivals.append((time.perf_counter_ns() - started) / 1_000_000)
    sock.close()
    gaps = [b - a for a, b in zip(arrivals, arrivals[1:])]
    print(
        f"pipeline count={count} total={arrivals[-1]:.3f}ms "
        f"rate={count * 1000 / arrivals[-1]:.1f}/s "
        f"arrival_gap_median={statistics.median(gaps):.3f}ms"
    )


def worker(host: str, port: int, count: int, barrier: threading.Barrier,
           results: list[float | str], index: int) -> None:
    try:
        sock = connect(host, port)
        request = packet()
        barrier.wait(timeout=3.0)
        started = time.perf_counter_ns()
        for _ in range(count):
            sock.sendall(request)
            recv_frame(sock)
        results[index] = (time.perf_counter_ns() - started) / 1_000_000
        sock.close()
    except Exception as exc:
        results[index] = f"{type(exc).__name__}: {exc}"
        try:
            barrier.abort()
        except Exception:
            pass


def parallel(host: str, port: int, connections: int, count: int) -> None:
    barrier = threading.Barrier(connections)
    results: list[float | str] = ["not started"] * connections
    threads = [
        threading.Thread(
            target=worker,
            args=(host, port, count, barrier, results, index),
        )
        for index in range(connections)
    ]
    wall_started = time.perf_counter_ns()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall_ms = (time.perf_counter_ns() - wall_started) / 1_000_000
    valid = [value for value in results if isinstance(value, float)]
    rate = connections * count * 1000 / wall_ms if len(valid) == connections else 0.0
    print(f"parallel connections={connections} wall={wall_ms:.3f}ms rate={rate:.1f}/s results={results}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=60001)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--skip-pipeline", action="store_true")
    args = parser.parse_args()
    if not args.skip_pipeline:
        try:
            pipeline(args.host, args.port, args.count)
        except (OSError, ConnectionError) as exc:
            print(f"pipeline unsupported_or_failed: {type(exc).__name__}: {exc}")
    parallel(args.host, args.port, 2, args.count)


if __name__ == "__main__":
    main()
