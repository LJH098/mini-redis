from __future__ import annotations

from core.models import Integer, RespError, Response
from core.storage import StorageEngine


def handle_del(storage: StorageEngine, command: list[str]) -> Response:
    if len(command) != 2:
        return RespError("wrong number of arguments")

    deleted = storage.delete(command[1])
    return Integer(1 if deleted else 0)


def handle_exists(storage: StorageEngine, command: list[str]) -> Response:
    if len(command) != 2:
        return RespError("wrong number of arguments")

    exists = storage.exists(command[1])
    return Integer(1 if exists else 0)
