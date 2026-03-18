import unittest

from mini_redis.protocol.parser import RespParser, RespProtocolError, parse_command
from mini_redis.protocol.resp_types import BulkString, Integer, NullBulkString, RespError, SimpleString
from mini_redis.protocol.serializer import RespSerializer, encode_response


class ParseCommandTest(unittest.TestCase):
    def test_parse_complete_bulk_array(self) -> None:
        payload = b"*2\r\n$3\r\nGET\r\n$3\r\nkey\r\n"

        parsed = parse_command(payload)

        self.assertEqual(parsed, (["GET", "key"], len(payload)))

    def test_parse_empty_command(self) -> None:
        self.assertEqual(parse_command(b"*0\r\n"), ([], 4))

    def test_parse_empty_bulk_string(self) -> None:
        payload = b"*3\r\n$3\r\nSET\r\n$1\r\nk\r\n$0\r\n\r\n"

        parsed = parse_command(payload)

        self.assertEqual(parsed, (["SET", "k", ""], len(payload)))

    def test_parse_utf8_multibyte_bulk_string(self) -> None:
        value = "안녕"
        encoded = value.encode("utf-8")
        payload = (
            b"*2\r\n"
            b"$4\r\nECHO\r\n"
            + f"${len(encoded)}\r\n".encode("ascii")
            + encoded
            + b"\r\n"
        )

        parsed = parse_command(payload)

        self.assertEqual(parsed, (["ECHO", value], len(payload)))

    def test_parse_returns_none_for_incomplete_input_only(self) -> None:
        self.assertIsNone(parse_command(b""))
        self.assertIsNone(parse_command(b"*2\r\n$3\r\nGET\r\n$3\r\n"))
        self.assertIsNone(parse_command(b"*2\r\n$3\r\nGET\r\n$3\r\nke"))

    def test_parse_consumed_excludes_trailing_bytes(self) -> None:
        first = b"*1\r\n$4\r\nPING\r\n"
        second = b"*2\r\n$4\r\nECHO\r\n$5\r\nhello\r\n"

        parsed = parse_command(first + second)

        self.assertEqual(parsed, (["PING"], len(first)))

    def test_parse_rejects_malformed_inputs(self) -> None:
        with self.assertRaises(RespProtocolError):
            parse_command(b"PING\r\n")
        with self.assertRaises(RespProtocolError):
            parse_command(b"*1\r\n$-1\r\n")
        with self.assertRaises(RespProtocolError):
            parse_command(b"*1\n")
        with self.assertRaises(RespProtocolError):
            parse_command(b"*1\r\n+4\r\nPING\r\n")
        with self.assertRaises(RespProtocolError):
            parse_command(b"*1\r\n$3\r\nabc\n")

    def test_parse_rejects_invalid_utf8_and_oversized_bulk(self) -> None:
        with self.assertRaises(RespProtocolError):
            parse_command(b"*1\r\n$1\r\n\xff\r\n")
        with self.assertRaises(RespProtocolError):
            parse_command(b"*1\r\n$5\r\nhello\r\n", max_bulk_bytes=4)

    def test_parser_wrapper_requires_exactly_one_complete_command(self) -> None:
        parser = RespParser()

        self.assertEqual(parser.parse(b"*1\r\n$4\r\nPING\r\n"), ["PING"])

        with self.assertRaises(RespProtocolError):
            parser.parse(b"*1\r\n$4\r\nPING\r\n*1\r\n$4\r\nPING\r\n")
        with self.assertRaises(RespProtocolError):
            parser.parse(b"*1\r\n$4\r\nPIN")


class RespSerializerTest(unittest.TestCase):
    def test_resp_serializer_handles_core_types(self) -> None:
        serializer = RespSerializer()

        self.assertEqual(serializer.serialize(SimpleString("OK")), b"+OK\r\n")
        self.assertEqual(serializer.serialize(BulkString("hello")), b"$5\r\nhello\r\n")
        self.assertEqual(serializer.serialize(Integer(1)), b":1\r\n")
        self.assertEqual(serializer.serialize(NullBulkString()), b"$-1\r\n")
        self.assertEqual(
            serializer.serialize(RespError("unknown command")),
            b"-ERR unknown command\r\n",
        )

    def test_encode_response_uses_utf8_byte_length(self) -> None:
        self.assertEqual(encode_response(BulkString("안녕")), b"$6\r\n\xec\x95\x88\xeb\x85\x95\r\n")


if __name__ == "__main__":
    unittest.main()
