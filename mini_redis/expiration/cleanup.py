from mini_redis.core.storage import Storage


class CleanupLoop:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def run_once(self) -> int:
        before = self.storage.size()
        self.storage.keys()
        after = self.storage.size()
        return max(before - after, 0)
