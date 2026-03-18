from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_READ_CHUNK_SIZE = 4096
DEFAULT_MAX_BUFFER_BYTES = 1024 * 1024
DEFAULT_MAX_BULK_BYTES = 256 * 1024
DEFAULT_SELECT_TIMEOUT_SECONDS = 0.5


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 6379
    read_chunk_size: int = DEFAULT_READ_CHUNK_SIZE
    max_buffer_bytes: int = DEFAULT_MAX_BUFFER_BYTES
    max_bulk_bytes: int = DEFAULT_MAX_BULK_BYTES
    select_timeout_seconds: float = DEFAULT_SELECT_TIMEOUT_SECONDS
    snapshot_path: Path = field(default_factory=lambda: Path("data/snapshot.json"))
    snapshot_interval_seconds: float = 30.0
