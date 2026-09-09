---
last_mapped_commit: 722da52125826f52cb0781fbfb78ec823fc64055
---

# External Integrations

**Analysis Date:** 2026-09-09

## APIs & External Services

Every provider integration in EstateX adheres to a strict contract defined in `backend/providers.py`:
- Missing credentials or `DEMO_MODE=1` triggers deterministic, safe **MOCK** responses (`ProviderResult(mode="MOCK", ok=True)`).
- Valid credentials trigger real **LIVE** HTTP calls via `requests` executed inside worker threads. Live failures return actual status codes and error details; they are never quietly masked as successes.
- Provider state is exposed to the frontend via `GET /api/providers` and rendered as real-time health chips (`frontend/src/components/ProviderStatus.jsx`).

### LLM & Intelligence
- **Groq API** (`backend/providers.py`):
  - **Purpose:** Structured lead qualification extraction, rubric evaluation, and autonomous supervisor agent reasoning.
  - **SDK/Client:** Direct HTTP REST calls to `https://api.groq.com/openai/v1/chat/completions` using JSON mode (`response_format: {"type": "json_object"}`).
  - **Auth:** Bearer token in `GROQ_API_KEY`.
  - **Models:** Primary `llama-3.3-70b-versatile`, with fallbacks to `llama3-70b-8192` and Google Gemini.
  - **Fallback:** Rule-based keyword extraction and deterministic state machine logic when LLM credentials are unset.
- **Google Generative AI (Optional Fallback)**:
  - **Purpose:** Secondary LLM fallback if a Google AI Studio key is provided.
  - **SDK:** `google-generativeai` package.

### Voice & Telephony
- **Vapi Voice AI** (`backend/providers.py`, `backend/server.py`):
  - **Purpose:** Autonomous outbound telephony calls to newly ingested real-estate leads.
  - **SDK/Client:** Direct REST requests to `https://api.vapi.ai/call/phone`.
  - **Auth:** Bearer token via `VAPI_API_KEY`, sending assistant configuration `VAPI_ASSISTANT_ID` and outbound number `VAPI_PHONE_NUMBER_ID`.
  - **Safety Gate:** Gated by `VOICE_ENABLED=1` environment variable to prevent unexpected billing.
  - **Webhook Endpoint:** `POST /api/webhooks/vapi` receives `end-of-call-report` payloads containing full audio recordings and conversation transcripts. Validated via `x-vapi-secret` header matching `VAPI_WEBHOOK_SECRET`.

### Calendar & Scheduling
- **Cal.com** (`backend/providers.py`, `backend/server.py`):
  - **Purpose:** Query real-time availability slots and commit buyer property viewing appointments.
  - **Endpoints Used:**
    - Slot Availability: `GET https://api.cal.com/v1/slots` or `GET https://api.cal.com/v2/slots/available` with `apiKey` and `eventTypeId`.
    - Booking Commit: `POST https://api.cal.com/v1/bookings` or `POST https://api.cal.com/v2/bookings`.
  - **Auth:** `CAL_API_KEY` and target event configuration `CAL_EVENT_TYPE_ID`.
  - **Strict Failure Handling:** If a live booking fails, the backend returns HTTP 502 Bad Gateway and refuses to advance the lead state to `BOOKED`.

### Messaging & Notifications
- **Resend Email** (`backend/providers.py`):
  - **Purpose:** Outbound buyer nurture sequences, property briefs, and calendar appointment confirmations.
  - **SDK/Client:** REST API `POST https://api.resend.com/emails`.
  - **Auth:** Bearer token via `RESEND_API_KEY`.
  - **Routing Policy:** `FROM_EMAIL` (defaulting to `onboarding@resend.dev` for test domains). `DEMO_EMAIL` redirects messages to developer inbox when demo/sample leads are processed.
- **Twilio SMS** (`backend/providers.py`, `backend/server.py`):
  - **Purpose:** Fast follow-up SMS text messaging and two-way compliance handling.
  - **SDK/Client:** REST requests to `https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json`.
  - **Auth:** Basic Auth with `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`.
  - **Safety Gate:** Gated by `SMS_ENABLED=1`.
  - **Webhook Endpoint:** `POST /api/webhooks/twilio-sms` processes inbound SMS messages. If a recipient replies with `STOP` or `UNSUBSCRIBE`, the backend sets `opted_out: True` on the lead record and responds with standard TwiML XML.

### CRM Synchronization
- **HubSpot** (`backend/providers.py`):
  - **Purpose:** Real-estate buyer contact creation, profile property enrichment, and deal association.
  - **Endpoints Used:**
    - Contact Upsert: `POST https://api.hubapi.com/crm/v3/objects/contacts` (idempotent on email).
    - Deal Association: `POST https://api.hubapi.com/crm/v3/objects/deals`.
  - **Auth:** Private App token in `HUBSPOT_ACCESS_TOKEN` with `crm.objects.contacts.write` and `crm.objects.deals.write` scopes.

### Ingestion Webhooks
- **Google Ads Lead Form Extensions** (`backend/server.py`):
  - **Endpoint:** `POST /api/webhooks/google-leads`.
  - **Auth:** Secret key validation via query parameter or header against `GOOGLE_LEADS_WEBHOOK_KEY`. Returns 503 if unconfigured; 401 on key mismatch.
  - **Payload Handling:** Maps Google column ids (`FULL_NAME`, `EMAIL`, `PHONE_NUMBER`, with `FIRST_NAME`/`LAST_NAME` fallbacks) into the standard EstateX lead schema.

## Data Storage

### Database
- **MongoDB** (`backend/server.py`, `backend/agents/graph.py`):
  - **Connection:** Managed via Motor async client (`MONGO_URL`, `DB_NAME`).
  - **Collections:**
    - `leads`: Core entity records including buyer status, score, qualification breakdown, contact details, and provider flags.
    - `events`: Append-only audit trail capturing state changes, timestamps, and correlation IDs.
    - `scheduled_actions`: Single queue for deferred tasks (`wait`, quiet-hours holds, scheduled follow-ups, autonomous retries).
    - `graph_checkpoints`: Persistence store for LangGraph supervisor checkpoints keyed by `lead_id`.
    - `provider_health`: Operational health log tracking the outcome of every provider invocation.
    - `webhook_receipts`: Idempotency tracking to prevent duplicate webhook processing.
  - **Indexes:** Compound unique index on phone number (`leads`), indexes on `status`, `run_at` (`scheduled_actions`), and `ts` (`events`).

## Authentication & Identity

- **Admin API Guard (`require_admin` in `backend/server.py`):**
  - **Mechanism:** Bearer token authorization header checked with constant-time string comparison (`secrets.compare_digest`).
  - **Secret:** `ADMIN_TOKEN` environment variable.
  - **Protected Endpoints:** `POST /api/seed`, `POST /api/simulate`, `POST /api/leads/bulk`, `POST /api/tick`, and `DELETE /api/reset`.
  - **Fail-Closed Design:** If `ADMIN_TOKEN` is unset, protected endpoints immediately reject all requests with HTTP 401 Unauthorized.
- **Frontend Admin Integration:**
  - Token input modal and indicator in `frontend/src/components/AdminTokenButton.jsx`.
  - Token auto-injected into Axios headers in `frontend/src/lib/api.js`.

## Observability & Logging

- **Logging Framework:** Python standard `logging` with structured formatting (`log = logging.getLogger(...)`).
- **Correlation IDs:** End-to-end request tracing propagating UUIDs through asynchronous background workers and database event rows.
- **Audit Trails:** Every state machine transition and provider execution writes a historical record into `db.events`.

## CI/CD & Deployment

- **Hosting Platform:**
  - **Backend:** Render Web Service defined in `render.yaml` (`uvicorn server:app --host 0.0.0.0 --port $PORT`).
  - **Frontend:** Vercel Static Deployment configured in `vercel.json` with SPA rewrite rules (`/* -> /index.html`).
- **Autonomous Tick Cron:**
  - GitHub Actions workflow (`.github/workflows/tick.yml`) triggers `POST /api/tick` every 10 minutes to drain due tasks and prevent backend instance idling on Render free tier.

---

*Integration analysis: 2026-09-09*
*Update after adding or modifying external integrations*
