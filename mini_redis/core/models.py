from dataclasses import dataclass
from typing import Optional


@dataclass
class Entry:
    value: str
    expire_at: Optional[float] = None
