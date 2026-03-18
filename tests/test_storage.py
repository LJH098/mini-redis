from mini_redis.core.models import Entry
from mini_redis.core.storage import Storage
from mini_redis.expiration.manager import get_expiration_manager
from mini_redis.persistence.snapshot import SnapshotRecord


def test_storage_basic_operations() -> None:
    storage = Storage()

    created = storage.set("foo", "bar")

    assert isinstance(created, Entry)
    assert storage.get("foo") == "bar"
    assert storage.exists("foo") == 1
    assert storage.delete("foo") == 1
    assert storage.get("foo") is None


def test_storage_lazily_deletes_expired_keys() -> None:
    expiration_manager = get_expiration_manager()
    storage = Storage()
    storage.set_expiration_checker(expiration_manager.is_expired)
    storage.set("foo", "bar")

    expiration_manager.set_current_time(100.0)
    storage.set_expire_at("foo", expiration_manager.build_expire_at(1))
    expiration_manager.set_current_time(101.0)

    assert storage.get("foo") is None
    assert storage.exists("foo") == 0
    assert storage.keys() == []
    assert storage.size() == 0

    expiration_manager.set_current_time(None)


def test_storage_expiration_helpers_round_trip() -> None:
    storage = Storage()

    storage.set("cache:key", "value")

    assert storage.set_expire_at("cache:key", 123.456) is True
    assert storage.get_entry("cache:key").expire_at == 123.456
    assert storage.clear_expire_at("cache:key") is True
    assert storage.get_entry("cache:key").expire_at is None


def test_storage_supports_multi_key_delete_and_exists() -> None:
    storage = Storage()
    storage.set("alive", "v1")
    storage.set("expired", "v2")

    assert storage.exists("alive", "expired", "missing") == 2
    assert storage.delete("alive", "missing") == 1
    assert storage.exists("alive", "expired") == 1


def test_storage_export_entries_returns_independent_copy() -> None:
    storage = Storage()
    storage.set("foo", "bar")

    exported = storage.export_entries()
    exported["foo"].value = "changed"
    exported["new"] = Entry(value="other")

    assert storage.get("foo") == "bar"
    assert storage.get("new") is None


def test_storage_restore_entries_replaces_existing_state() -> None:
    storage = Storage()
    storage.set("old", "value")

    storage.restore_entries({"fresh": SnapshotRecord(value="new", expire_at=None)})

    assert storage.get("old") is None
    assert storage.get("fresh") == "new"


def test_storage_is_lock_free_for_event_loop_execution() -> None:
    storage = Storage()

    assert not hasattr(storage, "_lock")
