import logging
from dataclasses import dataclass, field

from mini_redis.config import (
    DEFAULT_MAX_BULK_BYTES,
    DEFAULT_MAX_BUFFER_BYTES,
    DEFAULT_READ_CHUNK_SIZE,
)
from mini_redis.protocol.parser import RespProtocolError, parse_command
from mini_redis.protocol.resp_types import RespError, RespValue
from mini_redis.protocol.serializer import encode_response

LOGGER = logging.getLogger(__name__)
PROTOCOL_ERROR_WIRE = b"-ERR protocol error\r\n"


@dataclass
class Session:
    buffer: bytearray = field(default_factory=bytearray)


async def handle_client(
    reader,
    writer,
    dispatcher,
    *,
    read_chunk_size: int = DEFAULT_READ_CHUNK_SIZE,
    max_buffer_bytes: int = DEFAULT_MAX_BUFFER_BYTES,
    max_bulk_bytes: int = DEFAULT_MAX_BULK_BYTES,
) -> None:
    session = Session()

    try:
        while True:
            data = await reader.read(read_chunk_size)
            if not data:
                break

            session.buffer.extend(data)

            while session.buffer:
                parsed = parse_command(
                    session.buffer,
                    max_bulk_bytes=max_bulk_bytes,
                )
                if parsed is None:
                    break

                command, consumed = parsed
                del session.buffer[:consumed]
                response = _dispatch_command(dispatcher, command)
                await _write_response(writer, response)

            if session.buffer and len(session.buffer) > max_buffer_bytes:
                raise RespProtocolError("buffer limit exceeded")
    except RespProtocolError:
        await _write_protocol_error_and_close(writer)
        return
    except Exception:
        LOGGER.debug("Session closed after unexpected error", exc_info=True)
    finally:
        await _close_writer(writer)


def _dispatch_command(dispatcher, command: list[str]) -> RespValue:
    if not command:
        return RespError("unknown command")

    normalized_command = [command[0].upper(), *command[1:]]
    return dispatcher.dispatch(normalized_command)


async def _write_response(writer, response: RespValue) -> None:
    writer.write(encode_response(response))
    await writer.drain()


async def _write_protocol_error_and_close(writer) -> None:
    try:
        writer.write(PROTOCOL_ERROR_WIRE)
        await writer.drain()
    except Exception:
        LOGGER.exception("Failed to flush protocol error response")
    await _close_writer(writer)


async def _close_writer(writer) -> None:
    if writer.is_closing():
        await _wait_closed(writer)
        return

    writer.close()
    await _wait_closed(writer)


async def _wait_closed(writer) -> None:
    try:
        await writer.wait_closed()
    except Exception:
        LOGGER.debug("Ignoring wait_closed() failure for client session", exc_info=True)
