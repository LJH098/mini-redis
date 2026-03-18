from dataclasses import dataclass
from typing import Union


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
    pass


@dataclass(frozen=True)
class RespError:
    message: str


RespValue = Union[SimpleString, BulkString, Integer, NullBulkString, RespError]
