# Phase 1: Real Provider Live Readiness - Context

**Gathered:** 2026-09-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Eliminate mock fallbacks and paywall friction to make EstateX operate as a genuine, live SaaS real-estate platform. Specifically:
1. Replace the paid Vapi voice paywall with an open-source/native **Twilio Voice + Groq LLM** interactive outbound phone agent that calls leads, conducts real-estate qualification conversations, records real transcripts, and routes them into the qualification state machine.
2. Verify live connectivity and credentials for **Groq LLM** (active model routing), **Cal.com** (live appointment booking), **Resend** (live email delivery), **Twilio SMS** (outbound text notifications and inbound STOP compliance), and **HubSpot** (contact and deal CRM sync).
3. Ensure every provider chip on the dashboard reflects true LIVE operational health.

</domain>

<decisions>
## Implementation Decisions

### Voice Telephony & Paywall Removal
- **D-01:** Replace the proprietary Vapi dependency with direct **Twilio Voice + Groq LLM TwiML Speech Pipeline**.
  - **Mechanism:** `VoiceProvider.start_call()` uses Twilio's REST API (`/2010-04-01/Accounts/{sid}/Calls.json`) to place a real outbound call to the lead's phone number.
  - **Interactive Speech Turn Loop:** When the lead answers, Twilio requests TwiML from FastAPI (`POST /api/voice/twiml`). Twilio uses Polly TTS to speak and `<Gather input="speech">` to capture the lead's spoken words.
  - **Conversational Intelligence:** Spoken responses post to `POST /api/voice/gather`. Groq LLM generates real-time real-estate agent dialogue, systematically asking about purchasing timeline, budget, mortgage pre-approval status, and target neighbourhoods.
  - **Transcript Handoff:** At the conclusion of the call, the complete multi-turn transcript is saved on the lead and automatically passed to `qualify_and_route(lead_id)`.
  - **Reversibility:** costly — changes voice call provider signature in `backend/providers.py` and adds Twilio voice webhook routes in `backend/server.py`.

### Provider Integrity & Honest Reporting
- **D-02:** Strict honest reporting policy across all providers.
  - No silent fallbacks: when live credentials are provided and an API call fails, report the actual HTTP status code and error string in `ProviderResult`.
  - Failed calendar bookings return HTTP 502 and strictly refuse to transition the lead to `BOOKED` status.
  - All outcomes are recorded in `db.provider_health` for dashboard audit visibility.
  - **Reversibility:** reversible — aligns with existing architecture invariant in `backend/providers.py`.

### Scheduling & Email Delivery
- **D-03:** Cal.com integration configured with active API key and event type ID.
- **D-04:** Resend integration configured to deliver real emails to verified developer addresses using `onboarding@resend.dev` or custom domain.

### CRM Synchronization
- **D-05:** HubSpot integration syncs contacts (idempotent on email) and creates associated deal records in the real-estate pipeline.

### Agent Discretion
- Exact prompt engineering and turn limit (3–5 conversational turns) for the Twilio speech qualification loop.
- Choice of Polly neural voice (e.g. `Polly.Joanna` or `Polly.Matthew`) for natural telephony audio.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Integration & Architecture
- `.planning/codebase/INTEGRATIONS.md` — Provider contracts, credentials, and webhook endpoints
- `.planning/codebase/STACK.md` — Runtimes, Python dependencies, and environment keys
- `.planning/codebase/CONCERNS.md` — Known provider fragilities, trial limitations, and model deprecation risks
- `docs/PRD.md` §What's implemented — Qualification rubric, state machine rules, and webhook receipt idempotency

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/providers.py`: `ProviderResult`, `is_live()`, `demo_mode()`, `PROVIDER_SPECS`.
- `backend/server.py`: `qualify_and_route(lead_id)` — single unified entry point that processes call transcripts and triggers rubric scoring.
- `backend/server.py`: `db.webhook_receipts` — collection ensuring webhook calls are processed idempotently.

### Integration Points
- `VoiceProvider.start_call()` in `backend/providers.py`: update to trigger Twilio outbound call.
- `backend/server.py`: add `/api/voice/twiml` and `/api/voice/gather` to drive the interactive phone call loop.
- `frontend/src/components/ProviderStatus.jsx`: reflect Twilio Voice and external service statuses.

</code_context>

<specifics>
## Specific Ideas

- Outbound phone calls must ring real phones and conduct an interactive dialogue, eliminating Vapi paywalls by utilizing Twilio Voice + Groq LLM.
- At the end of the call, the qualification rubric (0–100) must score the lead based on the real conversation transcript.

</specifics>

<deferred>
## Deferred Ideas

- In-browser WebRTC mic agent (future enhancement for web-only leads).
- Multi-agent LangGraph streaming over Twilio Media Streams WebSockets (Phase 3+).

</deferred>

---

*Phase: 1-Real Provider Live Readiness*
*Context gathered: 2026-09-09*
