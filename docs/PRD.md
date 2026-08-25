# EstateX — PRD

## Problem
Real-estate leads go cold in minutes; the first responder wins. Humans can't call every lead
instantly, 24/7, and qualify consistently. This platform ingests leads → an AI calls and
qualifies in seconds → auto-books → follows up on its own schedule → shows everything,
including its own failures, on a dashboard.

## Stack
- Backend: FastAPI + Motor (MongoDB). No Redis, no Celery — `BackgroundTasks` for the fast
  path, a `scheduled_actions` collection plus a cron-driven `/api/tick` for the slow path.
- LLM: Groq `llama-3.3-70b-versatile` (optional Google AI Studio fallback, lazily imported).
- Agent layer: bespoke LangGraph-style `StateGraph` + `MongoCheckpointer` (139 lines).
- Frontend: React 19 + Tailwind + shadcn/ui + Recharts + Phosphor icons.
- Hosting: Render (always-on backend) + Vercel (static SPA).

## Personas
- Real-estate broker/team lead: monitors the pipeline, approves escalations, reviews AI
  qualifications, sees which integrations are live and which are mocked.
- End buyer/renter: fills the capture form OR submits a Google Ads Lead Form.

## Design rule
The agent proposes, the state machine enforces. The LLM extracts fields and picks next
actions; scoring, transitions, CRM writes and booking commits are deterministic code.

## What's implemented — 2026-08-25

### v1 — automation
- `POST /api/lead` — dedupe by phone, per-IP rate limit, background pipeline dispatch.
- `POST /api/webhooks/google-leads` — Google Ads Lead Form Extensions, key-verified
  (503 while `GOOGLE_LEADS_WEBHOOK_KEY` is unset), `FULL_NAME`/`EMAIL`/`PHONE_NUMBER` with
  `FIRST_NAME`/`LAST_NAME` fallback, `is_test` flag.
- `POST /api/webhooks/vapi` — `end-of-call-report` delivers the real transcript into
  `qualify_and_route()`, the same code path the mock pipeline uses.
- `POST /api/webhooks/twilio-sms` — inbound SMS; `STOP`/`UNSUBSCRIBE` sets `opted_out`.
  Returns TwiML. Both webhooks are idempotent on the provider's message id
  (`db.webhook_receipts`).
- Pipeline: voice call → transcript → LLM extraction → deterministic rubric score →
  classify → CRM sync → follow-up. A live call with no transcript yet parks the lead at
  `CALLING` with `awaiting_transcript`; qualification never runs on an empty transcript.
- State machine (`NEW → CALLING → IN_CONVERSATION → QUALIFIED|HOT|NURTURE → BOOKED`) with a
  legal-transitions guardrail and an append-only event log carrying a correlation id.
- Providers in `providers.py` behind `PROVIDER_SPECS`: Voice (Vapi), Booking (Cal.com),
  Notification (Resend, Twilio), CRM (HubSpot). Mode is derived from env vars, not
  hardcoded. Every call returns a `ProviderResult` recorded in `db.provider_health` — a
  failed live call is never reported as a success, and a mock fallback is recorded as its
  own separate result.
- Booking calls the provider first and only transitions to `BOOKED` on success; a Cal.com
  failure returns 502 and writes no appointment.
- Notifications: quiet hours (configurable, UTC) and opt-out enforced in one place;
  a deferred send becomes a `scheduled_actions` row rather than a logged intention.
- Per-lead correlation-id logging.
- Simulation harness (15 scripted leads) + `GET /api/eval`
  (`rubric_agreement`, `booking_rate`, `hallucination_rate`, `baseline_only`).
- 69 offline pytest tests — no server, no database, no network.

### v2 — agentic
- `StateGraph` engine (`agents/graph.py`): `add_node`, `add_edge`, `add_conditional_edges`,
  `compile`, `ainvoke`.
- `MongoCheckpointer` — state persisted per `lead_id`, so the agent has memory across days.
- Supervisor node — the LLM picks `next_action ∈ {call, enrich, follow_up, escalate, wait,
  done}` with reasoning; a deterministic rule-based fallback runs when no LLM is configured.
- Sub-agents: `enrichment_agent` (area brief + hook), `followup_agent` (drafts
  channel/tone/subject/body/defer_hours, delegates sending to the notification provider).
- Human-in-the-loop interrupt: `escalate` pauses the graph; `/approve` or `/reject` resumes
  it with the decision in state. Frontend approval banner + buttons.
- V1 vs V2 side-by-side comparison view.

### Autonomy
- `db.scheduled_actions` = `{lead_id, kind, run_at, payload, state, attempts, error}` is the
  single queue for everything deferred: the supervisor's `wait`, a quiet-hours hold, a retry.
- `POST /api/tick` (admin-only) drains what is due, rescues leads stranded in `CALLING` past
  `CALL_TIMEOUT_MINUTES`, requalifies leads whose transcript arrived but never scored, and
  returns a summary of what it did. Rows are claimed with a conditional `PENDING → RUNNING`
  update, so overlapping ticks cannot double-run one action.
- `.github/workflows/tick.yml` calls it every 10 minutes, which doubles as the keep-warm
  ping for the free-tier backend.

### Security
- `require_admin()` on `/api/seed`, `/api/simulate`, `/api/leads/bulk`, `/api/tick` and
  `DELETE /api/reset`. Fails closed: 401 when `ADMIN_TOKEN` is unset, compared with
  `secrets.compare_digest`.
- The public deploy is read-only — browsing needs no token; write actions are visibly
  disabled with a tooltip until one is entered.
- Per-IP rate limit on the public capture form. No import-time crash on a missing
  `MONGO_URL`: `GET /api/health` reports it instead.

## Backlog
- P1: retry with exponential backoff for `FAILED` scheduled actions (today they are recorded
  and left for inspection).
- P2: distributed rate limiting — the current limiter is per-process and in-memory.
- P2: schema version on checkpoints (per code review).
- P2: split `server.py` into modules (1,904 lines; the provider layer has already moved out
  to `providers.py`).
- P2: swap the 139-line micro-engine for the real `langgraph` dependency, if the extra
  surface earns its keep.
- P3: multi-tenant auth — one admin token today, no per-agency isolation.
- P3: replace dashboard polling with SSE.

## Done, previously on this list
Real Vapi / Cal.com / HubSpot / Twilio / Resend integrations (env keys only, no code
change); the "next check" scheduler; admin auth.
