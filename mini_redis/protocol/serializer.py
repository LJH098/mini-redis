from mini_redis.protocol.resp_types import (
    BulkString,
    Integer,
    NullBulkString,
    RespError,
    RespValue,
    SimpleString,
)

CRLF = b"\r\n"


def encode_response(value: RespValue) -> bytes:
    if isinstance(value, SimpleString):
        return b"+" + value.value.encode("utf-8") + CRLF
    if isinstance(value, BulkString):
        encoded = value.value.encode("utf-8")
        return b"$" + str(len(encoded)).encode("ascii") + CRLF + encoded + CRLF
    if isinstance(value, Integer):
        return b":" + str(value.value).encode("ascii") + CRLF
    if isinstance(value, NullBulkString):
        return b"$-1\r\n"
    if isinstance(value, RespError):
        return b"-ERR " + value.message.encode("utf-8") + CRLF
    raise TypeError(f"Unsupported RESP type: {type(value)!r}")


class RespSerializer:
    def serialize(self, value: RespValue) -> bytes:
        return encode_response(value)
