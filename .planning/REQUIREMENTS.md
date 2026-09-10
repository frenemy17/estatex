# Requirements: EstateX

**Defined:** 2026-09-09
**Core Value:** The agent proposes, the state machine enforces: fast, automated AI qualification and booking coupled with robust, inspectable, deterministic guardrails.

## Baseline Implemented Requirements

The following requirements represent existing verified capabilities synthesized from `docs/PRD.md` and codebase tests:

### Ingestion & Capture

- [x] **INGEST-01**: User can submit a lead via `POST /api/lead` with phone deduplication and per-IP rate limiting.
- [x] **INGEST-02**: Google Ads Lead Form webhook (`POST /api/webhooks/google-leads`) validates secret key and ingests contact fields.

### Voice & Qualification

- [x] **VOICE-01**: Voice provider initiates outbound calls and holds lead at `CALLING` with `awaiting_transcript=True` until transcript arrives.
- [x] **VOICE-02**: Inbound Vapi webhook (`POST /api/webhooks/vapi`) delivers real audio recording and transcript into `qualify_and_route`.
- [x] **QUAL-01**: LLM extracts structured qualification dimensions from transcript into typed JSON.
- [x] **QUAL-02**: Rubric calculator scores lead (0–100) across timeline, budget, pre-approval, and intent.
- [x] **QUAL-03**: State machine classifies and transitions lead into `HOT`, `QUALIFIED`, or `NURTURE` with event logging.

### Booking & Follow-up

- [x] **BOOK-01**: User can query real-time viewing slots on Cal.com via `GET /api/leads/:id/slots`.
- [x] **BOOK-02**: User can book property tour via `POST /api/leads/:id/book`, failing with 502 and withholding `BOOKED` status on provider error.
- [x] **NOTIF-01**: Outbound nurture email via Resend and follow-up SMS via Twilio enforce quiet hours (UTC).
- [x] **NOTIF-02**: Inbound Twilio SMS webhook (`POST /api/webhooks/twilio-sms`) processes `STOP` and marks lead as `opted_out`.

### Agentic Supervisor & Autonomy

- [x] **AGENT-01**: V2 LangGraph supervisor chooses `next_action` with persistent state across invocations via `MongoCheckpointer`.
- [x] **AGENT-02**: `escalate` action pauses execution with `{_interrupt: True}`; `/approve` or `/reject` resumes with operator decision.
- [x] **AUTO-01**: Autonomous `POST /api/tick` worker drains due `scheduled_actions` via atomic status claims.
- [x] **AUTO-02**: Autonomous tick worker rescues calls stranded past `CALL_TIMEOUT_MINUTES` and requalifies unscored leads.

---

## Active Milestone Requirements

Requirements for the current development cycle:

### Live Provider Production Readiness

- [x] **PROV-01**: Groq LLM integration reliably routes to active, supported models (`llama-3.3-70b-versatile`, `llama3-70b-8192`) with working credential validation.
- [x] **PROV-02**: Cal.com integration verified live with valid API key and event type ID, rendering green status chip and functional booking.
- [x] **PROV-03**: Resend email delivery verified with valid API key and working sender configuration.
- [x] **PROV-04**: Twilio SMS verified with verified destination phone numbers and inbound `STOP` test.
- [x] **PROV-05**: HubSpot CRM sync verified with valid access token, syncing contacts and associated deals.

### Autonomous Queue Resilience

- [x] **RESIL-01**: `scheduled_actions` runner implements exponential backoff retry loop for `FAILED` actions (`attempts < 5`).
- [x] **RESIL-02**: Distributed rate limiting mechanism implemented to replace single-process in-memory limiter.

### Architecture Refactoring

- [x] **MOD-01**: Split monolithic `backend/server.py` into modular route controllers (`routes/leads.py`, `routes/webhooks.py`, `routes/admin.py`, `routes/providers.py`).
- [x] **MOD-02**: Extract state machine and rubric scoring logic into `backend/core/`.

### Frontend Testing & Quality

- [x] **UI-01**: Establish React Testing Library component tests covering `Dashboard.jsx` (Kanban), `LeadDetail.jsx`, and `ProviderStatus.jsx`.

## Traceability Matrix

| Requirement | Phase | Status |
|:---|:---|:---|
| PROV-01 | Phase 1: Real Provider Live Readiness | Complete |
| PROV-02 | Phase 1: Real Provider Live Readiness | Complete |
| PROV-03 | Phase 1: Real Provider Live Readiness | Complete |
| PROV-04 | Phase 1: Real Provider Live Readiness | Complete |
| PROV-05 | Phase 1: Real Provider Live Readiness | Complete |
| RESIL-01 | Phase 2: Autonomous Queue Resilience | Complete |
| RESIL-02 | Phase 2: Autonomous Queue Resilience | Complete |
| MOD-01 | Phase 3: Monolithic Server Refactoring | Complete |
| MOD-02 | Phase 3: Monolithic Server Refactoring | Complete |
| UI-01 | Phase 4: Frontend Testing Suite | Complete |

---
*Requirements defined: 2026-09-09*
*Last updated: 2026-09-09 after docs ingestion*
