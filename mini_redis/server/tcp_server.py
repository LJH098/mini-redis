import asyncio
from functools import partial

from mini_redis.config import (
    DEFAULT_MAX_BULK_BYTES,
    DEFAULT_MAX_BUFFER_BYTES,
    DEFAULT_READ_CHUNK_SIZE,
)
from mini_redis.server.session import handle_client


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
    ) -> None:
        self.host = host
        self.port = port
        self.dispatcher = dispatcher
        self.read_chunk_size = read_chunk_size
        self.max_buffer_bytes = max_buffer_bytes
        self.max_bulk_bytes = max_bulk_bytes

    async def serve(self) -> None:
        handler = partial(
            handle_client,
            dispatcher=self.dispatcher,
            read_chunk_size=self.read_chunk_size,
            max_buffer_bytes=self.max_buffer_bytes,
            max_bulk_bytes=self.max_bulk_bytes,
        )
        server = await asyncio.start_server(handler, self.host, self.port)
        async with server:
            await server.serve_forever()

    def serve_forever(self) -> None:
        asyncio.run(self.serve())
