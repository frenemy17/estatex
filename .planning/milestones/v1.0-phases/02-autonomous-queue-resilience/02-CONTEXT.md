# Phase 2: Autonomous Queue Resilience — Context & Decisions

## Executive Summary

Phase 2 transforms EstateX's background `/api/tick` engine from a single-pass, fail-once task executor into a production-grade, resilient queue. Actions that fail due to transient upstream network glitches (e.g. Twilio API rate limits, temporary Resend outages, or transient database blips) will automatically retry with exponential backoff rather than immediately dropping the lead or failing silently. Items that exhaust all retries are safely quarantined in a `DEAD_LETTER` queue with full audit context. Furthermore, lead-capture rate limiting is upgraded from an ephemeral in-process memory structure to a distributed, persistent MongoDB collection with TTL expiration.

---

## Locked Architectural Decisions

### D-01: Exponential Backoff & Retry State Transitions
- **Max Attempts**: Configurable via `MAX_SCHEDULED_ATTEMPTS` (default: 5).
- **Backoff Algorithm**:
  $$\text{delay\_seconds} = \min(\text{BACKOFF\_BASE\_SECONDS} \times 2^{\text{attempts} - 1}, \text{MAX\_BACKOFF\_SECONDS})$$
  Default `BACKOFF_BASE_SECONDS = 30` seconds, `MAX_BACKOFF_SECONDS = 3600` (1 hour).
- **State Flow**:
  - Initial insert: `state: "PENDING"`, `attempts: 0`, `run_at: <scheduled_time>`.
  - Claimed by tick: `state: "RUNNING"`, `started_at: <now_iso>`, `attempts: attempts + 1`.
  - On Execution Success: `state: "DONE"`, `finished_at: <now_iso>`, `error: None`.
  - On Transient Failure (`attempts < MAX_SCHEDULED_ATTEMPTS`):
    - `state: "PENDING"` (rescheduled for future tick execution).
    - `run_at: now() + timedelta(seconds=delay)`.
    - `last_error: str(e)`.
    - Audit event: `scheduled.retrying` with `attempt: N`, `next_run_at: ...`.
  - On Terminal Failure (`attempts >= MAX_SCHEDULED_ATTEMPTS`):
    - `state: "DEAD_LETTER"`.
    - `dead_lettered_at: <now_iso>`.
    - `last_error: str(e)`.
    - Audit event: `scheduled.dead_letter` with full diagnostic metadata.

### D-02: Dead-Letter Queue (DLQ) Inspection API
- Add `GET /api/queue/dead-letter` (protected by `require_admin`) allowing operators to inspect quarantined tasks, failure reasons, and lead associations.
- Add `POST /api/queue/dead-letter/:id/retry` allowing manual requeueing of quarantined actions back into `PENDING` state with reset attempt counter.

### D-03: Persistent MongoDB-Backed Rate Limiter
- Upgrade `rate_limit()` to be asynchronous: `await rate_limit(request, bucket="lead")`.
- Store rate-limit records in `db.rate_limits`:
  - Documents: `{"ip": ip, "bucket": bucket, "ts": datetime.now(timezone.utc), "expires_at": ...}`.
  - Query: Count documents for `(ip, bucket)` within the sliding window `[now - 60s, now]`.
  - Automatic cleanup: MongoDB TTL index on `expires_at` (expireAfterSeconds=0).
  - Robustness: Seamless fallback to in-memory sliding window if MongoDB collection is temporarily unreachable or in unit tests.

---

## Requirements Traceability

| Requirement | Description | Delivered in Plan |
|-------------|-------------|-------------------|
| **RESIL-01** | `scheduled_actions` runner implements exponential backoff retry loop for `FAILED` actions (`attempts < 5`) and parks terminal failures in `DEAD_LETTER` | `02-01-PLAN.md` |
| **RESIL-02** | Distributed rate limiting mechanism implemented in MongoDB to persist limits across restarts and multiple processes | `02-02-PLAN.md` |

---

## Test & Compatibility Guarantees
- Zero breakage to existing 74 unit/integration tests in `backend/tests/`.
- All tests continue to pass in `DEMO_MODE=1` without external network connections.
