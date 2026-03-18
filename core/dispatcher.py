from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from core.commands.basic import handle_flushall, handle_get, handle_incr, handle_ping, handle_set
from core.commands.keyspace import handle_del, handle_exists
from core.models import RespError, Response
from core.storage import StorageEngine

CommandHandler = Callable[[StorageEngine, list[str]], Response]


class CommandDispatcher:
    def __init__(self, storage: Optional[StorageEngine] = None) -> None:
        self.storage = storage or StorageEngine()
        self.handlers: dict[str, CommandHandler] = {}
        self.register_many(
            {
                "PING": handle_ping,
                "SET": handle_set,
                "GET": handle_get,
                "INCR": handle_incr,
                "FLUSHALL": handle_flushall,
                "DEL": handle_del,
                "EXISTS": handle_exists,
            }
        )

    def register(self, command_name: str, handler: CommandHandler) -> None:
        self.handlers[str(command_name).upper()] = handler

    def register_many(self, handlers: dict[str, CommandHandler]) -> None:
        for command_name, handler in handlers.items():
            self.register(command_name, handler)

    def dispatch(self, command: list[str]) -> Response:
        if not isinstance(command, list) or len(command) == 0:
            return RespError("invalid command")

        normalized_command = [str(part) for part in command]
        command_name = normalized_command[0].upper()
        handler = self.handlers.get(command_name)

        if handler is None:
            return RespError("unknown command")

        return handler(self.storage, normalized_command)
