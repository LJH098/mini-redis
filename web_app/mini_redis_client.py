from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Optional


class MiniRedisError(RuntimeError):
    pass


@dataclass
class MiniRedisClient:
    host: str
    port: int
    timeout_seconds: float = 2.0

    def ping(self) -> str:
        return self._send(["PING"])

    def get(self, key: str) -> Optional[str]:
        return self._send(["GET", key])

    def set(self, key: str, value: str) -> str:
        return self._send(["SET", key, value])

    def incr(self, key: str) -> int:
        return self._send(["INCR", key])

    def delete(self, *keys: str) -> int:
        return self._send(["DEL", *keys])

    def exists(self, key: str) -> int:
        return self._send(["EXISTS", key])

    def _send(self, parts: list[str]):
        payload = self._encode(parts)
        with socket.create_connection((self.host, self.port), timeout=self.timeout_seconds) as sock:
            sock.sendall(payload)
            return self._read_response(sock)

    @staticmethod
    def _encode(parts: list[str]) -> bytes:
        chunks = [f"*{len(parts)}\r\n".encode("ascii")]
        for part in parts:
            encoded = part.encode("utf-8")
            chunks.append(f"${len(encoded)}\r\n".encode("ascii"))
            chunks.append(encoded + b"\r\n")
        return b"".join(chunks)

    def _read_response(self, sock: socket.socket):
        prefix = self._read_exact(sock, 1)
        if prefix == b"+":
            return self._read_line(sock).decode("utf-8")
        if prefix == b"-":
            message = self._read_line(sock).decode("utf-8")
            if message.startswith("ERR "):
                message = message[4:]
            raise MiniRedisError(message)
        if prefix == b":":
            return int(self._read_line(sock).decode("ascii"))
        if prefix == b"$":
            length = int(self._read_line(sock).decode("ascii"))
            if length == -1:
                return None
            data = self._read_exact(sock, length)
            self._read_exact(sock, 2)
            return data.decode("utf-8")
        raise MiniRedisError("unsupported response type")

    @staticmethod
    def _read_line(sock: socket.socket) -> bytes:
        chunks = bytearray()
        while True:
            byte = MiniRedisClient._read_exact(sock, 1)
            chunks.extend(byte)
            if chunks.endswith(b"\r\n"):
                return bytes(chunks[:-2])

    @staticmethod
    def _read_exact(sock: socket.socket, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = sock.recv(size - len(chunks))
            if not chunk:
                raise MiniRedisError("connection closed unexpectedly")
            chunks.extend(chunk)
        return bytes(chunks)
