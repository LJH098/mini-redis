from __future__ import annotations

from core.commands.basic import handle_get, handle_ping, handle_set
from core.commands.keyspace import handle_del, handle_exists
from core.models import RespError, Response
from core.storage import StorageEngine


class CommandDispatcher:
    def __init__(self, storage: StorageEngine | None = None) -> None:
        self.storage = storage or StorageEngine()
        self.handlers = {
            "PING": handle_ping,
            "SET": handle_set,
            "GET": handle_get,
            "DEL": handle_del,
            "EXISTS": handle_exists,
        }

    def dispatch(self, command: list[str]) -> Response:
        if not isinstance(command, list) or len(command) == 0:
            return RespError("invalid command")

        normalized_command = [str(part) for part in command]
        command_name = normalized_command[0].upper()
        handler = self.handlers.get(command_name)

        if handler is None:
            return RespError("unknown command")

        return handler(self.storage, normalized_command)
