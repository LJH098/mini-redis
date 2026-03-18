from dataclasses import dataclass


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 6379
