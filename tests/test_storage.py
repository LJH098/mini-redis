from mini_redis.core.storage import Storage
from mini_redis.expiration.manager import get_expiration_manager


def test_storage_basic_operations() -> None:
    storage = Storage()

    storage.set("foo", "bar")

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
