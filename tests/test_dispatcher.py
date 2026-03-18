import unittest

from core.dispatcher import CommandDispatcher
from core.models import BulkString, Integer, NullBulkString, RespError, SimpleString
from core.storage import StorageEngine


class CommandDispatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = StorageEngine()
        self.dispatcher = CommandDispatcher(self.storage)

    def test_ping_without_message(self) -> None:
        reply = self.dispatcher.dispatch(["PING"])
        self.assertEqual(reply, SimpleString("PONG"))

    def test_ping_with_message(self) -> None:
        reply = self.dispatcher.dispatch(["PING", "hello"])
        self.assertEqual(reply, BulkString("hello"))

    def test_set_and_get(self) -> None:
        set_reply = self.dispatcher.dispatch(["SET", "name", "campus-link"])
        get_reply = self.dispatcher.dispatch(["GET", "name"])

        self.assertEqual(set_reply, SimpleString("OK"))
        self.assertEqual(get_reply, BulkString("campus-link"))

    def test_get_missing_key(self) -> None:
        reply = self.dispatcher.dispatch(["GET", "missing"])
        self.assertEqual(reply, NullBulkString())

    def test_del_and_exists(self) -> None:
        self.dispatcher.dispatch(["SET", "alpha", "1"])

        exists_before = self.dispatcher.dispatch(["EXISTS", "alpha"])
        delete_reply = self.dispatcher.dispatch(["DEL", "alpha"])
        exists_after = self.dispatcher.dispatch(["EXISTS", "alpha"])

        self.assertEqual(exists_before, Integer(1))
        self.assertEqual(delete_reply, Integer(1))
        self.assertEqual(exists_after, Integer(0))

    def test_unknown_command(self) -> None:
        reply = self.dispatcher.dispatch(["NOPE"])
        self.assertEqual(reply, RespError("unknown command"))

    def test_wrong_number_of_arguments(self) -> None:
        reply = self.dispatcher.dispatch(["SET", "only-key"])
        self.assertEqual(reply, RespError("wrong number of arguments"))

    def test_invalid_command_payload(self) -> None:
        reply = self.dispatcher.dispatch([])
        self.assertEqual(reply, RespError("invalid command"))

    def test_can_register_ttl_handlers_without_changing_dispatcher(self) -> None:
        def handle_expire(storage: StorageEngine, command: list[str]):
            if len(command) != 3:
                return RespError("wrong number of arguments")
            updated = storage.set_expire_at(command[1], float(command[2]))
            return Integer(1 if updated else 0)

        self.storage.set("cache:key", "value")
        self.dispatcher.register("EXPIRE", handle_expire)

        reply = self.dispatcher.dispatch(["EXPIRE", "cache:key", "10"])

        self.assertEqual(reply, Integer(1))
        self.assertEqual(self.storage.get_entry("cache:key").expire_at, 10.0)

    def test_register_many_supports_external_ttl_commands(self) -> None:
        def handle_ttl(storage: StorageEngine, command: list[str]):
            if len(command) != 2:
                return RespError("wrong number of arguments")

            entry = storage.get_entry(command[1])
            if entry is None:
                return Integer(-2)
            if entry.expire_at is None:
                return Integer(-1)
            return Integer(int(entry.expire_at))

        def handle_persist(storage: StorageEngine, command: list[str]):
            if len(command) != 2:
                return RespError("wrong number of arguments")
            cleared = storage.clear_expire_at(command[1])
            return Integer(1 if cleared else 0)

        self.storage.set("cache:key", "value")
        self.storage.set_expire_at("cache:key", 15.0)
        self.dispatcher.register_many({"TTL": handle_ttl, "PERSIST": handle_persist})

        ttl_reply = self.dispatcher.dispatch(["TTL", "cache:key"])
        persist_reply = self.dispatcher.dispatch(["PERSIST", "cache:key"])
        ttl_after_reply = self.dispatcher.dispatch(["TTL", "cache:key"])

        self.assertEqual(ttl_reply, Integer(15))
        self.assertEqual(persist_reply, Integer(1))
        self.assertEqual(ttl_after_reply, Integer(-1))


if __name__ == "__main__":
    unittest.main()
