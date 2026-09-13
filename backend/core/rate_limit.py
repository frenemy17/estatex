from __future__ import annotations

import os
import sys
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import HTTPException, Request

from core.database import get_db, log, now

LEAD_RATE_LIMIT_PER_MIN = int(os.environ.get("LEAD_RATE_LIMIT_PER_MIN", "10"))

_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def _in_memory_rate_limit(key: str, limit: int) -> None:
    """Per-IP sliding window fallback using local memory."""
    # Check if server._rate_buckets was patched or shared
    srv = sys.modules.get("server")
    buckets = getattr(srv, "_rate_buckets", _rate_buckets) if srv else _rate_buckets

    window = buckets[key]
    cutoff = time.monotonic() - 60
    while window and window[0] < cutoff:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(429, f"Rate limit: max {limit} requests/minute")
    window.append(time.monotonic())


async def rate_limit(request: Request, bucket: str = "lead", per_min: int | None = None) -> None:
    """Per-IP sliding window backed by MongoDB db.rate_limits with in-memory fallback.

    The public capture form reaches the LLM, so an unthrottled endpoint is a billing hole
    as much as an abuse one.
    """
    srv = sys.modules.get("server")
    configured_limit = (
        getattr(srv, "LEAD_RATE_LIMIT_PER_MIN", LEAD_RATE_LIMIT_PER_MIN)
        if srv
        else LEAD_RATE_LIMIT_PER_MIN
    )
    limit = per_min if per_min is not None else configured_limit
    if limit <= 0:
        return
    ip = (request.client.host if request.client else "unknown") or "unknown"
    key = f"{bucket}:{ip}"
    cutoff = (now() - timedelta(seconds=60)).isoformat()

    try:
        current_db = get_db()
        count = await current_db.rate_limits.count_documents({"key": key, "ts": {"$gte": cutoff}})
        if count >= limit:
            raise HTTPException(429, f"Rate limit: max {limit} requests/minute")

        current_time = now()
        await current_db.rate_limits.insert_one(
            {
                "key": key,
                "ts": current_time.isoformat(),
                "expires_at": current_time + timedelta(seconds=120),
            }
        )
        buckets = getattr(srv, "_rate_buckets", _rate_buckets) if srv else _rate_buckets
        buckets[key].append(time.monotonic())
    except HTTPException:
        raise
    except Exception as e:
        log.warning("mongo rate_limits check failed (%s), falling back to in-memory: %s", key, e)
        _in_memory_rate_limit(key, limit)
