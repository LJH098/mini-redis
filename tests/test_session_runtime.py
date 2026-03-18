import socket
import threading
import unittest

from mini_redis.protocol.resp_types import BulkString, RespError, SimpleString
from mini_redis.server.tcp_server import TcpServer


class RecordingDispatcher:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.thread_ids: list[int] = []
        self._lock = threading.Lock()

    def dispatch(self, command: list[str]):
        with self._lock:
            self.commands.append(command)
            self.thread_ids.append(threading.get_ident())
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
        with self._lock:
            self.commands.append(command)
            self.thread_ids.append(threading.get_ident())
        if command and command[0] == "BOOM":
            raise RuntimeError("dispatcher failure")
        if not command:
            return RespError("unknown command")
        if command[0] == "PING":
            return SimpleString("PONG")
        return SimpleString("OK")


class SessionRuntimeTest(unittest.TestCase):
    def test_single_connection_handles_multiple_commands(self) -> None:
        dispatcher = RecordingDispatcher()
        server, _ = self._start_server(dispatcher)
        client = self._open_client(server)

        client.sendall(
            b"*1\r\n$4\r\nping\r\n"
            b"*2\r\n$4\r\nECHO\r\n$5\r\nhello\r\n"
        )

        self.assertEqual(self._read_exactly(client, 7), b"+PONG\r\n")
        self.assertEqual(self._read_exactly(client, 11), b"$5\r\nhello\r\n")
        self.assertEqual(dispatcher.commands, [["PING"], ["ECHO", "hello"]])

        client.close()

    def test_partial_input_waits_for_more_bytes(self) -> None:
        dispatcher = RecordingDispatcher()
        server, _ = self._start_server(dispatcher)
        client = self._open_client(server)

        client.sendall(b"*2\r\n$4\r\nECHO\r\n$5\r\nhe")
        client.settimeout(0.05)
        with self.assertRaises(socket.timeout):
            client.recv(1)

        client.settimeout(1.0)
        client.sendall(b"llo\r\n")

        self.assertEqual(self._read_exactly(client, 11), b"$5\r\nhello\r\n")
        client.close()

    def test_protocol_error_uses_fixed_wire_response_and_closes(self) -> None:
        dispatcher = RecordingDispatcher()
        server, _ = self._start_server(dispatcher)
        client = self._open_client(server)

        client.sendall(b"PING\r\n")

        self.assertEqual(self._read_exactly(client, 21), b"-ERR protocol error\r\n")
        self.assertEqual(client.recv(1), b"")
        client.close()

    def test_command_error_keeps_connection_open(self) -> None:
        dispatcher = RecordingDispatcher()
        server, _ = self._start_server(dispatcher)
        client = self._open_client(server)

        client.sendall(b"*1\r\n$4\r\nNOPE\r\n")
        self.assertEqual(self._read_exactly(client, 22), b"-ERR unknown command\r\n")

        client.sendall(b"*1\r\n$4\r\nPING\r\n")
        self.assertEqual(self._read_exactly(client, 7), b"+PONG\r\n")
        client.close()

    def test_incomplete_buffer_limit_triggers_protocol_error(self) -> None:
        dispatcher = RecordingDispatcher()
        server, _ = self._start_server(dispatcher, max_buffer_bytes=8)
        client = self._open_client(server)

        client.sendall(b"*1\r\n$10\r\nabc")

        self.assertEqual(self._read_exactly(client, 21), b"-ERR protocol error\r\n")
        self.assertEqual(client.recv(1), b"")
        client.close()

    def test_dispatcher_exception_only_closes_failing_session(self) -> None:
        dispatcher = ExplodingDispatcher()
        server, _ = self._start_server(dispatcher)

        failing_client = self._open_client(server)
        failing_client.sendall(b"*1\r\n$4\r\nBOOM\r\n")
        self.assertEqual(failing_client.recv(1), b"")

        healthy_client = self._open_client(server)
        healthy_client.sendall(b"*1\r\n$4\r\nPING\r\n")
        self.assertEqual(self._read_exactly(healthy_client, 7), b"+PONG\r\n")

        failing_client.close()
        healthy_client.close()

    def test_dispatcher_runs_on_single_server_thread_for_multiple_clients(self) -> None:
        dispatcher = RecordingDispatcher()
        server, _ = self._start_server(dispatcher)
        ready = threading.Barrier(3)
        responses: list[bytes] = []
        lock = threading.Lock()

        def send_ping() -> None:
            client = self._open_client(server)
            try:
                ready.wait(timeout=1.0)
                client.sendall(b"*1\r\n$4\r\nPING\r\n")
                response = self._read_exactly(client, 7)
            finally:
                client.close()
            with lock:
                responses.append(response)

        first = threading.Thread(target=send_ping)
        second = threading.Thread(target=send_ping)
        first.start()
        second.start()
        ready.wait(timeout=1.0)
        first.join(timeout=1.0)
        second.join(timeout=1.0)

        self.assertEqual(responses, [b"+PONG\r\n", b"+PONG\r\n"])
        self.assertEqual(len(set(dispatcher.thread_ids)), 1)

    def test_maintenance_step_runs_on_idle_ticks(self) -> None:
        dispatcher = RecordingDispatcher()
        called = threading.Event()
        tick_times: list[float] = []

        def maintenance_step(now: float) -> None:
            tick_times.append(now)
            called.set()

        self._start_server(
            dispatcher,
            maintenance_step=maintenance_step,
            select_timeout_seconds=0.01,
        )

        self.assertTrue(called.wait(timeout=1.0))
        self.assertTrue(tick_times)

    def _start_server(self, dispatcher, **kwargs):
        kwargs.setdefault("select_timeout_seconds", 0.01)
        server = TcpServer(
            host="127.0.0.1",
            port=0,
            dispatcher=dispatcher,
            **kwargs,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self._stop_server, server, thread)
        self.assertTrue(server.wait_until_ready(timeout=1.0))
        return server, thread

    def _stop_server(self, server: TcpServer, thread: threading.Thread) -> None:
        server.shutdown()
        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive())

    @staticmethod
    def _open_client(server: TcpServer) -> socket.socket:
        client = socket.create_connection(("127.0.0.1", server.port), timeout=1.0)
        client.settimeout(1.0)
        return client

    @staticmethod
    def _read_exactly(client: socket.socket, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            chunk = client.recv(remaining)
            if not chunk:
                raise AssertionError("Socket closed before receiving expected payload")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


if __name__ == "__main__":
    unittest.main()
