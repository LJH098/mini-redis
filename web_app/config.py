import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://mongo:27017")
    mongo_db: str = os.getenv("MONGO_DB", "mini_redis_demo")
    mini_redis_host: str = os.getenv("MINI_REDIS_HOST", "host.docker.internal")
    mini_redis_port: int = int(os.getenv("MINI_REDIS_PORT", "6379"))
    like_target: int = int(os.getenv("LIKE_TARGET", "10"))
    compare_document_id: str = os.getenv("COMPARE_DOCUMENT_ID", "demo-user")


config = AppConfig()
