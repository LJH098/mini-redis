import unittest

from core.storage import StorageEngine


class StorageContractTest(unittest.TestCase):
    def test_items_exposes_internal_store_shape(self) -> None:
        storage = StorageEngine()
        storage.set("a", "1")
        storage.set("b", "2")

        items = dict(storage.items())

        self.assertIn("a", items)
        self.assertEqual(items["a"].value, "1")
        self.assertIn("b", items)
        self.assertEqual(items["b"].value, "2")


if __name__ == "__main__":
    unittest.main()
