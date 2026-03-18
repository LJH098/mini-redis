from typing import Optional

from mini_redis.core.models import Entry


class SnapshotManager:
    def dump(self, entries: dict[str, Entry]) -> dict[str, dict[str, Optional[object]]]:
        return {
            key: {"value": entry.value, "expire_at": entry.expire_at}
            for key, entry in entries.items()
        }

    def load(self, snapshot: dict[str, dict[str, Optional[object]]]) -> dict[str, Entry]:
        return {
            key: Entry(
                value=str(payload["value"]),
                expire_at=payload["expire_at"],  # type: ignore[arg-type]
            )
            for key, payload in snapshot.items()
        }
