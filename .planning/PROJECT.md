# EstateX — AI Real-Estate Lead Qualifier & Autonomous Orchestrator

## What This Is

EstateX is a full-stack real-estate lead automation platform that ingests inbound buyer/renter leads, contacts them within minutes using an AI voice assistant, qualifies them into structured criteria with an objective 0–100 rubric score, auto-books calendar appointments, and executes autonomous follow-up sequences. It combines a high-speed automation pipeline (v1) with a LangGraph-style multi-agent supervisor (v2) featuring persistent MongoDB checkpoints and human-in-the-loop escalation interrupts.

## Core Value

**The agent proposes, the state machine enforces.**
Probabilistic LLMs and voice agents handle conversational qualification, reasoning, and message drafting; deterministic Python code strictly enforces state transitions, rubric scoring, CRM synchronizations, calendar booking commits, quiet hours, and opt-outs.

## Business Context

- **Customer**: Real-estate brokerage teams, agents, and lead coordinators looking to eliminate response lag and qualify leads 24/7.
- **Revenue model**: B2B SaaS subscription per seat/brokerage with usage-based telephony and AI routing tiers.
- **Success metric**: Lead response time (< 5 minutes), qualification accuracy (> 90% agreement with manual broker rubrics), and booked tour conversion rate.
- **Strategy notes**: Live integrations must be honest and inspectable — every dashboard status chip accurately reflects live API health rather than silently masking failures with mocks.

## Requirements

### Validated

- [x] Inbound lead capture via REST API (`/api/lead`) with phone deduplication and IP rate limiting.
- [x] Google Ads Lead Form webhook integration (`/api/webhooks/google-leads`) with key authentication.
- [x] Outbound voice qualification pipeline (Vapi / mock) with `awaiting_transcript` hold state.
- [x] Webhook transcript ingestion (`/api/webhooks/vapi`) delivering end-of-call transcripts into qualification.
- [x] AI structured extraction via Groq LLM with deterministic 0–100 rubric scoring across 4 weighted dimensions.
- [x] Finite state machine (`NEW -> CALLING -> IN_CONVERSATION -> QUALIFIED|HOT|NURTURE -> BOOKED`) with append-only event auditing.
- [x] Calendar slot availability and appointment booking via Cal.com (502 on failure; no premature transition to `BOOKED`).
- [x] Email nurture via Resend and SMS follow-up via Twilio with centralized quiet-hours and `STOP` opt-out compliance.
- [x] V2 LangGraph supervisor engine (`agents/graph.py` + `agents/supervisor.py`) with `MongoCheckpointer`.
- [x] Human-in-the-loop approval interrupts (`escalate` -> `/approve` or `/reject`).
- [x] Autonomous background reconciliation worker (`/api/tick`) draining `scheduled_actions` and rescuing stranded calls.
- [x] **LIVE-01**: Live provider verification — Groq LLM, Cal.com API v2, Resend, and HubSpot CRM operating in LIVE mode with real API calls.
- [x] **AUTO-01**: Exponential backoff retry loop and Dead-Letter Queue (DLQ) for `scheduled_actions` in `/api/tick`.
- [x] **REFACTOR-01**: Modularized monolithic `server.py` into dedicated routers (`routes/`) and domain packages (`core/`), shrinking server entry point by ~90%.
- [x] **TEST-01**: Comprehensive frontend testing suite (Jest + RTL) covering Kanban pipeline, lead details, live provider chips, and API helpers.
- [x] **AUTH-01**: Full JWT authentication system with native bcrypt hashing (`routes/auth.py`), route guards (`ProtectedRoute.jsx`), and auto-seeded demo concierge.
- [x] **VOICE-03**: In-browser Web Speech API audio synthesis for turn-by-turn playback of qualification calls.
- [x] **TEST-02**: 138 total automated tests (82 pytest backend + 56 Jest frontend) passing 100% with zero flakes.

### Active (Next Milestone Goals)

- [ ] **DEPLOY-01**: Production deployment configuration for Render (Backend) and Vercel (Frontend) with GitHub Actions cron keep-alive.
- [ ] **EXPORT-01**: CSV/PDF lead audit report export for brokerage managers.
- [ ] **MULTI-01**: Multi-brokerage workspace isolation and role-based permissions (Broker Owner vs Lead Concierge).

### Out of Scope

- **Heavy Redis/Celery queue dependencies** — queue-less architecture via MongoDB `scheduled_actions` and FastAPI BackgroundTasks is optimal for cloud free tiers.
- **Replacing bespoke StateGraph with external heavy `langgraph` package** — current 139-line zero-dependency engine meets all requirements without dependency bloat.
- **Mobile native apps** — responsive React 19 web application serves mobile browser needs.

## Context

- **Codebase Map**: Documented in detail under `.planning/codebase/` (`STACK.md`, `ARCHITECTURE.md`, `STRUCTURE.md`, `CONVENTIONS.md`, `TESTING.md`, `INTEGRATIONS.md`, `CONCERNS.md`).
- **Provider Contract**: Managed centrally in `backend/providers.py` via `ProviderResult`. Any provider lacking keys falls back cleanly to mock without crashes.
- **Database**: Cloud MongoDB Atlas cluster (`cluster0.n8kxzlk.mongodb.net`, DB: `estatex`) with automatic compound indexes.
- **Test Suite**: 138 automated tests (82 pytest + 56 Jest), running in ~8 seconds total.

## Constraints

- **Security**: Destructive/expensive endpoints fail closed (HTTP 401) when `ADMIN_TOKEN` or JWT bearer token is missing or invalid.
- **Testing**: Zero-network test execution must remain true for the test suite (`backend/tests/conftest.py`).
- **Reliability**: A failed live booking must never mark a lead as `BOOKED`.
- **Telephony Gates**: Live voice calls and SMS gated by explicit flags (`VOICE_ENABLED=1`, `SMS_ENABLED=1`) to prevent billing accidents.

## Key Decisions

| Decision | Rationale | Outcome |
|:---|:---|:---|
| The agent proposes, state machine enforces | Prevents LLM hallucinations from corrupting business data, CRM states, or bookings | ✓ Good |
| Queue-less architecture (FastAPI BackgroundTasks + MongoDB `scheduled_actions`) | Eliminates Redis/Celery operational complexity on cloud free tiers | ✓ Good |
| Single qualification code path for mock & live | Ensures live webhook path cannot diverge or drift from local testing and demo logic | ✓ Good |
| In-memory Motor test double | Enables zero-install, zero-database local `pytest` testing for reviewers and CI | ✓ Good |
| Native bcrypt + PyJWT Bearer auth | Eliminates passlib 1.7.4 deprecation bugs on Python 3.14 while providing standard 7-day tokens | ✓ Good |
| In-browser Web Speech API audio synthesizer | Provides realistic call playback without requiring paid cellular phone carrier minutes | ✓ Good |

---
*Last updated: 2026-09-13 after v1.0 milestone completion*
