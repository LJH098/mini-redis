from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 6379
    snapshot_path: Path = field(default_factory=lambda: Path("data/snapshot.json"))
    snapshot_interval_seconds: float = 30.0
