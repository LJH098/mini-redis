import math
import time
from typing import Callable, Optional

from mini_redis.core.models import Entry


class ExpirationManager:
    def __init__(self, now_provider: Optional[Callable[[], float]] = None) -> None:
        self._now_provider = now_provider or time.time
        self._fixed_now: Optional[float] = None

    def set_current_time(self, now: Optional[float]) -> None:
        self._fixed_now = now

    def now(self) -> float:
        if self._fixed_now is not None:
            return self._fixed_now
        return self._now_provider()

    def build_expire_at(self, seconds: int) -> float:
        return self.now() + seconds

    def is_expired(self, entry: Entry) -> bool:
        if entry.expire_at is None:
            return False
        return entry.expire_at <= self.now()

    def ttl(self, entry: Entry) -> int:
        if entry.expire_at is None:
            return -1

        remaining = entry.expire_at - self.now()
        if remaining <= 0:
            return -2
        return math.ceil(remaining)


_DEFAULT_EXPIRATION_MANAGER = ExpirationManager()


def get_expiration_manager() -> ExpirationManager:
    return _DEFAULT_EXPIRATION_MANAGER
