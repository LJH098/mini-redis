from __future__ import annotations

import logging
import selectors
import socket
import threading
import time
from typing import Callable, Optional

from mini_redis.config import (
    DEFAULT_MAX_BULK_BYTES,
    DEFAULT_MAX_BUFFER_BYTES,
    DEFAULT_READ_CHUNK_SIZE,
    DEFAULT_SELECT_TIMEOUT_SECONDS,
)
from mini_redis.server.session import Session, desired_events, handle_readable, handle_writable

LOGGER = logging.getLogger(__name__)


class TcpServer:
    def __init__(
        self,
        host: str,
        port: int,
        dispatcher,
        *,
        read_chunk_size: int = DEFAULT_READ_CHUNK_SIZE,
        max_buffer_bytes: int = DEFAULT_MAX_BUFFER_BYTES,
        max_bulk_bytes: int = DEFAULT_MAX_BULK_BYTES,
        maintenance_step: Optional[Callable[[float], None]] = None,
        select_timeout_seconds: float = DEFAULT_SELECT_TIMEOUT_SECONDS,
    ) -> None:
        self.host = host
        self.port = port
        self.dispatcher = dispatcher
        self.read_chunk_size = read_chunk_size
        self.max_buffer_bytes = max_buffer_bytes
        self.max_bulk_bytes = max_bulk_bytes
        self.maintenance_step = maintenance_step
        self.select_timeout_seconds = select_timeout_seconds
        self._selector: Optional[selectors.BaseSelector] = None
        self._server_socket: Optional[socket.socket] = None
        self._wakeup_reader: Optional[socket.socket] = None
        self._wakeup_writer: Optional[socket.socket] = None
        self._sessions: dict[socket.socket, Session] = {}
        self._stop_requested = threading.Event()
        self._ready = threading.Event()

    def serve_forever(self) -> None:
        self._stop_requested.clear()
        self._ready.clear()

        with selectors.DefaultSelector() as selector:
            self._selector = selector
            server_socket = self._create_server_socket()
            self._server_socket = server_socket
            wakeup_reader, wakeup_writer = socket.socketpair()
            self._wakeup_reader = wakeup_reader
            self._wakeup_writer = wakeup_writer
            wakeup_reader.setblocking(False)
            wakeup_writer.setblocking(False)

            selector.register(server_socket, selectors.EVENT_READ, data="listener")
            selector.register(wakeup_reader, selectors.EVENT_READ, data="wakeup")
            self._ready.set()

            try:
                while not self._stop_requested.is_set():
                    events = selector.select(timeout=self.select_timeout_seconds)
                    loop_now = time.time()
                    for key, mask in events:
                        if key.data == "listener":
                            self._accept_connections()
                        elif key.data == "wakeup":
                            self._drain_wakeup_socket()
                        else:
                            self._service_session(key.data, mask)

                    self._run_maintenance(loop_now)
            finally:
                self._ready.clear()
                self._close_all_sessions()
                self._close_socket(self._server_socket)
                self._close_socket(self._wakeup_reader)
                self._close_socket(self._wakeup_writer)
                self._selector = None
                self._server_socket = None
                self._wakeup_reader = None
                self._wakeup_writer = None

    def wait_until_ready(self, timeout: float = 1.0) -> bool:
        return self._ready.wait(timeout)

    def shutdown(self) -> None:
        self._stop_requested.set()
        if self._wakeup_writer is None:
            return
        try:
            self._wakeup_writer.send(b"\x00")
        except OSError:
            pass

    def _create_server_socket(self) -> socket.socket:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen()
        server_socket.setblocking(False)
        self.port = server_socket.getsockname()[1]
        return server_socket

    def _accept_connections(self) -> None:
        if self._server_socket is None or self._selector is None:
            return

        while True:
            try:
                client_socket, _ = self._server_socket.accept()
            except BlockingIOError:
                break

            client_socket.setblocking(False)
            session = Session(sock=client_socket)
            self._sessions[client_socket] = session
            self._selector.register(client_socket, selectors.EVENT_READ, data=session)

    def _service_session(self, session: Session, mask: int) -> None:
        try:
            if mask & selectors.EVENT_READ:
                handle_readable(
                    session,
                    self.dispatcher,
                    read_chunk_size=self.read_chunk_size,
                    max_buffer_bytes=self.max_buffer_bytes,
                    max_bulk_bytes=self.max_bulk_bytes,
                )
            if mask & selectors.EVENT_WRITE:
                handle_writable(session)
        except Exception:
            LOGGER.debug("Closing client session after unexpected error", exc_info=True)
            self._close_session(session)
            return

        self._refresh_interest(session)

    def _refresh_interest(self, session: Session) -> None:
        if self._selector is None:
            return

        events = desired_events(session)
        if events == 0:
            self._close_session(session)
            return

        try:
            self._selector.modify(session.sock, events, data=session)
        except KeyError:
            self._close_session(session)

    def _run_maintenance(self, loop_now: float) -> None:
        if self.maintenance_step is None:
            return
        try:
            self.maintenance_step(loop_now)
        except Exception:
            LOGGER.exception("Maintenance step failed")

    def _drain_wakeup_socket(self) -> None:
        if self._wakeup_reader is None:
            return

        while True:
            try:
                payload = self._wakeup_reader.recv(1024)
            except BlockingIOError:
                return
            if not payload:
                return

    def _close_session(self, session: Session) -> None:
        self._sessions.pop(session.sock, None)
        if self._selector is not None:
            try:
                self._selector.unregister(session.sock)
            except Exception:
                pass
        self._close_socket(session.sock)

    def _close_all_sessions(self) -> None:
        for session in list(self._sessions.values()):
            self._close_session(session)
        self._sessions.clear()

    @staticmethod
    def _close_socket(sock: Optional[socket.socket]) -> None:
        if sock is None:
            return
        try:
            sock.close()
        except OSError:
            pass
