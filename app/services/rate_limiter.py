"""
rate_limiter.py — Sliding-window rate limiter.
Uses Redis when available; falls back to in-memory (per-process) store.
Supports per-minute and per-day limits.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Optional

from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)

# ── In-memory fallback ────────────────────────────────────────────────────

class _InMemoryLimiter:
    def __init__(self) -> None:
        self._minute: dict[int, deque] = defaultdict(deque)
        self._day:    dict[int, deque] = defaultdict(deque)

    def _clean(self, dq: deque, window: float) -> None:
        now = time.time()
        while dq and dq[0] < now - window:
            dq.popleft()

    def check(self, user_id: int, per_min: int, per_day: int) -> tuple[bool, str]:
        now = time.time()
        mdq = self._minute[user_id]
        ddq = self._day[user_id]
        self._clean(mdq, 60)
        self._clean(ddq, 86400)
        if len(mdq) >= per_min:
            return False, "minute"
        if len(ddq) >= per_day:
            return False, "day"
        mdq.append(now)
        ddq.append(now)
        return True, ""


_in_memory = _InMemoryLimiter()
_redis_client = None


async def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not settings.redis_url:
        return None
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _redis_client.ping()
        log.info("rate_limiter_redis_connected")
        return _redis_client
    except Exception as exc:
        log.warning("rate_limiter_redis_unavailable", error=str(exc))
        _redis_client = None
        return None


async def check_rate_limit(user_id: int,
                           per_min: Optional[int] = None,
                           per_day: Optional[int] = None) -> tuple[bool, str]:
    """
    Returns (allowed: bool, violated_window: str).
    violated_window is '' if allowed, 'minute' or 'day' if blocked.
    """
    per_min = per_min or settings.rate_limit_per_minute
    per_day = per_day or settings.rate_limit_per_day

    redis = await _get_redis()
    if redis is None:
        return _in_memory.check(user_id, per_min, per_day)

    # Redis sliding window via sorted sets
    now = time.time()
    pipe = redis.pipeline()
    min_key  = f"rl:m:{user_id}"
    day_key  = f"rl:d:{user_id}"
    min_cut  = now - 60
    day_cut  = now - 86400

    pipe.zremrangebyscore(min_key, "-inf", min_cut)
    pipe.zremrangebyscore(day_key, "-inf", day_cut)
    pipe.zcard(min_key)
    pipe.zcard(day_key)
    results = await pipe.execute()

    min_count, day_count = results[2], results[3]
    if min_count >= per_min:
        return False, "minute"
    if day_count >= per_day:
        return False, "day"

    pipe2 = redis.pipeline()
    score = now
    pipe2.zadd(min_key,  {str(score): score})
    pipe2.zadd(day_key,  {str(score): score})
    pipe2.expire(min_key, 70)
    pipe2.expire(day_key, 90000)
    await pipe2.execute()
    return True, ""
