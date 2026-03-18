from __future__ import annotations

import selectors
import socket
from dataclasses import dataclass, field

from mini_redis.config import (
    DEFAULT_MAX_BULK_BYTES,
    DEFAULT_MAX_BUFFER_BYTES,
    DEFAULT_READ_CHUNK_SIZE,
)
from mini_redis.protocol.parser import RespProtocolError, parse_command
from mini_redis.protocol.resp_types import RespError, RespValue
from mini_redis.protocol.serializer import encode_response

PROTOCOL_ERROR_WIRE = b"-ERR protocol error\r\n"


@dataclass
class Session:
    sock: socket.socket
    in_buffer: bytearray = field(default_factory=bytearray)
    out_buffer: bytearray = field(default_factory=bytearray)
    close_after_flush: bool = False


def handle_readable(
    session: Session,
    dispatcher,
    *,
    read_chunk_size: int = DEFAULT_READ_CHUNK_SIZE,
    max_buffer_bytes: int = DEFAULT_MAX_BUFFER_BYTES,
    max_bulk_bytes: int = DEFAULT_MAX_BULK_BYTES,
) -> None:
    try:
        payload = session.sock.recv(read_chunk_size)
    except BlockingIOError:
        return

    if not payload:
        session.close_after_flush = True
        return

    session.in_buffer.extend(payload)

    try:
        while session.in_buffer:
            parsed = parse_command(session.in_buffer, max_bulk_bytes=max_bulk_bytes)
            if parsed is None:
                break

            command, consumed = parsed
            del session.in_buffer[:consumed]
            queue_response(session, _dispatch_command(dispatcher, command))
    except RespProtocolError:
        queue_protocol_error(session)
        return

    if session.in_buffer and len(session.in_buffer) > max_buffer_bytes:
        queue_protocol_error(session)


def handle_writable(session: Session) -> None:
    if not session.out_buffer:
        return

    try:
        sent = session.sock.send(session.out_buffer)
    except BlockingIOError:
        return

    if sent <= 0:
        raise ConnectionError("socket closed while sending")
    del session.out_buffer[:sent]


def desired_events(session: Session) -> int:
    if session.close_after_flush:
        return selectors.EVENT_WRITE if session.out_buffer else 0

    events = selectors.EVENT_READ
    if session.out_buffer:
        events |= selectors.EVENT_WRITE
    return events


def queue_response(session: Session, response: RespValue) -> None:
    session.out_buffer.extend(encode_response(response))


def queue_protocol_error(session: Session) -> None:
    session.in_buffer.clear()
    session.out_buffer.extend(PROTOCOL_ERROR_WIRE)
    session.close_after_flush = True


def _dispatch_command(dispatcher, command: list[str]) -> RespValue:
    if not command:
        return RespError("unknown command")

    normalized_command = [command[0].upper(), *command[1:]]
    return dispatcher.dispatch(normalized_command)
