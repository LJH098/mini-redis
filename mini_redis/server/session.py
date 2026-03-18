from dataclasses import dataclass, field


@dataclass
class Session:
    buffer: bytearray = field(default_factory=bytearray)
