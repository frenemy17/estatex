# Roadmap: EstateX

## Overview

EstateX has a complete, working, offline-tested baseline (v1 automation pipeline + v2 LangGraph supervisor). This roadmap drives the platform from an offline demo to a rock-solid, production-grade SaaS system: first verifying live external integrations with honest reporting, then hardening background autonomy with exponential backoff retries, refactoring the 1,900-line server monolith into clean modular domain packages, and introducing automated frontend test coverage.

## Phases

- [ ] **Phase 1: Real Provider Live Readiness** — Verify and configure live credentials for Groq, Cal.com, Resend, Twilio, and HubSpot so every status chip is green and real API calls execute.
- [ ] **Phase 2: Autonomous Queue Resilience** — Implement exponential backoff retries for failed scheduled actions and replace in-memory rate limiting with a persistent store.
- [ ] **Phase 3: Monolithic Server Refactoring** — Modularize `backend/server.py` into dedicated FastAPI routers and domain services while preserving 100% offline test passes.
- [ ] **Phase 4: Frontend Testing Suite** — Author automated unit and component tests for React components, Kanban board, and client API layers.

---

## Phase Details

### Phase 1: Real Provider Live Readiness
**Goal**: Transition from mock fallbacks to genuinely live SaaS integrations with active credentials, accurate status chips, and real outbound calls/emails/SMS/calendar bookings.
**Depends on**: Nothing (first milestone phase)
**Requirements**: PROV-01, PROV-02, PROV-03, PROV-04, PROV-05
**Success Criteria** (what must be TRUE):
  1. Groq LLM queries succeed against supported live models (`llama-3.3-70b-versatile` / `llama3-70b-8192`) and produce structured qualification data.
  2. Cal.com integration fetches real booking slots and successfully creates appointments on live calendars.
  3. Resend dispatches live emails to verified developer addresses without delivery failures.
  4. Twilio SMS sends live notifications to verified numbers and inbound `STOP` webhook correctly opts out contacts.
  5. `GET /api/providers` reports live status (`mode="LIVE"`, `ok=true`) for all configured services.
**Plans**: 2 plans

Plans:
- [ ] 01-01: Environment key validation and provider connectivity tests across Groq, Cal.com, Resend, Twilio, and HubSpot.
- [ ] 01-02: End-to-end live flow verification through real lead capture, qualification, appointment booking, and CRM deal creation.

---

### Phase 2: Autonomous Queue Resilience
**Goal**: Elevate the background `/api/tick` engine from simple single-pass execution to a resilient, fault-tolerant autonomous queue with automated retries.
**Depends on**: Phase 1
**Requirements**: RESIL-01, RESIL-02
**Success Criteria** (what must be TRUE):
  1. Any action in `db.scheduled_actions` that fails upstream transitions to `FAILED` with an incremented `attempts` counter and recalculated exponential `run_at` timestamp.
  2. Tasks reaching maximum attempts (e.g. 5) are parked in `DEAD_LETTER` with root-cause error logging.
  3. Lead capture rate limiting persists across server restarts and enforces limits uniformly.
**Plans**: 2 plans

Plans:
- [ ] 02-01: Implement exponential backoff retry scheduling and dead-letter queue semantics in `/api/tick`.
- [ ] 02-02: Implement persistent MongoDB-backed rate limiter with TTL indexes.

---

### Phase 3: Monolithic Server Refactoring
**Goal**: Deconstruct `backend/server.py` (1,904 lines) into clean, maintainable, single-responsibility FastAPI routers and domain modules without altering API contracts.
**Depends on**: Phase 2
**Requirements**: MOD-01, MOD-02
**Success Criteria** (what must be TRUE):
  1. `server.py` is reduced to an assembly shell (< 200 lines) mounting modular routers.
  2. Route controllers are separated into `backend/routes/` (`leads.py`, `webhooks.py`, `admin.py`, `providers.py`).
  3. Business domain logic is separated into `backend/core/` (`state_machine.py`, `scoring.py`, `tick.py`).
  4. All 69 offline tests in `backend/tests/` continue to pass without modification.
**Plans**: 2 plans

Plans:
- [ ] 03-01: Extract domain logic (state machine invariants, rubric scoring, tick reconciliation) into `backend/core/`.
- [ ] 03-02: Extract endpoint handlers into `backend/routes/` and rewire `server.py` with FastAPI router includes.

---

### Phase 4: Frontend Testing Suite
**Goal**: Establish comprehensive client-side automated test coverage for the React 19 application.
**Depends on**: Phase 3
**Requirements**: UI-01
**Success Criteria** (what must be TRUE):
  1. `npm test` runs in CI and locally via Craco/Jest, verifying core frontend components.
  2. Test suites cover `Dashboard.jsx` (Kanban column rendering, lead drag/drop, filters).
  3. Test suites cover `LeadDetail.jsx` (rubric scoring display, audio player, admin action triggers).
  4. Test suites cover `api.js` (auth header injection, token prompt on 401).
**Plans**: 2 plans

Plans:
- [ ] 04-01: Setup React Testing Library test harness and mock handlers for API endpoints.
- [ ] 04-02: Implement component test suites for `Dashboard`, `LeadDetail`, and `ProviderStatus`.

---
*Roadmap defined: 2026-09-09*
*Last updated: 2026-09-09 after docs ingestion*
