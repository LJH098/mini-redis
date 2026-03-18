from collections.abc import Callable

from mini_redis.core.commands.basic import (
    handle_del,
    handle_exists,
    handle_get,
    handle_ping,
    handle_set,
)
from mini_redis.core.storage import Storage
from mini_redis.protocol.resp_types import RespError, RespValue


CommandHandler = Callable[[Storage, list[str]], RespValue]


class CommandDispatcher:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, name: str, handler: CommandHandler) -> None:
        self._handlers[name.upper()] = handler

    def register_many(self, handlers: dict[str, CommandHandler]) -> None:
        for name, handler in handlers.items():
            self.register(name, handler)

    def dispatch(self, command: list[str]) -> RespValue:
        if not command:
            return RespError("unknown command")

        name = command[0].upper()
        handler = self._handlers.get(name)
        if handler is None:
            return RespError("unknown command")
        normalized_command = [name, *command[1:]]
        return handler(self.storage, normalized_command)


def default_handlers() -> dict[str, CommandHandler]:
    from mini_redis.core.commands.ttl import handle_expire, handle_persist, handle_ttl

    return {
        "PING": handle_ping,
        "SET": handle_set,
        "GET": handle_get,
        "DEL": handle_del,
        "EXISTS": handle_exists,
        "EXPIRE": handle_expire,
        "TTL": handle_ttl,
        "PERSIST": handle_persist,
    }
