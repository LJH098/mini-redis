from mini_redis.core.storage import Storage


def cleanup_expired(storage: Storage) -> int:
    """Run one synchronous expiration sweep inside the event-loop thread."""
    return storage.cleanup_expired()


class CleanupLoop:
    """Compatibility wrapper for event-loop tick based cleanup."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def run_once(self) -> int:
        return cleanup_expired(self.storage)
