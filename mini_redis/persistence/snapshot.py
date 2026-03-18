from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Optional, Protocol


class SnapshotLike(Protocol):
    value: str
    expire_at: Optional[float]


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class SnapshotRecord:
    value: str
    expire_at: Optional[float]


class SnapshotManager:
    def __init__(
        self,
        snapshot_path: Path,
        export_entries: Callable[[], dict[str, SnapshotLike]],
        restore_entries: Callable[[dict[str, SnapshotRecord]], None],
        interval_seconds: float = 30.0,
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        self._snapshot_path = Path(snapshot_path)
        self._export_entries = export_entries
        self._restore_entries = restore_entries
        self._interval_seconds = interval_seconds
        self._time_fn = time_fn

    def dump(
        self, entries: dict[str, SnapshotLike]
    ) -> dict[str, dict[str, Optional[float] | str]]:
        records = self._normalize_live_entries(entries)
        return {
            key: {"value": record.value, "expire_at": record.expire_at}
            for key, record in records.items()
        }

    def load(self, snapshot: dict[str, object]) -> dict[str, SnapshotRecord]:
        return self._normalize_loaded_entries(snapshot)

    def load_entries(self) -> dict[str, SnapshotRecord]:
        if not self._snapshot_path.exists():
            return {}

        try:
            payload = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SnapshotError("Snapshot file is not valid JSON") from exc

        return self._normalize_loaded_entries(payload)

    def restore_from_disk(self) -> dict[str, SnapshotRecord]:
        records = self.load_entries()
        self._restore_entries(records)
        return records

    def save_now(self) -> None:
        payload = self.dump(self._export_entries())
        self._atomic_write(payload)

    @property
    def interval_seconds(self) -> float:
        return self._interval_seconds

    def autosave_enabled(self) -> bool:
        return self._interval_seconds > 0

    def next_snapshot_at(self, last_snapshot_at: Optional[float]) -> Optional[float]:
        if not self.autosave_enabled():
            return None
        if last_snapshot_at is None:
            return self._time_fn() + self._interval_seconds
        return last_snapshot_at + self._interval_seconds

    def should_snapshot(
        self,
        last_snapshot_at: Optional[float],
        *,
        now: Optional[float] = None,
    ) -> bool:
        deadline = self.next_snapshot_at(last_snapshot_at)
        if deadline is None:
            return False
        current_time = self._time_fn() if now is None else now
        return current_time >= deadline

    def final_save(self) -> None:
        self.save_now()

    def _normalize_live_entries(
        self, entries: dict[str, SnapshotLike]
    ) -> dict[str, SnapshotRecord]:
        normalized: dict[str, SnapshotRecord] = {}
        for key, entry in entries.items():
            if not isinstance(key, str):
                raise SnapshotError("Snapshot keys must be strings")

            value = getattr(entry, "value", None)
            expire_at = getattr(entry, "expire_at", None)

            if not isinstance(value, str):
                raise SnapshotError("Snapshot value fields must be strings")
            if expire_at is not None and (
                not isinstance(expire_at, (int, float)) or isinstance(expire_at, bool)
            ):
                raise SnapshotError("Snapshot expire_at must be a float or null")

            normalized[key] = SnapshotRecord(
                value=value,
                expire_at=None if expire_at is None else float(expire_at),
            )
        return normalized

    def _normalize_loaded_entries(self, snapshot: object) -> dict[str, SnapshotRecord]:
        if not isinstance(snapshot, dict):
            raise SnapshotError("Snapshot top-level payload must be a dict")

        now = self._time_fn()
        normalized: dict[str, SnapshotRecord] = {}
        for key, payload in snapshot.items():
            if not isinstance(key, str):
                raise SnapshotError("Snapshot keys must be strings")
            if not isinstance(payload, dict):
                raise SnapshotError("Snapshot entries must be dict objects")
            if "value" not in payload:
                raise SnapshotError("Snapshot entries must include value")
            if "expire_at" not in payload:
                raise SnapshotError("Snapshot entries must include expire_at")

            value = payload["value"]
            expire_at = payload["expire_at"]
            if not isinstance(value, str):
                raise SnapshotError("Snapshot value fields must be strings")

            if expire_at is None:
                normalized_expire_at = None
            elif isinstance(expire_at, (int, float)) and not isinstance(expire_at, bool):
                normalized_expire_at = float(expire_at)
            else:
                raise SnapshotError("Snapshot expire_at must be a float or null")

            if normalized_expire_at is None or normalized_expire_at > now:
                normalized[key] = SnapshotRecord(
                    value=value,
                    expire_at=normalized_expire_at,
                )
        return normalized

    def _atomic_write(self, payload: dict[str, dict[str, object]]) -> None:
        self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._snapshot_path.parent,
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                self._write_payload(temp_file, payload)
                temp_file.flush()
                try:
                    os.fsync(temp_file.fileno())
                except OSError:
                    pass
            os.replace(temp_path, self._snapshot_path)
        except Exception:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise

    def _write_payload(self, temp_file, payload: dict[str, dict[str, object]]) -> None:
        json.dump(payload, temp_file, sort_keys=True)
