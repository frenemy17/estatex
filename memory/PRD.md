# AI Real-Estate Lead Qualifier — PRD

## Problem
Real-estate leads go cold in minutes; first responder wins. Humans can't call every lead
instantly, 24/7, and qualify consistently. This platform ingests leads → AI calls
& qualifies in seconds → auto-books → follows up → shows everything on a dashboard.

## Stack
- Backend: FastAPI + Motor (MongoDB) + BackgroundTasks (no Redis/Celery).
- LLM: Groq LLM (llama-3.3-70b-versatile).
- Agent layer: bespoke LangGraph-style StateGraph + MongoCheckpointer.
- Frontend: React 19 + Tailwind + shadcn/ui + Recharts + Phosphor icons.

## Personas
- Real-estate broker/team lead: monitors pipeline, approves escalations, reviews AI qualifications.
- End buyer/renter: fills capture form OR submits Google Ads Lead Form.

## What's implemented — 2026-07-22

### v1 (automation)
- POST /api/lead — dedupe by phone + background AI pipeline dispatch.
- POST /api/webhooks/google-leads — Google Ads Lead Form Extensions webhook with key verification, FULL_NAME/EMAIL/PHONE_NUMBER + FIRST/LAST_NAME fallback, is_test flag.
- Background pipeline: mock voice call → Gemini structured JSON qualification → score → classify → CRM sync → follow-up.
- State machine (NEW → CALLING → IN_CONVERSATION → QUALIFIED|HOT|NURTURE → BOOKED) with legal-transitions guardrail + event audit log.
- Providers (mocked, swappable): Voice, Booking, Notification, CRM.
- Booking: mock Cal.com slot fetch + book + double-booking safety via state-machine.
- Notifications: quiet hours (21:00-08:00 UTC configurable) + opt-out enforcement + defer.
- Per-lead correlation-id logging.
- Simulation harness (15 scripted leads) + eval endpoint (qualification accuracy, booking rate, hallucination proxy).
- pytest suite (8 tests: transitions map + scoring rubric).

### v2 (agentic)
- LangGraph-style StateGraph engine (`agents/graph.py`) with `add_node`, `add_edge`, `add_conditional_edges`, `compile`, `ainvoke`.
- MongoCheckpointer — state persisted per lead_id, memory across days.
- LLM-powered supervisor node — Gemini picks next_action ∈ {call, enrich, follow_up, escalate, wait, done} + reasoning.
- Sub-agents: enrichment_agent (LLM area brief) + followup_agent (LLM drafts channel/tone/subject/body).
- Human-in-the-loop interrupt: escalate node pauses; /approve or /reject resumes with approved flag.
- Frontend approval banner + Approve/Reject buttons.
- V1 vs V2 side-by-side comparison view.

## Backlog
- P1: Real Vapi + Cal.com + HubSpot + Twilio + Resend (swap provider classes; env keys only).
- P1: LangGraph library (`pip install langgraph`) if user wants the real dependency instead of our micro-engine.
- P2: schema version on checkpoints (per code review).
- P2: extract server.py into modules (currently ~980 lines).
- P2: auth + multi-tenant.

## Next Action Items
- Ask user for real API keys and swap providers.
- Add "next check" scheduler (cron-like) that periodically invokes supervisor on WAIT leads.
