from dataclasses import dataclass
from typing import Optional, Union


@dataclass
class Entry:
    value: str
    expire_at: Optional[float] = None


@dataclass(frozen=True)
class SimpleString:
    value: str


@dataclass(frozen=True)
class BulkString:
    value: str


@dataclass(frozen=True)
class Integer:
    value: int


@dataclass(frozen=True)
class NullBulkString:
    value: None = None


@dataclass(frozen=True)
class RespError:
    message: str


Response = Union[SimpleString, BulkString, Integer, NullBulkString, RespError]
