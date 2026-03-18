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


if __name__ == "__main__":
    unittest.main()
