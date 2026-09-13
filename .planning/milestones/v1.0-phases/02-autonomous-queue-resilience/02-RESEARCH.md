# Phase 2: Autonomous Queue Resilience — Technical Research

## Research Objectives
1. Analyze `backend/server.py` queue draining (`run_tick`), scheduled actions schema, and state transitions.
2. Formulate bulletproof exponential backoff and dead-letter queue (DLQ) state semantics that withstand process restarts and concurrent worker execution.
3. Design a distributed, MongoDB-backed sliding window rate limiter that persists across process lifecycles and handles multi-worker concurrency.

---

## Technical Analysis

### 1. `db.scheduled_actions` Execution Lifecycle

#### Current State:
```python
due = await db.scheduled_actions.find(
    {"state": "PENDING", "run_at": {"$lte": started.isoformat()}}
).sort("run_at", 1).to_list(limit)

for doc in due:
    claim = await db.scheduled_actions.update_one(
        {"id": doc["id"], "state": "PENDING"},
        {"$set": {"state": "RUNNING", "started_at": now_iso()}, "$inc": {"attempts": 1}},
    )
    if not claim.modified_count:
        continue
    try:
        label = await _run_scheduled(doc)
        # sets state: "DONE"
    except Exception as e:
        # sets state: "FAILED", finishes and never retries
```

#### Identified Vulnerabilities:
1. **Single Point of Transient Failure**: If an upstream API returns HTTP 500, 502, or 429, the action immediately dies in `FAILED`. A temporary 2-second network hiccup permanently cancels follow-up emails, SMS, or supervisor re-checks.
2. **Missing Attempt Context**: The caller does not track how many retries remain, nor when next attempt should trigger.
3. **No Dead-Letter Observability**: Dead tasks sit interspersed with operational records without distinct status or operator-level management endpoints.

#### Resilient Architecture (RESIL-01):
```python
MAX_SCHEDULED_ATTEMPTS = int(os.environ.get("MAX_SCHEDULED_ATTEMPTS", "5"))
BACKOFF_BASE_SECONDS = int(os.environ.get("BACKOFF_BASE_SECONDS", "30"))
MAX_BACKOFF_SECONDS = int(os.environ.get("MAX_BACKOFF_SECONDS", "3600"))

def compute_backoff_seconds(attempt: int) -> int:
    return min(BACKOFF_BASE_SECONDS * (2 ** max(0, attempt - 1)), MAX_BACKOFF_SECONDS)
```
When `_run_scheduled` throws:
- Fetch updated `attempts`: `current_attempts = doc.get("attempts", 0) + 1`.
- If `current_attempts < MAX_SCHEDULED_ATTEMPTS`:
  - Calculate `next_run_at = now() + timedelta(seconds=compute_backoff_seconds(current_attempts))`.
  - Update document:
    ```python
    await db.scheduled_actions.update_one(
        {"id": doc["id"]},
        {
            "$set": {
                "state": "PENDING",
                "run_at": next_run_at.isoformat(),
                "last_error": str(e)[:500],
                "failed_at": now_iso(),
            }
        }
    )
    ```
  - Record audit event: `scheduled.retrying` (`meta={"attempt": current_attempts, "next_run_at": next_run_at.isoformat()}`).
- If `current_attempts >= MAX_SCHEDULED_ATTEMPTS`:
  - Update document:
    ```python
    await db.scheduled_actions.update_one(
        {"id": doc["id"]},
        {
            "$set": {
                "state": "DEAD_LETTER",
                "failed_at": now_iso(),
                "last_error": str(e)[:500],
                "dead_letter_reason": f"Exceeded max attempts ({MAX_SCHEDULED_ATTEMPTS})",
            }
        }
    )
    ```
  - Record audit event: `scheduled.dead_letter` (`meta={"attempts": current_attempts, "error": str(e)[:500]}`).

---

### 2. Distributed Rate Limiter with MongoDB TTL (RESIL-02)

#### Current State:
`_rate_buckets: dict[str, deque[float]] = defaultdict(deque)`
This in-memory deque:
- Loses all request history on restart.
- Cannot coordinate across multiple instances or workers.
- Has no persistent auditing.

#### Persistent MongoDB Pattern:
Create a dedicated `db.rate_limits` collection:
```python
# In startup or init:
await db.rate_limits.create_index([("expires_at", 1)], expireAfterSeconds=0)
await db.rate_limits.create_index([("key", 1), ("ts", 1)])
```

#### Sliding-Window Hit Algorithm:
```python
async def rate_limit(request: Request, bucket: str = "lead", per_min: int | None = None) -> None:
    limit = per_min if per_min is not None else LEAD_RATE_LIMIT_PER_MIN
    if limit <= 0:
        return

    ip = (request.client.host if request.client else "unknown") or "unknown"
    key = f"{bucket}:{ip}"
    current_time = now()
    window_start = (current_time - timedelta(seconds=60)).isoformat()

    try:
        # 1. Count recent hits within sliding 60-second window
        recent_hits = await db.rate_limits.count_documents({
            "key": key,
            "ts": {"$gte": window_start}
        })
        if recent_hits >= limit:
            raise HTTPException(429, f"Rate limit: max {limit} requests/minute")

        # 2. Record this request hit with auto-expiration (TTL 120s)
        await db.rate_limits.insert_one({
            "key": key,
            "ts": current_time.isoformat(),
            "expires_at": current_time + timedelta(seconds=120),
        })
    except HTTPException:
        raise
    except Exception as e:
        # Graceful degradation to in-memory sliding window if DB throws
        log.warning("mongo rate_limit failed, falling back to memory: %s", e)
        _in_memory_rate_limit(key, limit)
```

---

### 3. DLQ Operations & Management APIs

To enable operator visibility and administrative actions on dead-lettered tasks:
1. `GET /api/queue/dead-letter`:
   - Returns paginated list of documents with `state: "DEAD_LETTER"`.
   - Includes lead contact name/phone (via `$lookup` or batch lead fetch).
   - Includes error details, attempt history, and timestamps.
2. `POST /api/queue/dead-letter/{action_id}/retry`:
   - Requeues action: sets `state: "PENDING"`, `run_at: now_iso()`, `attempts: 0`, `error: None`.
   - Immediately schedules it for next `/api/tick`.

---

## Verification Strategy
- **Unit Tests (`test_tick.py`)**:
  - Test action failure increments `attempts` and reschedules with future `run_at`.
  - Test action reaching 5 attempts transitions to `DEAD_LETTER`.
  - Test dead-lettered actions are returned by `GET /api/queue/dead-letter`.
  - Test dead-lettered action retry resets state to `PENDING`.
  - Test `rate_limit` enforces limit in `FakeDB` and persists hit records.
