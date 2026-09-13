# Extracted Technical Constraints

## Zero-Dependency Offline Pytest Harness
- source: docs/PRD.md
- type: nfr
- content:
  Reviewers must be able to clone and run `pytest` offline with zero server running, zero external database, and zero network calls. All database interaction is substituted with an in-memory double in `backend/tests/conftest.py`.

## Provider Capability Contract
- source: docs/PRD.md
- type: api-contract
- content:
  Every provider in `providers.py` must return a `ProviderResult`. Missing keys or `DEMO_MODE=1` returns a mock result (`mode="MOCK", ok=True`). Real keys return actual live status. Failed live calls must report the genuine HTTP error and status, never claiming a false success.

## Webhook Signature & Deduplication Idempotency
- source: docs/PRD.md
- type: protocol
- content:
  All webhooks (Google Leads, Vapi, Twilio) must be idempotent against provider message IDs stored in `db.webhook_receipts`. Duplicate deliveries must be acknowledged without duplicate state mutations.

## Single Queue for Deferred Work
- source: docs/PRD.md
- type: schema
- content:
  `db.scheduled_actions` is the single queue schema for everything deferred: `{lead_id, kind, run_at, payload, state, attempts, error}`. Row claims must be atomic via conditional `PENDING -> RUNNING` updates to prevent race conditions during tick sweeps.
