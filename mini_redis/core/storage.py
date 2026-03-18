from typing import Callable, Optional

from mini_redis.core.models import Entry


class Storage:
    def __init__(self, initial_data: Optional[dict[str, Entry]] = None) -> None:
        self._store: dict[str, Entry] = initial_data or {}
        self._expiration_checker: Optional[Callable[[Entry], bool]] = None

    def set_expiration_checker(
        self,
        expiration_checker: Optional[Callable[[Entry], bool]],
    ) -> None:
        self._expiration_checker = expiration_checker

    def set(self, key: str, value: str) -> Entry:
        entry = Entry(value=value)
        self._store[key] = entry
        return entry

    def _is_expired(self, entry: Entry) -> bool:
        if self._expiration_checker is None:
            return False
        return self._expiration_checker(entry)

    def _purge_if_expired(self, key: str, entry: Entry) -> bool:
        if not self._is_expired(entry):
            return False
        self._store.pop(key, None)
        return True

    def get_entry(self, key: str) -> Optional[Entry]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if self._purge_if_expired(key, entry):
            return None
        return entry

    def get(self, key: str) -> Optional[str]:
        entry = self.get_entry(key)
        return None if entry is None else entry.value

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if self.get_entry(key) is None:
                continue
            self._store.pop(key, None)
            deleted += 1
        return deleted

    def exists(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if self.get_entry(key) is not None:
                count += 1
        return count

    def set_expire_at(self, key: str, expire_at: Optional[float]) -> bool:
        entry = self.get_entry(key)
        if entry is None:
            return False
        entry.expire_at = expire_at
        self._purge_if_expired(key, entry)
        return True

    def clear_expire_at(self, key: str) -> bool:
        entry = self.get_entry(key)
        if entry is None or entry.expire_at is None:
            return False
        entry.expire_at = None
        return True

    def keys(self) -> list[str]:
        available_keys: list[str] = []
        for key in list(self._store.keys()):
            if self.get_entry(key) is not None:
                available_keys.append(key)
        return available_keys

    def size(self) -> int:
        return len(self.keys())
