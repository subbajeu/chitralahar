"""A tiny, dependency-free, per-process rate limiter.

Best-effort throttle for the admin login and the private-gallery passphrase. It
lives in memory, so with multiple gunicorn workers each worker counts
separately — that is fine as a speed bump, but the robust answer for a public
server is fail2ban on the failure log lines the callers emit. Keyed by a string
(typically "<scope>:<client-ip>").
"""
import time
from collections import defaultdict, deque
from threading import Lock

_BUCKETS: "defaultdict[str, deque]" = defaultdict(deque)
_LOCK = Lock()


def too_many(key: str, max_attempts: int = 6, window: int = 300) -> bool:
    """True if `key` already has >= max_attempts failures within `window` seconds."""
    now = time.time()
    with _LOCK:
        dq = _BUCKETS[key]
        while dq and now - dq[0] > window:
            dq.popleft()
        return len(dq) >= max_attempts


def record_failure(key: str, window: int = 300) -> None:
    now = time.time()
    with _LOCK:
        dq = _BUCKETS[key]
        dq.append(now)
        while dq and now - dq[0] > window:
            dq.popleft()


def reset(key: str) -> None:
    with _LOCK:
        _BUCKETS.pop(key, None)
