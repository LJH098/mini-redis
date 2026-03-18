import unittest

from core.dispatcher import CommandDispatcher
from core.models import Entry, Integer
from core.storage import StorageEngine


class Role2ContractTest(unittest.TestCase):
    def test_entry_model_uses_value_and_optional_expire_at(self) -> None:
        entry = Entry(value="hello")

        self.assertEqual(entry.value, "hello")
        self.assertIsNone(entry.expire_at)

    def test_storage_hides_internal_store_and_exposes_public_methods(self) -> None:
        storage = StorageEngine()

        self.assertFalse(hasattr(storage, "store"))
        self.assertTrue(hasattr(storage, "get"))
        self.assertTrue(hasattr(storage, "set"))
        self.assertTrue(hasattr(storage, "delete"))
        self.assertTrue(hasattr(storage, "exists"))
        self.assertTrue(hasattr(storage, "get_entry"))

    def test_dispatcher_registers_handlers_with_storage_and_string_args(self) -> None:
        storage = StorageEngine()
        dispatcher = CommandDispatcher(storage)

        def handle_expire(bound_storage: StorageEngine, command: list[str]):
            self.assertIs(bound_storage, storage)
            self.assertEqual(command, ["EXPIRE", "cache:key", "10"])
            return Integer(1)

        dispatcher.register("EXPIRE", handle_expire)

        reply = dispatcher.dispatch(["EXPIRE", "cache:key", 10])

        self.assertEqual(reply, Integer(1))


if __name__ == "__main__":
    unittest.main()
