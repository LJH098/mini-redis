from mini_redis.core.models import Entry
from mini_redis.core.storage import Storage
from mini_redis.expiration.cleanup import cleanup_expired
from mini_redis.expiration.manager import ExpirationManager, get_expiration_manager


def test_expiration_manager_reports_ttl_states() -> None:
    manager = ExpirationManager()
    entry = Entry(value="bar")

    manager.set_current_time(100.0)

    assert manager.ttl(entry) == -1

    entry.expire_at = manager.build_expire_at(5)

    assert manager.ttl(entry) == 5
    manager.set_current_time(104.2)
    assert manager.ttl(entry) == 1
    manager.set_current_time(105.0)
    assert manager.ttl(entry) == -2
    manager.set_current_time(None)


def test_storage_ttl_contract() -> None:
    expiration_manager = get_expiration_manager()
    storage = Storage()
    storage.set_expiration_checker(expiration_manager.is_expired)
    storage.set("foo", "bar")

    assert storage.get_entry("missing") is None
    assert storage.get_entry("foo") is not None
    assert storage.get_entry("foo").expire_at is None

    expiration_manager.set_current_time(100.0)
    storage.set_expire_at("foo", expiration_manager.build_expire_at(3))

    entry = storage.get_entry("foo")
    assert entry is not None
    assert expiration_manager.ttl(entry) == 3

    expiration_manager.set_current_time(103.0)
    assert storage.get("foo") is None
    expiration_manager.set_current_time(None)


def test_persist_removes_expiration() -> None:
    expiration_manager = get_expiration_manager()
    storage = Storage()
    storage.set_expiration_checker(expiration_manager.is_expired)
    storage.set("foo", "bar")

    expiration_manager.set_current_time(100.0)
    storage.set_expire_at("foo", expiration_manager.build_expire_at(10))

    assert storage.clear_expire_at("foo") is True
    assert storage.get_entry("foo").expire_at is None
    assert storage.clear_expire_at("foo") is False
    expiration_manager.set_current_time(None)


def test_shared_manager_clock_can_be_reset() -> None:
    expiration_manager = get_expiration_manager()
    expiration_manager.set_current_time(123.0)
    assert expiration_manager.now() == 123.0
    expiration_manager.set_current_time(None)


def test_cleanup_expired_runs_synchronously_in_storage_thread() -> None:
    expiration_manager = get_expiration_manager()
    storage = Storage()
    storage.set_expiration_checker(expiration_manager.is_expired)
    storage.set("expired", "gone")
    storage.set("alive", "here")

    expiration_manager.set_current_time(100.0)
    storage.set_expire_at("expired", expiration_manager.build_expire_at(1))
    storage.set_expire_at("alive", expiration_manager.build_expire_at(10))

    expiration_manager.set_current_time(102.0)
    assert cleanup_expired(storage) == 1
    assert storage.get("expired") is None
    assert storage.get("alive") == "here"
    expiration_manager.set_current_time(None)
