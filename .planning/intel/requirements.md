# Extracted Requirements

## REQ-lead-capture
- source: docs/PRD.md
- description: Public lead capture via REST API with deduplication by phone number and per-IP rate limiting, triggering asynchronous pipeline dispatch.
- acceptance:
  - Validates `name`, `phone`, `email` with Pydantic.
  - Returns existing lead without duplication if phone number matches.
  - Rejects abusive submissions with HTTP 429 when IP limit is exceeded.
- scope: lead ingestion, rate limiting, validation

## REQ-google-leads-webhook
- source: docs/PRD.md
- description: Google Ads Lead Form webhook integration supporting standard and test lead payloads.
- acceptance:
  - Verifies key against `GOOGLE_LEADS_WEBHOOK_KEY`.
  - Returns 503 while key is unset; returns 401 on key mismatch.
  - Parses `FULL_NAME`/`EMAIL`/`PHONE_NUMBER` with `FIRST_NAME`/`LAST_NAME` fallback.
  - Idempotent on provider lead ID using `db.webhook_receipts`.
- scope: lead ingestion, Google Ads, webhooks

## REQ-voice-telephony
- source: docs/PRD.md
- description: Outbound AI telephony integration via Vapi with webhook-driven transcript delivery.
- acceptance:
  - Initiates outbound call when `VOICE_ENABLED=1` and credentials exist.
  - A live call with no transcript parks lead at `CALLING` with `awaiting_transcript=True`.
  - `POST /api/webhooks/vapi` receives `end-of-call-report`, saves audio/transcript, and dispatches qualification.
- scope: telephony, Vapi, voice agent, transcripts

## REQ-ai-qualification
- source: docs/PRD.md
- description: AI structured extraction and deterministic rubric qualification scoring (0–100).
- acceptance:
  - Groq LLM extracts timeline, budget, pre-approval, and preferences into structured JSON.
  - Deterministic rubric computes 0–100 integer score across four weighted dimensions.
  - Classifies lead into `HOT` (≥85), `QUALIFIED` (60–84), or `NURTURE` (<60).
- scope: AI extraction, rubric scoring, lead classification

## REQ-state-machine
- source: docs/PRD.md
- description: Guarded lead lifecycle state machine with append-only event auditing.
- acceptance:
  - Enforces legal transitions (`NEW -> CALLING -> IN_CONVERSATION -> QUALIFIED|HOT|NURTURE -> BOOKED`).
  - Rejects illegal transitions with error.
  - Every transition writes an event row to `events` with timestamp and correlation ID.
- scope: state machine, audit log, data integrity

## REQ-calendar-booking
- source: docs/PRD.md
- description: Calendar slot availability querying and viewing appointment booking via Cal.com.
- acceptance:
  - `GET /api/leads/:id/slots` fetches live available booking slots.
  - `POST /api/leads/:id/book` commits booking to Cal.com.
  - Returns HTTP 502 on provider booking failure and does NOT advance lead to `BOOKED`.
- scope: calendar booking, Cal.com, appointments

## REQ-notifications
- source: docs/PRD.md
- description: Nurture email and SMS notifications with centralized opt-out and quiet-hours policies.
- acceptance:
  - Dispatches email via Resend and SMS via Twilio.
  - Respects quiet hours (UTC); holds messages by creating `scheduled_actions` rows.
  - Inbound SMS `STOP`/`UNSUBSCRIBE` sets `opted_out=True` and halts all future messaging.
- scope: notifications, Resend, Twilio, quiet hours, compliance

## REQ-agent-supervisor
- source: docs/PRD.md
- description: V2 LangGraph-style multi-agent supervisor orchestrating lead next-best-actions with persistent state.
- acceptance:
  - Supervisor node selects `next_action ∈ {call, enrich, follow_up, escalate, wait, done}` with LLM reasoning and rule-based fallback.
  - Specialized sub-agents for enrichment and contextual follow-up drafting.
  - State persisted across sessions in MongoDB `graph_checkpoints` keyed by `lead_id`.
- scope: agentic supervisor, LangGraph, checkpoints, sub-agents

## REQ-human-in-the-loop
- source: docs/PRD.md
- description: Execution interrupt for high-value or ambiguous leads requiring human approval.
- acceptance:
  - `escalate` action sets `{_interrupt: True}` and pauses graph execution.
  - `/api/leads/:id/approve` or `/reject` resumes execution with approval decision in state.
- scope: human-in-the-loop, approvals, escalation

## REQ-autonomy-tick
- source: docs/PRD.md
- description: Autonomous reconciliation worker draining queued actions, rescuing stuck calls, and requalifying leads.
- acceptance:
  - `POST /api/tick` claims due tasks atomically via `PENDING -> RUNNING` updates.
  - Rescues leads stranded in `CALLING` past `CALL_TIMEOUT_MINUTES`.
  - Requalifies leads with arrived transcripts that missed scoring.
  - Scheduled via 10-minute GitHub Actions workflow or cron.
- scope: autonomy, scheduled actions, tick worker, reconciliation

## REQ-backlog-exponential-retries
- source: docs/PRD.md
- description: Exponential backoff retry loop for failed scheduled actions.
- acceptance:
  - Failed actions increment `attempts` counter.
  - Automatically recalculate `run_at` with exponential backoff up to max attempts.
- scope: backlog, resilience, retry policy

## REQ-backlog-modularize-server
- source: docs/PRD.md
- description: Split monolithic `server.py` into decoupled routers and domain modules.
- acceptance:
  - Extract endpoints into `routes/leads.py`, `routes/webhooks.py`, `routes/admin.py`.
  - Extract domain logic into state machine, scoring, and tick worker modules.
- scope: backlog, refactoring, code structure
