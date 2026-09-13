# Phase 2: Plan 2 Summary
**Autonomous Queue Resilience: Persistent MongoDB-Backed Distributed Rate Limiter**

## Outcome
Upgraded lead capture rate limiting from ephemeral process memory to a distributed MongoDB-backed sliding window with automatic 120s TTL document expiration and local memory fallback.

## Completed Tasks
1. **Task 1: Implement MongoDB-Backed Sliding Window Rate Limiter with TTL Index**
   - Converted `rate_limit()` in `backend/server.py` to `async def`.
   - Connected `rate_limit()` to `current_db.rate_limits`, counting recent hits within a 60-second sliding window (`ts >= now() - 60s`).
   - Inserts hit document into `db.rate_limits` with `expires_at: now() + 120s` for automatic MongoDB TTL cleanup.
   - Updated `lifespan` startup to ensure TTL index on `expires_at` (`expireAfterSeconds=0`) and compound index on `("key", 1), ("ts", 1)`.
   - Added `_in_memory_rate_limit(key, limit)` fallback to maintain protection even if MongoDB is temporarily unreachable or mocked.
   - Updated `create_lead` route handler to await `rate_limit(request, "lead")`.

2. **Task 2: Validate Distributed Rate Limiter Persistence Across Server Restarts**
   - Enhanced `test_lead_capture_is_rate_limited_per_ip` in `backend/tests/test_tick.py` to assert hit documents are written to `db.rate_limits` with `expires_at`.
   - Added `test_rate_limit_persists_across_in_memory_cache_clearing` asserting that clearing in-memory caches (simulating process recycle or multiple worker nodes) continues to reject abusive IPs with HTTP 429 using the MongoDB state.

3. **Task 3: Full Test Suite Regression Pass**
   - Executed full test suite across all 78 tests.
   - 100% pass rate achieved with zero regressions.

## Verification
- Test command: `backend/.venv/bin/pytest backend/tests/`
- Result: 78 passed in 1.16s.
