import asyncio
import unittest

from mini_redis.protocol.resp_types import BulkString, RespError, SimpleString
from mini_redis.server.session import handle_client


class RecordingDispatcher:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def dispatch(self, command: list[str]):
        self.commands.append(command)
        if not command:
            return RespError("unknown command")
        if command[0] == "PING":
            return SimpleString("PONG")
        if command[0] == "ECHO":
            return BulkString(command[1])
        if command[0] == "NOPE":
            return RespError("unknown command")
        return SimpleString("OK")


class ExplodingDispatcher(RecordingDispatcher):
    def dispatch(self, command: list[str]):
        self.commands.append(command)
        if command and command[0] == "BOOM":
            raise RuntimeError("dispatcher failure")
        if not command:
            return RespError("unknown command")
        if command[0] == "PING":
            return SimpleString("PONG")
        return SimpleString("OK")


class SessionRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_single_connection_handles_multiple_commands(self) -> None:
        dispatcher = RecordingDispatcher()
        server = await self._start_server(dispatcher)
        reader, writer = await self._open_client(server)

        writer.write(
            b"*1\r\n$4\r\nping\r\n"
            b"*2\r\n$4\r\nECHO\r\n$5\r\nhello\r\n"
        )
        await writer.drain()

        self.assertEqual(await reader.readexactly(7), b"+PONG\r\n")
        self.assertEqual(await reader.readexactly(11), b"$5\r\nhello\r\n")
        self.assertEqual(dispatcher.commands, [["PING"], ["ECHO", "hello"]])

        writer.close()
        await writer.wait_closed()

    async def test_partial_input_waits_for_more_bytes(self) -> None:
        dispatcher = RecordingDispatcher()
        server = await self._start_server(dispatcher)
        reader, writer = await self._open_client(server)

        writer.write(b"*2\r\n$4\r\nECHO\r\n$5\r\nhe")
        await writer.drain()

        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(reader.read(1), timeout=0.05)

        writer.write(b"llo\r\n")
        await writer.drain()

        self.assertEqual(await reader.readexactly(11), b"$5\r\nhello\r\n")

        writer.close()
        await writer.wait_closed()

    async def test_protocol_error_uses_fixed_wire_response_and_closes(self) -> None:
        dispatcher = RecordingDispatcher()
        server = await self._start_server(dispatcher)
        reader, writer = await self._open_client(server)

        writer.write(b"PING\r\n")
        await writer.drain()

        self.assertEqual(await reader.readexactly(21), b"-ERR protocol error\r\n")
        self.assertEqual(await reader.read(), b"")

        writer.close()
        await writer.wait_closed()

    async def test_command_error_keeps_connection_open(self) -> None:
        dispatcher = RecordingDispatcher()
        server = await self._start_server(dispatcher)
        reader, writer = await self._open_client(server)

        writer.write(b"*1\r\n$4\r\nNOPE\r\n")
        await writer.drain()
        self.assertEqual(await reader.readexactly(22), b"-ERR unknown command\r\n")

        writer.write(b"*1\r\n$4\r\nPING\r\n")
        await writer.drain()
        self.assertEqual(await reader.readexactly(7), b"+PONG\r\n")

        writer.close()
        await writer.wait_closed()

    async def test_incomplete_buffer_limit_triggers_protocol_error(self) -> None:
        dispatcher = RecordingDispatcher()
        server = await self._start_server(dispatcher, max_buffer_bytes=8)
        reader, writer = await self._open_client(server)

        writer.write(b"*1\r\n$10\r\nabc")
        await writer.drain()

        self.assertEqual(await reader.readexactly(21), b"-ERR protocol error\r\n")
        self.assertEqual(await reader.read(), b"")

        writer.close()
        await writer.wait_closed()

    async def test_dispatcher_exception_only_closes_failing_session(self) -> None:
        dispatcher = ExplodingDispatcher()
        server = await self._start_server(dispatcher)

        failing_reader, failing_writer = await self._open_client(server)
        failing_writer.write(b"*1\r\n$4\r\nBOOM\r\n")
        await failing_writer.drain()
        self.assertEqual(await failing_reader.read(), b"")

        healthy_reader, healthy_writer = await self._open_client(server)
        healthy_writer.write(b"*1\r\n$4\r\nPING\r\n")
        await healthy_writer.drain()
        self.assertEqual(await healthy_reader.readexactly(7), b"+PONG\r\n")

        failing_writer.close()
        await failing_writer.wait_closed()
        healthy_writer.close()
        await healthy_writer.wait_closed()

    async def _start_server(self, dispatcher, **kwargs):
        server = await asyncio.start_server(
            lambda reader, writer: handle_client(reader, writer, dispatcher, **kwargs),
            "127.0.0.1",
            0,
        )
        self.addAsyncCleanup(self._close_server, server)
        return server

    async def _open_client(self, server):
        host, port = server.sockets[0].getsockname()[:2]
        return await asyncio.open_connection(host, port)

    async def _close_server(self, server) -> None:
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
