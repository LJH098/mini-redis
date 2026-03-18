from typing import Optional, Tuple, Union

from mini_redis.config import DEFAULT_MAX_BULK_BYTES


class RespProtocolError(ValueError):
    """Raised when the RESP payload is malformed."""


ProtocolError = RespProtocolError


BytesLike = Union[bytes, bytearray]


def parse_command(
    buffer: BytesLike,
    *,
    max_bulk_bytes: int = DEFAULT_MAX_BULK_BYTES,
) -> Optional[Tuple[list[str], int]]:
    if max_bulk_bytes < 0:
        raise ValueError("max_bulk_bytes must be non-negative")
    if not buffer:
        return None
    if buffer[0:1] != b"*":
        raise RespProtocolError("expected array")

    header = _read_line(buffer, 1)
    if header is None:
        return None
    count_bytes, cursor = header
    count = _parse_non_negative_integer(count_bytes, "invalid array length")

    command: list[str] = []
    for _ in range(count):
        if cursor >= len(buffer):
            return None
        if buffer[cursor:cursor + 1] != b"$":
            raise RespProtocolError("expected bulk string")

        bulk_header = _read_line(buffer, cursor + 1)
        if bulk_header is None:
            return None
        bulk_size_bytes, cursor = bulk_header
        bulk_size = _parse_non_negative_integer(
            bulk_size_bytes,
            "invalid bulk string length",
        )
        if bulk_size > max_bulk_bytes:
            raise RespProtocolError("bulk string too large")

        payload_end = cursor + bulk_size
        if payload_end > len(buffer):
            return None
        terminator_end = payload_end + 2
        if terminator_end > len(buffer):
            if payload_end < len(buffer) and buffer[payload_end] != 13:
                raise RespProtocolError("missing bulk string terminator")
            return None
        if buffer[payload_end:terminator_end] != b"\r\n":
            raise RespProtocolError("missing bulk string terminator")

        chunk = bytes(buffer[cursor:payload_end])
        try:
            command.append(chunk.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise RespProtocolError("invalid utf-8") from exc
        cursor = terminator_end

    return command, cursor


class RespParser:
    def __init__(self, *, max_bulk_bytes: int = DEFAULT_MAX_BULK_BYTES) -> None:
        self.max_bulk_bytes = max_bulk_bytes

    def parse(self, payload: BytesLike) -> list[str]:
        parsed = parse_command(payload, max_bulk_bytes=self.max_bulk_bytes)
        if parsed is None:
            raise RespProtocolError("incomplete input")

        command, consumed = parsed
        if consumed != len(payload):
            raise RespProtocolError("trailing bytes after command")
        return command


def _read_line(buffer: BytesLike, start: int) -> Optional[Tuple[bytes, int]]:
    cursor = start
    while cursor < len(buffer):
        current = buffer[cursor]
        if current == 13:
            if cursor + 1 >= len(buffer):
                return None
            if buffer[cursor + 1] != 10:
                raise RespProtocolError("expected LF after CR")
            return bytes(buffer[start:cursor]), cursor + 2
        if current == 10:
            raise RespProtocolError("expected CRLF")
        cursor += 1
    return None


def _parse_non_negative_integer(raw: bytes, error_message: str) -> int:
    if not raw or not raw.isdigit():
        raise RespProtocolError(error_message)
    return int(raw)
