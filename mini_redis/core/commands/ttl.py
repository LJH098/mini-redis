from typing import Optional

from mini_redis.core.commands.basic import wrong_arity
from mini_redis.core.storage import Storage
from mini_redis.expiration.manager import get_expiration_manager
from mini_redis.protocol.resp_types import Integer, RespError, RespValue


def _parse_seconds(raw: str) -> Optional[int]:
    try:
        return int(raw)
    except ValueError:
        return None


def invalid_argument() -> RespError:
    return RespError("invalid argument")


def handle_expire(storage: Storage, command: list[str]) -> RespValue:
    if len(command) != 3:
        return wrong_arity()

    _, key, raw_seconds = command
    seconds = _parse_seconds(raw_seconds)
    if seconds is None:
        return invalid_argument()

    entry = storage.get_entry(key)
    if entry is None:
        return Integer(0)

    expiration_manager = get_expiration_manager()
    expire_at = expiration_manager.build_expire_at(seconds)
    storage.set_expire_at(key, expire_at)
    storage.get_entry(key)
    return Integer(1)


def handle_ttl(storage: Storage, command: list[str]) -> RespValue:
    if len(command) != 2:
        return wrong_arity()

    entry = storage.get_entry(command[1])
    if entry is None:
        return Integer(-2)
    if entry.expire_at is None:
        return Integer(-1)

    return Integer(get_expiration_manager().ttl(entry))


def handle_persist(storage: Storage, command: list[str]) -> RespValue:
    if len(command) != 2:
        return wrong_arity()

    entry = storage.get_entry(command[1])
    if entry is None or entry.expire_at is None:
        return Integer(0)
    return Integer(1 if storage.clear_expire_at(command[1]) else 0)
