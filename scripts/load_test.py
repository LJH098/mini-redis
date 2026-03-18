#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
import socket
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional


class BenchmarkError(RuntimeError):
    pass


@dataclass
class BenchmarkConfig:
    host: str
    port: int
    mode: str
    workers: int
    requests: int
    warmup_requests: int
    key_prefix: str
    keyspace: int
    payload_size: int
    timeout_seconds: float
    seed: int


@dataclass
class WorkerResult:
    latencies_ms: list[float]
    errors: int = 0


class RespConnection:
    def __init__(self, host: str, port: int, timeout_seconds: float) -> None:
        self._sock = socket.create_connection((host, port), timeout=timeout_seconds)
        self._sock.settimeout(timeout_seconds)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass

    def execute(self, parts: list[str]):
        self._sock.sendall(self._encode(parts))
        return self._read_response()

    @staticmethod
    def _encode(parts: list[str]) -> bytes:
        chunks = [f"*{len(parts)}\r\n".encode("ascii")]
        for part in parts:
            encoded = part.encode("utf-8")
            chunks.append(f"${len(encoded)}\r\n".encode("ascii"))
            chunks.append(encoded)
            chunks.append(b"\r\n")
        return b"".join(chunks)

    def _read_response(self):
        prefix = self._read_exact(1)
        if prefix == b"+":
            return self._read_line().decode("utf-8")
        if prefix == b":":
            return int(self._read_line().decode("ascii"))
        if prefix == b"$":
            size = int(self._read_line().decode("ascii"))
            if size == -1:
                return None
            payload = self._read_exact(size)
            self._read_exact(2)
            return payload.decode("utf-8")
        if prefix == b"-":
            message = self._read_line().decode("utf-8")
            raise BenchmarkError(message)
        raise BenchmarkError("unsupported RESP response")

    def _read_line(self) -> bytes:
        chunks = bytearray()
        while True:
            chunks.extend(self._read_exact(1))
            if chunks.endswith(b"\r\n"):
                return bytes(chunks[:-2])

    def _read_exact(self, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            payload = self._sock.recv(size - len(chunks))
            if not payload:
                raise BenchmarkError("connection closed unexpectedly")
            chunks.extend(payload)
        return bytes(chunks)


def parse_args() -> BenchmarkConfig:
    parser = argparse.ArgumentParser(description="Load test mini redis over RESP/TCP.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument(
        "--mode",
        choices=["ping", "get", "set", "incr", "mixed"],
        default="ping",
        help="Command mix to benchmark.",
    )
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--requests", type=int, default=5000, help="Total measured requests.")
    parser.add_argument("--warmup-requests", type=int, default=200)
    parser.add_argument("--key-prefix", default="bench:key")
    parser.add_argument("--keyspace", type=int, default=100)
    parser.add_argument("--payload-size", type=int, default=32)
    parser.add_argument("--timeout-seconds", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    return BenchmarkConfig(
        host=args.host,
        port=args.port,
        mode=args.mode,
        workers=max(1, args.workers),
        requests=max(1, args.requests),
        warmup_requests=max(0, args.warmup_requests),
        key_prefix=args.key_prefix,
        keyspace=max(1, args.keyspace),
        payload_size=max(1, args.payload_size),
        timeout_seconds=max(0.1, args.timeout_seconds),
        seed=args.seed,
    )


def prepare_dataset(config: BenchmarkConfig) -> None:
    connection = RespConnection(config.host, config.port, config.timeout_seconds)
    payload = "x" * config.payload_size
    try:
        if config.mode in {"get", "mixed"}:
            for worker_id in range(config.workers):
                for index in range(config.keyspace):
                    connection.execute(["SET", _key_for(config, worker_id, index, family="str"), payload])
        if config.mode in {"incr", "mixed"}:
            for worker_id in range(config.workers):
                for index in range(config.keyspace):
                    connection.execute(["SET", _key_for(config, worker_id, index, family="incr"), "0"])
    finally:
        connection.close()


def warmup(config: BenchmarkConfig) -> None:
    if config.warmup_requests == 0:
        return
    connection = RespConnection(config.host, config.port, config.timeout_seconds)
    rng = random.Random(config.seed)
    try:
        for index in range(config.warmup_requests):
            command = build_command(config, worker_id=0, operation_index=index, rng=rng)
            connection.execute(command)
    finally:
        connection.close()


def build_command(
    config: BenchmarkConfig,
    *,
    worker_id: int,
    operation_index: int,
    rng: random.Random,
) -> list[str]:
    mode = config.mode
    if mode == "mixed":
        mode = rng.choice(["ping", "get", "set", "incr"])

    if mode == "ping":
        return ["PING"]
    if mode == "get":
        key = _key_for(config, worker_id, operation_index, family="str")
        return ["GET", key]
    if mode == "set":
        key = _key_for(config, worker_id, operation_index, family="str")
        value = f"{worker_id}:{operation_index}:" + ("x" * config.payload_size)
        return ["SET", key, value]
    if mode == "incr":
        key = _key_for(config, worker_id, operation_index, family="incr")
        return ["INCR", key]
    raise ValueError(f"Unsupported mode: {mode}")


def run_benchmark(config: BenchmarkConfig) -> WorkerResult:
    requests_by_worker = split_requests(config.requests, config.workers)
    start_barrier = threading.Barrier(config.workers)

    with ThreadPoolExecutor(max_workers=config.workers) as executor:
        futures = [
            executor.submit(run_worker, config, worker_id, request_count, start_barrier)
            for worker_id, request_count in enumerate(requests_by_worker)
        ]

    combined = WorkerResult(latencies_ms=[], errors=0)
    for future in futures:
        result = future.result()
        combined.latencies_ms.extend(result.latencies_ms)
        combined.errors += result.errors
    return combined


def run_worker(
    config: BenchmarkConfig,
    worker_id: int,
    request_count: int,
    start_barrier: threading.Barrier,
) -> WorkerResult:
    connection = RespConnection(config.host, config.port, config.timeout_seconds)
    rng = random.Random(config.seed + worker_id)
    result = WorkerResult(latencies_ms=[])
    try:
        start_barrier.wait()
        for operation_index in range(request_count):
            command = build_command(
                config,
                worker_id=worker_id,
                operation_index=operation_index,
                rng=rng,
            )
            started = time.perf_counter()
            try:
                connection.execute(command)
            except Exception:
                result.errors += 1
            else:
                result.latencies_ms.append((time.perf_counter() - started) * 1000)
    finally:
        connection.close()
    return result


def split_requests(total_requests: int, workers: int) -> list[int]:
    base = total_requests // workers
    remainder = total_requests % workers
    return [base + (1 if index < remainder else 0) for index in range(workers)]


def _key_for(
    config: BenchmarkConfig,
    worker_id: int,
    operation_index: int,
    *,
    family: str,
) -> str:
    slot = operation_index % config.keyspace
    return f"{config.key_prefix}:{family}:{worker_id}:{slot}"


def percentile(samples: list[float], ratio: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def main() -> None:
    config = parse_args()
    prepare_dataset(config)
    warmup(config)

    started = time.perf_counter()
    result = run_benchmark(config)
    duration_seconds = time.perf_counter() - started

    successful_requests = len(result.latencies_ms)
    throughput = successful_requests / duration_seconds if duration_seconds > 0 else 0.0

    print("Mini Redis Load Test")
    print(f"target         : {config.host}:{config.port}")
    print(f"mode           : {config.mode}")
    print(f"workers        : {config.workers}")
    print(f"requests       : {config.requests}")
    print(f"warmup         : {config.warmup_requests}")
    print(f"duration       : {duration_seconds:.3f}s")
    print(f"success        : {successful_requests}")
    print(f"errors         : {result.errors}")
    print(f"throughput     : {throughput:.2f} req/s")

    if result.latencies_ms:
        print(f"latency avg    : {statistics.mean(result.latencies_ms):.3f} ms")
        print(f"latency median : {statistics.median(result.latencies_ms):.3f} ms")
        print(f"latency p95    : {percentile(result.latencies_ms, 0.95):.3f} ms")
        print(f"latency p99    : {percentile(result.latencies_ms, 0.99):.3f} ms")
        print(f"latency best   : {min(result.latencies_ms):.3f} ms")
        print(f"latency worst  : {max(result.latencies_ms):.3f} ms")


if __name__ == "__main__":
    main()
