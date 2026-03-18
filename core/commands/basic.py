from __future__ import annotations

from core.models import BulkString, Integer, NullBulkString, RespError, Response, SimpleString
from core.storage import StorageEngine


def handle_ping(_storage: StorageEngine, command: list[str]) -> Response:
    if len(command) not in (1, 2):
        return RespError("wrong number of arguments")

    if len(command) == 1:
        return SimpleString("PONG")

    return BulkString(command[1])


def handle_set(storage: StorageEngine, command: list[str]) -> Response:
    if len(command) != 3:
        return RespError("wrong number of arguments")

    storage.set(command[1], command[2])
    return SimpleString("OK")


def handle_get(storage: StorageEngine, command: list[str]) -> Response:
    if len(command) != 2:
        return RespError("wrong number of arguments")

    value = storage.get(command[1])
    if value is None:
        return NullBulkString()

    return BulkString(value)


def handle_incr(storage: StorageEngine, command: list[str]) -> Response:
    if len(command) != 2:
        return RespError("wrong number of arguments")

    try:
        return Integer(storage.increment(command[1]))
    except ValueError:
        return RespError("value is not an integer")


def handle_flushall(storage: StorageEngine, command: list[str]) -> Response:
    if len(command) != 1:
        return RespError("wrong number of arguments")

    storage.clear()
    return SimpleString("OK")
