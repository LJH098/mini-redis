from mini_redis.protocol.resp_types import (
    BulkString,
    Integer,
    NullBulkString,
    RespError,
    RespValue,
    SimpleString,
)


class RespSerializer:
    def serialize(self, value: RespValue) -> bytes:
        if isinstance(value, SimpleString):
            return f"+{value.value}\r\n".encode()
        if isinstance(value, BulkString):
            encoded = value.value.encode()
            return f"${len(encoded)}\r\n".encode() + encoded + b"\r\n"
        if isinstance(value, Integer):
            return f":{value.value}\r\n".encode()
        if isinstance(value, NullBulkString):
            return b"$-1\r\n"
        if isinstance(value, RespError):
            return f"-ERR {value.message}\r\n".encode()
        raise TypeError(f"Unsupported RESP type: {type(value)!r}")
