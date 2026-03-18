from mini_redis.core.dispatcher import CommandDispatcher, default_handlers
from mini_redis.core.storage import Storage
from mini_redis.expiration.manager import get_expiration_manager
from mini_redis.protocol.resp_types import BulkString, Integer, NullBulkString, RespError, SimpleString


def make_dispatcher() -> CommandDispatcher:
    storage = Storage()
    storage.set_expiration_checker(get_expiration_manager().is_expired)
    dispatcher = CommandDispatcher(storage=storage)
    dispatcher.register_many(default_handlers())
    return dispatcher


def test_ttl_flow_through_dispatcher() -> None:
    expiration_manager = get_expiration_manager()
    dispatcher = make_dispatcher()

    assert dispatcher.dispatch(["SET", "foo", "bar"]) == SimpleString("OK")
    expiration_manager.set_current_time(100.0)
    assert dispatcher.dispatch(["EXPIRE", "foo", "3"]) == Integer(1)
    assert dispatcher.dispatch(["TTL", "foo"]) == Integer(3)
    expiration_manager.set_current_time(104.0)
    assert dispatcher.dispatch(["GET", "foo"]) == NullBulkString()
    assert dispatcher.dispatch(["TTL", "foo"]) == Integer(-2)
    expiration_manager.set_current_time(None)


def test_ttl_commands_handle_invalid_input() -> None:
    dispatcher = make_dispatcher()

    assert dispatcher.dispatch(["EXPIRE", "foo"]) == RespError("wrong number of arguments")
    assert dispatcher.dispatch(["EXPIRE", "foo", "NaN"]) == RespError("invalid argument")


def test_basic_commands_still_work_with_ttl_storage() -> None:
    dispatcher = make_dispatcher()

    assert dispatcher.dispatch(["PING"]) == SimpleString("PONG")
    assert dispatcher.dispatch(["SET", "foo", "bar"]) == SimpleString("OK")
    assert dispatcher.dispatch(["GET", "foo"]) == BulkString("bar")
    assert dispatcher.dispatch(["EXISTS", "foo", "missing"]) == Integer(1)
    assert dispatcher.dispatch(["DEL", "foo"]) == Integer(1)
