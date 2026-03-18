import unittest

from core.models import Entry
from core.storage import StorageEngine


class StorageEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = StorageEngine()

    def test_set_and_get_value(self) -> None:
        created = self.storage.set("user:1", "alice")

        self.assertIsInstance(created, Entry)
        self.assertEqual(self.storage.get("user:1"), "alice")
        self.assertEqual(self.storage.size(), 1)

    def test_delete_existing_key(self) -> None:
        self.storage.set("session:1", "active")

        self.assertTrue(self.storage.delete("session:1"))
        self.assertIsNone(self.storage.get("session:1"))
        self.assertEqual(self.storage.size(), 0)

    def test_delete_missing_key(self) -> None:
        self.assertFalse(self.storage.delete("missing"))

    def test_exists(self) -> None:
        self.storage.set("feature:flag", "on")

        self.assertTrue(self.storage.exists("feature:flag"))
        self.assertFalse(self.storage.exists("feature:missing"))

    def test_expiration_hooks_are_available(self) -> None:
        self.storage.set("cache:key", "value")

        self.assertTrue(self.storage.set_expire_at("cache:key", 123.456))
        self.assertEqual(self.storage.get_entry("cache:key").expire_at, 123.456)
        self.assertTrue(self.storage.clear_expire_at("cache:key"))
        self.assertIsNone(self.storage.get_entry("cache:key").expire_at)

    def test_expired_entry_is_deleted_on_get(self) -> None:
        storage = StorageEngine(expiration_checker=lambda entry: entry.expire_at == 1.0)
        storage.set("cache:key", "value")
        storage.set_expire_at("cache:key", 1.0)

        self.assertIsNone(storage.get("cache:key"))
        self.assertFalse(storage.exists("cache:key"))
        self.assertEqual(storage.size(), 0)

    def test_keys_filters_out_expired_entries(self) -> None:
        storage = StorageEngine(expiration_checker=lambda entry: entry.expire_at == 1.0)
        storage.set("alive", "v1")
        storage.set("expired", "v2")
        storage.set_expire_at("expired", 1.0)

        self.assertEqual(storage.keys(), ["alive"])
        self.assertEqual(storage.size(), 1)

    def test_expiration_checker_can_be_injected_later(self) -> None:
        self.storage.set("cache:key", "value")
        self.storage.set_expire_at("cache:key", 1.0)

        self.storage.set_expiration_checker(lambda entry: entry.expire_at == 1.0)

        self.assertIsNone(self.storage.get_entry("cache:key"))
        self.assertFalse(self.storage.exists("cache:key"))


if __name__ == "__main__":
    unittest.main()
