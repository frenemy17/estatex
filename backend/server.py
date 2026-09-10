"""EstateX AI Lead Concierge - FastAPI Backend Server.

Assembles domain services from backend/core/ and route controllers from backend/routes/.
Maintains backward-compatible symbol re-exports for test harness double compatibility.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import providers
import core.database as _db_mod
import core.pipeline as _pipeline_mod
import core.rate_limit as _rate_mod
from core.database import (
    _client,
    _db,
    clog,
    close_db,
    db,
    from_mongo,
    get_db,
    log,
    now,
    now_iso,
    to_mongo,
)
from core.models import (
    Appointment,
    BaseDoc,
    BookSlotRequest,
    Event,
    GoogleLeadColumn,
    GoogleLeadPayload,
    Lead,
    LeadCreate,
    LeadStatus,
    Qualification,
    ScheduledAction,
)
from core.pipeline import (
    _background_tasks,
    _compiled_graph,
    _dispatch_pipeline_sync,
    _move_to_calling,
    _schedule_supervisor_check,
    get_graph,
    run_ai_pipeline,
    run_supervisor,
)
from core.rate_limit import (
    LEAD_RATE_LIMIT_PER_MIN,
    _in_memory_rate_limit,
    _rate_buckets,
    rate_limit,
)
from core.scoring import (
    FIELD_ORDER,
    QUALIFICATION_RUBRIC,
    _fallback_score,
    _match_question,
    _QUESTION_PATTERNS,
    classify_score,
    extract_answers,
    qualify_and_route,
    qualify_with_llm,
)
from core.services import (
    CALL_TIMEOUT_MINUTES,
    QUIET_HOURS_ENABLED,
    QUIET_HOURS_END,
    QUIET_HOURS_START,
    SUPERVISOR_WAIT_HOURS,
    _lead_fields,
    fetch_slots,
    in_quiet_hours,
    quiet_hours_end_at,
    record_provider,
    send_notification,
    sync_crm,
)
from core.state_machine import (
    ACTIVE,
    ALLOWED_TRANSITIONS,
    STATUSES,
    TERMINAL,
    can_transition,
    is_legal,
    record_event,
    touch,
    transition,
)
from core.tick import (
    BACKOFF_BASE_SECONDS,
    MAX_BACKOFF_SECONDS,
    MAX_SCHEDULED_ATTEMPTS,
    _run_scheduled,
    compute_backoff_seconds,
    run_tick,
    schedule_action,
)
import routes.auth as _auth_mod
import routes.webhooks as _webhooks_mod
from routes.admin import (
    FUNNEL_ORDER,
    SEED_LEADS,
    SIM_LEADS,
    analytics,
    eval_run,
    list_dead_letter,
    reset,
    retry_dead_letter,
    router as admin_router,
    seed,
    simulate,
    tick,
)
from routes.auth import ADMIN_TOKEN, require_admin
from routes.leads import (
    _ingest_lead,
    approve_lead,
    book,
    bulk_create_leads,
    create_lead,
    get_appointments,
    get_checkpoint,
    get_events,
    get_lead,
    get_scheduled,
    get_slots,
    list_leads,
    opt_out,
    reject_lead,
    rerun,
    router as leads_router,
    supervisor,
)
from routes.providers import list_providers, router as providers_router
from routes.webhooks import (
    GOOGLE_LEADS_WEBHOOK_KEY,
    VAPI_WEBHOOK_SECRET,
    _claim_once,
    _dispatch_supervisor,
    _finalize_twilio_voice_call,
    _pick,
    google_leads_webhook,
    router as webhooks_router,
    twilio_sms_webhook,
    vapi_webhook,
    voice_gather_endpoint,
    voice_twiml_endpoint,
)

QUESTIONS = providers.QUESTIONS


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        current_db = get_db()
        await current_db.command("ping")
        log.info("mongo connected db=%s", os.environ.get("DB_NAME", "estatex_db"))
        try:
            await current_db.rate_limits.create_index([("expires_at", 1)], expireAfterSeconds=0)
            await current_db.rate_limits.create_index([("key", 1), ("ts", 1)])
        except Exception as idx_err:
            log.warning("could not create rate_limits indexes: %s", idx_err)
    except Exception as e:  # noqa: BLE001
        log.error("mongo unreachable at startup: %s", e)
    if providers.demo_mode():
        log.info("DEMO_MODE=1 — every provider forced to MOCK")
    if not os.environ.get("ADMIN_TOKEN"):
        log.warning("ADMIN_TOKEN not set — admin routes (seed/reset/tick) are locked")
    yield
    close_db()


app = FastAPI(title="EstateX AI Lead Concierge", lifespan=lifespan)
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"service": "estatex-ai-lead-concierge", "status": "ok"}


@api.get("/health")
async def health():
    """Boot diagnostics. Reports DB reachability instead of dying on import."""
    db_ok, db_error = True, None
    try:
        await get_db().command("ping")
    except Exception as e:  # noqa: BLE001
        db_ok, db_error = False, str(e)[:300]
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "error",
        "db_error": db_error,
        "demo_mode": providers.demo_mode(),
        "admin_configured": bool(os.environ.get("ADMIN_TOKEN")),
        "quiet_hours": {
            "enabled": QUIET_HOURS_ENABLED,
            "start_utc": QUIET_HOURS_START,
            "end_utc": QUIET_HOURS_END,
            "active_now": in_quiet_hours(),
        },
        "providers": {p["name"]: p["mode"] for p in providers.all_provider_status()},
        "ts": now_iso(),
    }


# Include sub-routers into /api
api.include_router(leads_router)
api.include_router(webhooks_router)
api.include_router(admin_router)
api.include_router(providers_router)

# Mount /api onto top-level app
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
