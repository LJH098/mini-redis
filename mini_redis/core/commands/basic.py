from mini_redis.core.storage import Storage
from mini_redis.protocol.resp_types import (
    BulkString,
    Integer,
    NullBulkString,
    RespError,
    RespValue,
    SimpleString,
)


def wrong_arity() -> RespError:
    return RespError("wrong number of arguments")


def handle_ping(storage: Storage, command: list[str]) -> RespValue:
    del storage
    if len(command) != 1:
        return wrong_arity()
    return SimpleString("PONG")


def handle_set(storage: Storage, command: list[str]) -> RespValue:
    if len(command) != 3:
        return wrong_arity()
    _, key, value = command
    storage.set(key, value)
    return SimpleString("OK")


def handle_get(storage: Storage, command: list[str]) -> RespValue:
    if len(command) != 2:
        return wrong_arity()
    value = storage.get(command[1])
    if value is None:
        return NullBulkString()
    return BulkString(value)


def handle_del(storage: Storage, command: list[str]) -> RespValue:
    if len(command) < 2:
        return wrong_arity()
    return Integer(storage.delete(*command[1:]))


def handle_exists(storage: Storage, command: list[str]) -> RespValue:
    if len(command) < 2:
        return wrong_arity()
    return Integer(storage.exists(*command[1:]))


def handle_incr(storage: Storage, command: list[str]) -> RespValue:
    if len(command) != 2:
        return wrong_arity()
    try:
        return Integer(storage.increment(command[1]))
    except ValueError:
        return RespError("value is not an integer")
