from dataclasses import dataclass
from typing import Optional, Union


@dataclass(slots=True)
class Entry:
    value: str
    expire_at: Optional[float] = None


@dataclass(frozen=True, slots=True)
class SimpleString:
    value: str


@dataclass(frozen=True, slots=True)
class BulkString:
    value: str


@dataclass(frozen=True, slots=True)
class Integer:
    value: int


@dataclass(frozen=True, slots=True)
class NullBulkString:
    value: None = None


@dataclass(frozen=True, slots=True)
class RespError:
    message: str


Response = Union[SimpleString, BulkString, Integer, NullBulkString, RespError]
