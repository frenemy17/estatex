---
last_mapped_commit: 722da52125826f52cb0781fbfb78ec823fc64055
---

# Codebase Concerns

**Analysis Date:** 2026-09-09

## Tech Debt

**Monolithic Backend Entry Point (`backend/server.py`):**
- **Issue:** `server.py` spans 1,904 lines, containing Pydantic schemas, route definitions, deterministic state transition logic, rubric scoring calculators, autonomous tick worker loops, simulation fixtures, and helper methods in a single file.
- **Why:** Rapid initial prototype iteration prioritized single-file co-location.
- **Impact:** High cognitive load, merge conflict risks, and tight coupling between transport endpoints and domain business logic.
- **Fix approach:** Modularize into FastAPI routers (`api/routers/leads.py`, `api/routers/webhooks.py`, `api/routers/admin.py`) and extract domain logic into `core/state_machine.py`, `core/scoring.py`, and `workers/tick.py`.

**In-Memory IP Rate Limiter (`backend/server.py`):**
- **Issue:** Inbound public lead submission rate limiting is stored in an in-memory dictionary (`_rate_limiter`).
- **Why:** Avoided introducing external dependency on Redis.
- **Impact:** Does not persist across server restarts and cannot enforce shared limits across multiple Uvicorn worker processes or horizontally scaled container instances.
- **Fix approach:** Migrate rate limiting state to MongoDB with TTL indexes or integrate Redis/Upstash.

**Bespoke StateGraph Engine (`backend/agents/graph.py`):**
- **Issue:** Bespoke 139-line LangGraph micro-engine implements a custom subset of graph execution.
- **Why:** Kept installation lightweight with zero extra pip dependencies.
- **Impact:** Lacks full LangGraph ecosystem features like streaming tokens, complex nested subgraphs, and native trace visualization.
- **Fix approach:** Evaluate adopting official `langgraph` if advanced multi-agent capabilities are required, or keep the micro-engine if simplicity and zero dependency overhead remain primary.

**Zero Frontend Test Coverage (`frontend/`):**
- **Issue:** `frontend/src/` has no automated unit, integration, or snapshot tests despite having Jest configured via `craco test`.
- **Why:** Development focused on backend reliability and visual polish.
- **Impact:** UI regressions on state changes, polling hooks, or Kanban drag-and-drop must be caught via manual verification.
- **Fix approach:** Add Vitest or Jest React Testing Library suites for critical components (`LeadDetail.jsx`, `Dashboard.jsx`, `api.js`).

## Known Issues & Integration Fragilities

**External Provider Model Deprecations (Groq / LLMs):**
- **Symptoms:** LLM calls fail with model retirement or missing model errors (e.g. decommission of older checkpoint names on Groq).
- **Trigger:** Groq updating model versions or removing deprecated endpoints.
- **Workaround:** Dynamic fallback list implemented in `providers.py` (`llama-3.3-70b-versatile`, `llama3-70b-8192`, Google Gemini fallback).
- **Fix approach:** Parameterize model names via environment variables (`GROQ_MODEL=...`) with automated capability health checks.

**Third-Party Trial & Account Constraints:**
- **Twilio SMS:** Trial accounts require recipient number verification and US numbers require A2P 10DLC registration. `SMS_ENABLED=1` gate prevents silent billing/deliverability failures.
- **Vapi Voice:** Outbound calls require an active paid account balance and configured SIP/phone number IDs. Gated by `VOICE_ENABLED=1`.
- **Resend Email:** Free accounts require `onboarding@resend.dev` sender until custom domains pass DNS DKIM/SPF verification.
- **Cal.com API:** Expired API keys or changed event IDs return HTTP 502 on booking attempts. The state machine correctly halts and leaves the lead unbooked.

**Scheduled Actions Retry Policy:**
- **Symptoms:** Actions that encounter persistent external failures remain in state `FAILED` indefinitely.
- **Trigger:** Upstream network outage or invalid API credentials during scheduled tick.
- **Workaround:** Manual inspection of `db.scheduled_actions`.
- **Fix approach:** Implement exponential backoff with a max retry counter (`attempts < 5`) in the `/api/tick` worker loop (P1 on PRD backlog).

## Security Considerations

**Single-Tenant Admin Authentication:**
- **Risk:** Access to administrative and destructive endpoints (`/api/seed`, `/api/simulate`, `/api/tick`, `/api/reset`) is guarded by a single global `ADMIN_TOKEN`.
- **Current Mitigation:** Uses constant-time string comparison (`secrets.compare_digest`) and fails closed (401) when unset.
- **Recommendations:** Implement multi-tenant authentication with per-agency role-based access control (RBAC) if offering true multi-tenant SaaS.

**Webhook Authenticity Verification:**
- **Twilio Webhook:** Inbound SMS handler deduplicates via message SID in `db.webhook_receipts`, but does not currently compute and verify Twilio's HMAC-SHA1 `X-Twilio-Signature`.
- **Recommendation:** Add `RequestValidator` cryptographic check using `TWILIO_AUTH_TOKEN`.

**CORS Default Policy:**
- **Risk:** Defaults to `*` if `CORS_ORIGINS` is unset in production.
- **Recommendation:** Enforce explicit origin matching on production domains.

## Performance & Scalability

**Dashboard Polling Overhead:**
- **Problem:** Frontend relies on client-side HTTP polling (`usePoll.js`) every few seconds to refresh lead status.
- **Impact:** High numbers of concurrent dashboard tabs generate redundant read load against MongoDB.
- **Improvement Path:** Replace polling with Server-Sent Events (SSE) or WebSockets streamed from MongoDB Change Streams.

**Unbounded Database Cursor Projections:**
- **Problem:** Several queries in `server.py` fetch lists with high limits (e.g. `to_list(200)`).
- **Improvement Path:** Implement cursor pagination with indexed `created_at` or `_id` filters for large lead archives.

---

*Concerns analysis: 2026-09-09*
*Update after resolving technical debt or discovering new risks*
