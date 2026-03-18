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


if __name__ == "__main__":
    unittest.main()
