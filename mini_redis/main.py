from typing import Optional, Tuple

from mini_redis.config import ServerConfig
from mini_redis.core.dispatcher import CommandDispatcher, default_handlers
from mini_redis.core.storage import Storage
from mini_redis.expiration.manager import get_expiration_manager
from mini_redis.persistence.snapshot import SnapshotManager
from mini_redis.server.tcp_server import TcpServer


def create_components(
    config: Optional[ServerConfig] = None,
) -> Tuple[TcpServer, SnapshotManager]:
    resolved_config = config or ServerConfig()
    storage = Storage()
    storage.set_expiration_checker(get_expiration_manager().is_expired)
    snapshot_manager = SnapshotManager(
        snapshot_path=resolved_config.snapshot_path,
        export_entries=storage.export_entries,
        restore_entries=storage.restore_entries,
        interval_seconds=resolved_config.snapshot_interval_seconds,
    )
    snapshot_manager.restore_from_disk()
    dispatcher = CommandDispatcher(storage=storage)
    dispatcher.register_many(default_handlers())
    maintenance_step = _build_snapshot_maintenance_step(snapshot_manager)
    server = TcpServer(
        host=resolved_config.host,
        port=resolved_config.port,
        dispatcher=dispatcher,
        read_chunk_size=resolved_config.read_chunk_size,
        max_buffer_bytes=resolved_config.max_buffer_bytes,
        max_bulk_bytes=resolved_config.max_bulk_bytes,
        maintenance_step=maintenance_step,
        select_timeout_seconds=resolved_config.select_timeout_seconds,
    )
    return server, snapshot_manager


def create_app() -> TcpServer:
    server, _ = create_components()
    return server


def main() -> None:
    server, snapshot_manager = create_components()
    try:
        server.serve_forever()
    finally:
        snapshot_manager.final_save()


def _build_snapshot_maintenance_step(snapshot_manager: SnapshotManager):
    last_snapshot_at: Optional[float] = None

    def maintenance_step(now: float) -> None:
        nonlocal last_snapshot_at
        if not snapshot_manager.should_snapshot(last_snapshot_at, now=now):
            return
        snapshot_manager.save_now()
        last_snapshot_at = now

    return maintenance_step


if __name__ == "__main__":
    main()
