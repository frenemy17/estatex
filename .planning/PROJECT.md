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
- [x] Zero-dependency offline pytest test harness (69 passing tests with in-memory Motor double).

### Active

- [ ] **LIVE-01**: Live provider verification — ensure all external SaaS integrations (Groq, Cal.com, Resend, Twilio, HubSpot) operate in LIVE mode with verified credentials.
- [ ] **AUTO-01**: Exponential backoff retry loop for `FAILED` scheduled actions (PRD Backlog P1).
- [ ] **REFACTOR-01**: Modularize monolithic `server.py` (1,904 lines) into decoupled routers and domain services (PRD Backlog P2).
- [ ] **TEST-01**: Automated frontend testing suite for React components, Kanban board, and API client.

### Out of Scope

- **Distributed multi-tenant billing & organization isolation** — single-tenant admin token model suffices for current production deployment.
- **Replacing bespoke StateGraph with full heavy `langgraph` package** — current 139-line zero-dependency engine meets all requirements without dependency bloat.
- **Mobile native apps** — responsive React 19 web application serves mobile browser needs.

## Context

- **Codebase Map**: Documented in detail under `.planning/codebase/` (`STACK.md`, `ARCHITECTURE.md`, `STRUCTURE.md`, `CONVENTIONS.md`, `TESTING.md`, `INTEGRATIONS.md`, `CONCERNS.md`).
- **Provider Contract**: Managed centrally in `backend/providers.py` via `ProviderResult`. Any provider lacking keys or in `DEMO_MODE=1` falls back cleanly to mock without crashes.
- **Database**: MongoDB with Motor async driver. No Redis or Celery dependencies.

## Constraints

- **Security**: Destructive/expensive endpoints fail closed (HTTP 401) when `ADMIN_TOKEN` is unset or mismatched (`secrets.compare_digest`).
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

---
*Last updated: 2026-09-09 after docs ingestion from docs/PRD.md*
