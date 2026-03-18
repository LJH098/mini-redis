from mini_redis.protocol.parser import RespParser
from mini_redis.protocol.resp_types import BulkString, Integer, NullBulkString, RespError, SimpleString
from mini_redis.protocol.serializer import RespSerializer


def test_resp_parser_handles_bulk_array() -> None:
    parser = RespParser()

    payload = b"*2\r\n$3\r\nGET\r\n$3\r\nkey\r\n"

    assert parser.parse(payload) == ["GET", "key"]


def test_resp_serializer_handles_core_types() -> None:
    serializer = RespSerializer()

    assert serializer.serialize(SimpleString("OK")) == b"+OK\r\n"
    assert serializer.serialize(BulkString("hello")) == b"$5\r\nhello\r\n"
    assert serializer.serialize(Integer(1)) == b":1\r\n"
    assert serializer.serialize(NullBulkString()) == b"$-1\r\n"
    assert serializer.serialize(RespError("unknown command")) == b"-ERR unknown command\r\n"
