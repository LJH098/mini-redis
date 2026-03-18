from __future__ import annotations

from collections.abc import Callable

from .models import Entry

ExpirationChecker = Callable[[Entry], bool]


class StorageEngine:
    def __init__(self, expiration_checker: ExpirationChecker | None = None) -> None:
        self._store: dict[str, Entry] = {}
        self._expiration_checker = expiration_checker

    def set_expiration_checker(
        self,
        expiration_checker: ExpirationChecker | None,
    ) -> None:
        self._expiration_checker = expiration_checker

    def set(self, key: str, value: str) -> Entry:
        normalized_key = str(key)
        entry = Entry(value=str(value))
        self._store[normalized_key] = entry
        return entry

    def get_entry(self, key: str) -> Entry | None:
        normalized_key = str(key)
        entry = self._store.get(normalized_key)
        return self._evict_if_expired(normalized_key, entry)

    def get(self, key: str) -> str | None:
        entry = self.get_entry(key)
        return entry.value if entry is not None else None

    def delete(self, key: str) -> bool:
        normalized_key = str(key)
        if normalized_key not in self._store:
            return False
        del self._store[normalized_key]
        return True

    def exists(self, key: str) -> bool:
        return self.get_entry(key) is not None

    def set_expire_at(self, key: str, expire_at: float) -> bool:
        entry = self.get_entry(key)
        if entry is None:
            return False
        entry.expire_at = float(expire_at)
        return True

    def clear_expire_at(self, key: str) -> bool:
        entry = self.get_entry(key)
        if entry is None:
            return False
        entry.expire_at = None
        return True

    def size(self) -> int:
        self._cleanup_expired_keys()
        return len(self._store)

    def keys(self) -> list[str]:
        self._cleanup_expired_keys()
        return list(self._store.keys())

    def _cleanup_expired_keys(self) -> None:
        if self._expiration_checker is None:
            return

        for key in list(self._store.keys()):
            self.get_entry(key)

    def _evict_if_expired(self, key: str, entry: Entry | None) -> Entry | None:
        if entry is None:
            return None
        if self._expiration_checker is None:
            return entry
        if not self._expiration_checker(entry):
            return entry

        self.delete(key)
        return None
