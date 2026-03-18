from __future__ import annotations

from .models import Entry


class StorageEngine:
    def __init__(self) -> None:
        self.store: dict[str, Entry] = {}

    def set(self, key: str, value: str) -> Entry:
        entry = Entry(value=str(value))
        self.store[str(key)] = entry
        return entry

    def get_entry(self, key: str) -> Entry | None:
        return self.store.get(str(key))

    def get(self, key: str) -> str | None:
        entry = self.get_entry(key)
        return entry.value if entry is not None else None

    def delete(self, key: str) -> bool:
        normalized_key = str(key)
        if normalized_key not in self.store:
            return False
        del self.store[normalized_key]
        return True

    def exists(self, key: str) -> bool:
        return self.get_entry(key) is not None

    def set_expire_at(self, key: str, expire_at: float) -> bool:
        entry = self.get_entry(key)
        if entry is None:
            return False
        entry.expire_at = expire_at
        return True

    def clear_expire_at(self, key: str) -> bool:
        entry = self.get_entry(key)
        if entry is None:
            return False
        entry.expire_at = None
        return True

    def size(self) -> int:
        return len(self.store)

    def items(self) -> list[tuple[str, Entry]]:
        return list(self.store.items())
