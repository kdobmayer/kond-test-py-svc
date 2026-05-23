import threading
import time
from typing import Optional

from fastapi import Header, HTTPException

WINDOW_SECONDS = 60
MAX_REQUESTS = 10

_store: dict[str, list[float]] = {}
_lock = threading.Lock()


async def check_rate_limit(key: str) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds). retry_after is 0 when allowed."""
    now = time.time()
    cutoff = now - WINDOW_SECONDS

    with _lock:
        timestamps = _store.get(key, [])
        timestamps = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= MAX_REQUESTS:
            retry_after = int(timestamps[0] - cutoff) + 1
            _store[key] = timestamps
            return False, retry_after

        timestamps.append(now)
        _store[key] = timestamps
        return True, 0


def clear_rate_limit_state() -> None:
    with _lock:
        _store.clear()


async def require_rate_limit(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> str:
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="X-API-Key header is required")
    return x_api_key
