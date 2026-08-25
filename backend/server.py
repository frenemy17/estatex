"""EstateX — AI real-estate lead concierge. FastAPI backend.

Three layers, deliberately separated:

* **Deterministic backbone** — the ``ALLOWED_TRANSITIONS`` state machine plus an
  append-only event log. Every status change goes through :func:`transition`, so
  the audit trail can never disagree with the lead's state.
* **Agentic layer** — LLM qualification and a LangGraph-style supervisor graph
  with Mongo checkpointing (``agents/``).
* **Providers** — ``providers.py``. Absent keys run a mock; present keys run the
  real API and report the real HTTP status. Nothing claims a success it did not
  get.

Autonomy comes from ``db.scheduled_actions`` + ``POST /api/tick``: anything that
says "later" (supervisor waits, quiet-hours deferrals) enqueues a row, and the
tick drains what is due and rescues leads stuck mid-call. A cron hitting /tick is
what makes the "24/7" claim true.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import certifi
from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
)
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

import providers
from providers import ProviderResult

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("estatex")

for handler in logging.getLogger().handlers:
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [lead=%(lead_id)s] %(name)s %(levelname)s %(message)s",
            defaults={"lead_id": "-"},
        )
    )


def clog(lead_id: str | None = None) -> logging.LoggerAdapter:
    """Correlation-id logger — every message tagged with [lead=<id>]."""
    return logging.LoggerAdapter(log, {"lead_id": lead_id or "-"})


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ---------- DB (lazy) ----------
#
# Resolved on first use rather than at import. A missing MONGO_URL used to take
# the whole app down at import time with an opaque 500 and no /health output; now
# the app boots, /api/health reports the problem, and `pytest` can import this
# module without a database.

_client: AsyncIOMotorClient | None = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        url = os.environ.get("MONGO_URL")
        if not url:
            raise RuntimeError(
                "MONGO_URL is not set. Copy backend/.env.example to backend/.env "
                "and set MONGO_URL + DB_NAME."
            )
        kwargs: dict[str, Any] = {"serverSelectionTimeoutMS": 8000}
        if "mongodb+srv" in url:
            # Atlas needs an explicit CA bundle on many macOS/Linux Python builds.
            kwargs["tlsCAFile"] = certifi.where()
        _client = AsyncIOMotorClient(url, **kwargs)
        _db = _client[os.environ.get("DB_NAME", "estatex_db")]
    return _db


def close_db() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client, _db = None, None


class _DBProxy:
    """Deferred handle so ``db.leads`` and ``db["x"]`` work before connect."""

    def __getattr__(self, name: str):
        return getattr(get_db(), name)

    def __getitem__(self, name: str):
        return get_db()[name]


db = _DBProxy()


# ---------- Config ----------

GOOGLE_LEADS_WEBHOOK_KEY = os.environ.get("GOOGLE_LEADS_WEBHOOK_KEY")
QUIET_HOURS_ENABLED = _flag("QUIET_HOURS_ENABLED", True)
QUIET_HOURS_START = int(os.environ.get("QUIET_HOURS_START", "21"))  # 9pm UTC
QUIET_HOURS_END = int(os.environ.get("QUIET_HOURS_END", "8"))  # 8am UTC
# How long a lead may sit in CALLING/IN_CONVERSATION before /tick rescues it.
CALL_TIMEOUT_MINUTES = int(os.environ.get("CALL_TIMEOUT_MINUTES", "20"))
SUPERVISOR_WAIT_HOURS = int(os.environ.get("SUPERVISOR_WAIT_HOURS", "6"))
LEAD_RATE_LIMIT_PER_MIN = int(os.environ.get("LEAD_RATE_LIMIT_PER_MIN", "10"))


# ---------- State machine ----------

LeadStatus = Literal[
    "NEW", "CALLING", "IN_CONVERSATION", "QUALIFIED", "NURTURE", "HOT", "BOOKED"
]

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "NEW": {"CALLING", "NURTURE"},
    "CALLING": {"IN_CONVERSATION", "NURTURE", "NEW"},
    "IN_CONVERSATION": {"QUALIFIED", "NURTURE", "HOT"},
    "QUALIFIED": {"BOOKED", "NURTURE"},
    "HOT": {"BOOKED", "QUALIFIED", "NURTURE"},
    "NURTURE": {"CALLING", "QUALIFIED", "HOT"},
    "BOOKED": {"NURTURE"},
}

QUALIFICATION_RUBRIC = {
    "threshold_qualified": 70,
    "threshold_nurture": 40,
    "weights": {"intent": 25, "budget": 25, "timeline": 20, "financing": 15, "area": 15},
}

QUESTIONS = providers.QUESTIONS


# ---------- Models ----------


class BaseDoc(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class Qualification(BaseModel):
    intent: Optional[str] = None
    budget: Optional[str] = None
    timeline: Optional[str] = None
    financing: Optional[str] = None
    area: Optional[str] = None
    reasoning: Optional[str] = None


class Lead(BaseDoc):
    name: str
    phone: str
    email: Optional[EmailStr] = None
    source: str = "web"
    status: LeadStatus = "NEW"
    score: int = 0
    qualification: Optional[Qualification] = None
    transcript: list[dict[str, str]] = Field(default_factory=list)
    supervisor_trace: list[dict[str, Any]] = Field(default_factory=list)
    attempt_history: list[dict[str, Any]] = Field(default_factory=list)
    enrichment: Optional[dict[str, Any]] = None
    opted_out: bool = False
    pending_approval: bool = False
    next_check_at: Optional[str] = None
    # Set when a real Vapi call is in flight and we are waiting on the
    # end-of-call-report webhook to deliver the transcript.
    voice_call_id: Optional[str] = None
    awaiting_transcript: bool = False
    # Pins which scripted mock conversation this lead gets. Only set by
    # /api/simulate, so the eval sweep covers every profile exactly.
    sim_profile: Optional[int] = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class LeadCreate(BaseModel):
    name: str
    phone: str
    email: Optional[EmailStr] = None
    source: str = "web"
    notes: Optional[str] = None


class Event(BaseDoc):
    lead_id: str
    # transition | note | call | booking | followup | supervisor | enrichment
    # | provider | error
    kind: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    reason: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=now)


class Appointment(BaseDoc):
    lead_id: str
    slot_iso: str
    duration_min: int = 30
    provider: str = "mock-calcom"
    external_id: Optional[str] = None
    status: str = "BOOKED"
    created_at: datetime = Field(default_factory=now)


class ScheduledAction(BaseDoc):
    """A promise to do something later. Drained by :func:`run_tick`.

    This collection is what turns "wait 6 hours" and "deferred until 08:00" from
    a logged intention into an action that actually happens.
    """

    lead_id: str
    kind: str  # supervisor | notify
    run_at: str  # ISO-8601 UTC; compared lexicographically
    payload: dict[str, Any] = Field(default_factory=dict)
    state: str = "PENDING"  # PENDING | RUNNING | DONE | FAILED
    attempts: int = 0
    error: Optional[str] = None
    reason: str = ""
    created_at: datetime = Field(default_factory=now)


class BookSlotRequest(BaseModel):
    slot_iso: str


# ---------- Serialization ----------


def to_mongo(doc: BaseModel) -> dict:
    d = doc.model_dump()
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def from_mongo(cls, doc: dict):
    if not doc:
        return None
    d = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("created_at", "updated_at", "ts"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = datetime.fromisoformat(d[k])
            except Exception:  # noqa: BLE001
                pass
    return cls(**d)


# ---------- Auth ----------


async def require_admin(
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> bool:
    """Guard destructive and expensive routes.

    Deliberately fails closed: with no ``ADMIN_TOKEN`` configured, admin routes
    are unreachable rather than open. A public deploy therefore starts read-only.
    """
    expected = os.environ.get("ADMIN_TOKEN")
    if not expected:
        raise HTTPException(
            401,
            "Admin routes are locked because ADMIN_TOKEN is not set on the server.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(401, "Invalid or missing X-Admin-Token")
    return True


_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request, bucket: str = "lead", per_min: int | None = None) -> None:
    """Per-IP sliding window. The public capture form reaches the LLM, so an
    unthrottled endpoint is a billing hole as much as an abuse one."""
    limit = per_min if per_min is not None else LEAD_RATE_LIMIT_PER_MIN
    if limit <= 0:
        return
    ip = (request.client.host if request.client else "unknown") or "unknown"
    key = f"{bucket}:{ip}"
    window = _rate_buckets[key]
    cutoff = time.monotonic() - 60
    while window and window[0] < cutoff:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(429, f"Rate limit: max {limit} requests/minute")
    window.append(time.monotonic())


# ---------- Events + transitions ----------


async def record_event(
    lead_id: str,
    kind: str,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str = "",
    meta: dict[str, Any] | None = None,
) -> None:
    ev = Event(
        lead_id=lead_id,
        kind=kind,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        meta=meta or {},
    )
    await db.events.insert_one(to_mongo(ev))


def is_legal(current: str, target: str) -> bool:
    return target == current or target in ALLOWED_TRANSITIONS.get(current, set())


async def transition(lead_id: str, new_status: str, reason: str = "") -> Lead:
    lead_doc = await db.leads.find_one({"id": lead_id})
    if not lead_doc:
        raise HTTPException(404, "Lead not found")
    lead = from_mongo(Lead, lead_doc)
    if new_status == lead.status:
        return lead
    if not is_legal(lead.status, new_status):
        raise HTTPException(400, f"Illegal transition {lead.status} -> {new_status}")
    old = lead.status
    lead.status = new_status  # type: ignore[assignment]
    lead.updated_at = now()
    await db.leads.update_one(
        {"id": lead_id},
        {"$set": {"status": new_status, "updated_at": lead.updated_at.isoformat()}},
    )
    await record_event(lead_id, "transition", old, new_status, reason)
    clog(lead_id).info("transition %s -> %s (%s)", old, new_status, reason)
    return lead


async def touch(lead_id: str, **fields: Any) -> None:
    """Update lead fields and bump ``updated_at`` (which /tick uses for timeouts)."""
    fields["updated_at"] = now_iso()
    await db.leads.update_one({"id": lead_id}, {"$set": fields})


# ---------- Provider glue ----------
#
# Providers are pure I/O. Persistence of what they did lives here: one row per
# provider in db.provider_health (drives the dashboard chips) and, when a lead is
# involved, one event in the audit log.


async def record_provider(
    result: ProviderResult,
    lead_id: str | None = None,
    reason: str = "",
    kind: str | None = None,
    extra: dict[str, Any] | None = None,
) -> ProviderResult:
    await db.provider_health.update_one(
        {"_id": result.spec},
        {
            "$set": {
                "mode": result.mode,
                "ok": result.ok,
                "status": result.status,
                "error": result.error,
                "provider": result.provider,
                "at": now_iso(),
            },
            "$inc": {"calls": 1, "failures": 0 if result.ok else 1},
        },
        upsert=True,
    )
    if lead_id and (reason or not result.ok):
        meta = {**result.to_meta(), **(extra or {})}
        await record_event(
            lead_id,
            kind or ("provider" if result.ok else "error"),
            reason=reason or f"{result.spec}.failed",
            meta=meta,
        )
    if result.live_failure:
        clog(lead_id).warning(
            "%s LIVE failure status=%s error=%s", result.spec, result.status, result.error
        )
    return result


def in_quiet_hours(at: datetime | None = None) -> bool:
    if not QUIET_HOURS_ENABLED:
        return False
    h = (at or now()).hour
    if QUIET_HOURS_START <= QUIET_HOURS_END:
        return QUIET_HOURS_START <= h < QUIET_HOURS_END
    return h >= QUIET_HOURS_START or h < QUIET_HOURS_END


def quiet_hours_end_at(at: datetime | None = None) -> datetime:
    ref = at or now()
    # `% 24` so a config of QUIET_HOURS_END=24 means midnight rather than crashing.
    target = ref.replace(hour=QUIET_HOURS_END % 24, minute=0, second=0, microsecond=0)
    if target <= ref:
        target += timedelta(days=1)
    return target


def _lead_fields(lead: Any) -> dict[str, Any]:
    """Accept a Lead, a raw Mongo dict, or anything with the right attributes."""
    if isinstance(lead, dict):
        return lead
    return {
        "id": getattr(lead, "id", None),
        "name": getattr(lead, "name", None),
        "phone": getattr(lead, "phone", None),
        "email": getattr(lead, "email", None),
    }


async def send_notification(
    lead: Any, channel: str, template: str, ctx: dict | None = None
) -> dict:
    """Send an SMS or email under the compliance rules.

    Policy order — opt-out, then quiet hours, then transport:

    * opted out  -> blocked, recorded, nothing sent.
    * quiet hours -> enqueued in ``scheduled_actions`` for the moment the window
      opens. The previous version logged a ``deferred_until`` and dropped the
      message on the floor; now /tick actually sends it.
    * otherwise   -> real provider if configured, mock if not. A LIVE failure is
      recorded as a failure *and then* retried through the mock, so the audit log
      shows both the attempt and the fallback.
    """
    f = _lead_fields(lead)
    lead_id = f.get("id")
    name = f.get("name") or "there"

    doc = await db.leads.find_one({"id": lead_id}, {"opted_out": 1})
    if doc and doc.get("opted_out"):
        await record_event(
            lead_id,
            "followup",
            reason=f"{channel}/{template}/blocked",
            meta={"blocked": "opted_out", "provider": "notifier"},
        )
        return {"blocked": "opted_out"}

    ctx = ctx or {}
    subject = ctx.get("subject") or "Your property search"
    body = ctx.get("body") or (
        f"Hi {name}, following up on your property search — I have a couple of "
        "matches I'd like to show you."
    )

    if in_quiet_hours():
        run_at = quiet_hours_end_at()
        action = await schedule_action(
            lead_id,
            "notify",
            run_at,
            payload={"channel": channel, "template": template, "ctx": ctx},
            reason=f"{channel}/{template}/quiet_hours",
        )
        await record_event(
            lead_id,
            "followup",
            reason=f"{channel}/{template}/deferred",
            meta={
                "deferred_until": run_at.isoformat(),
                "scheduled_action_id": action.id,
                "provider": "notifier",
                "channel": channel,
                "template": template,
            },
        )
        return {
            "deferred_until": run_at.isoformat(),
            "scheduled_action_id": action.id,
            "channel": channel,
            "template": template,
        }

    if channel == "sms":
        result = await providers.notifier.send_sms(to=f.get("phone"), body=body)
    else:
        result = await providers.notifier.send_email(
            to=f.get("email"), subject=subject, body=body
        )

    if result.live_failure:
        await record_provider(
            result, lead_id, reason=f"{channel}/{template}/provider_failed", kind="error"
        )
        # Fall back so the pipeline still advances, but as a *separate* recorded
        # result — the log never shows a live send that did not happen.
        result = ProviderResult(
            spec=result.spec,
            provider=f"mock-{result.spec}",
            mode="MOCK",
            ok=True,
            data={"fallback_after": result.status},
        )

    payload = {
        "channel": channel,
        "template": template,
        "to": result.data.get("to") or f.get("phone" if channel == "sms" else "email"),
        "sent_at": now_iso(),
        **result.to_meta(),
        "ctx": ctx,
    }
    await record_provider(result, lead_id=None)
    await record_event(
        lead_id, "followup", reason=f"{channel}/{template}", meta=payload
    )
    return payload


async def fetch_slots(lead_id: str | None = None) -> dict:
    result = await providers.booker.get_slots()
    if result.live_failure:
        await record_provider(
            result, lead_id, reason="calcom.slots_failed", kind="error"
        )
        return {
            "slots": providers.mock_slots(),
            "provider": "mock-calcom",
            "mode": "MOCK",
            "degraded": True,
            "error": result.error,
            "status": result.status,
        }
    await record_provider(result, lead_id=None)
    return {
        "slots": result.data.get("slots", []),
        "provider": result.provider,
        "mode": result.mode,
        "degraded": False,
    }


async def sync_crm(lead: Lead) -> None:
    contact = await providers.crm.upsert_contact(
        name=lead.name, phone=lead.phone, email=lead.email
    )
    await record_provider(
        contact,
        lead.id,
        reason="crm.contact_upserted" if contact.ok else "crm.contact_failed",
        kind="note" if contact.ok else "error",
    )
    if lead.status not in ("QUALIFIED", "HOT"):
        return
    deal = await providers.crm.create_deal(
        name=lead.name,
        status=lead.status,
        score=lead.score,
        contact_id=contact.data.get("contact_id"),
    )
    await record_provider(
        deal,
        lead.id,
        reason="crm.deal_created" if deal.ok else "crm.deal_failed",
        kind="note" if deal.ok else "error",
        extra={"score": lead.score},
    )


# ---------- Scheduled actions ----------


async def schedule_action(
    lead_id: str,
    kind: str,
    run_at: datetime,
    payload: dict | None = None,
    reason: str = "",
) -> ScheduledAction:
    action = ScheduledAction(
        lead_id=lead_id,
        kind=kind,
        run_at=run_at.isoformat(),
        payload=payload or {},
        reason=reason,
    )
    await db.scheduled_actions.insert_one(to_mongo(action))
    clog(lead_id).info("scheduled %s at %s (%s)", kind, action.run_at, reason)
    return action


async def _run_scheduled(doc: dict) -> str:
    """Execute one due action. Returns a short label for the tick summary."""
    kind = doc.get("kind")
    lead_id = doc["lead_id"]
    payload = doc.get("payload") or {}

    if kind == "supervisor":
        await run_supervisor(lead_id)
        return "supervisor"

    if kind == "notify":
        lead_doc = await db.leads.find_one({"id": lead_id}, {"_id": 0})
        if not lead_doc:
            return "notify:lead_missing"
        await send_notification(
            lead_doc,
            payload.get("channel", "email"),
            payload.get("template", "nurture_sequence"),
            payload.get("ctx"),
        )
        return "notify"

    raise ValueError(f"unknown scheduled action kind: {kind}")


async def run_tick(limit: int = 25) -> dict:
    """One idempotent autonomy pass. This is the whole scheduler.

    1. drain due ``scheduled_actions``
    2. rescue leads stranded mid-call (a serverless freeze or a dropped Vapi
       webhook would otherwise leave them in CALLING forever)

    Safe to run concurrently: each action is claimed with a conditional update,
    so two overlapping ticks cannot run the same row twice.
    """
    started = now()
    summary: dict[str, Any] = {
        "ran_at": started.isoformat(),
        "drained": 0,
        "failed": 0,
        "rescued": 0,
        "requalified": 0,
        "actions": [],
    }

    due = (
        await db.scheduled_actions.find(
            {"state": "PENDING", "run_at": {"$lte": started.isoformat()}}
        )
        .sort("run_at", 1)
        .to_list(limit)
    )

    for doc in due:
        claim = await db.scheduled_actions.update_one(
            {"id": doc["id"], "state": "PENDING"},
            {"$set": {"state": "RUNNING", "started_at": now_iso()}, "$inc": {"attempts": 1}},
        )
        if not claim.modified_count:
            continue  # another tick claimed it
        try:
            label = await _run_scheduled(doc)
            await db.scheduled_actions.update_one(
                {"id": doc["id"]},
                {"$set": {"state": "DONE", "finished_at": now_iso(), "error": None}},
            )
            summary["drained"] += 1
            summary["actions"].append(
                {"lead_id": doc["lead_id"], "kind": doc.get("kind"), "result": label}
            )
        except Exception as e:  # noqa: BLE001
            clog(doc["lead_id"]).exception("scheduled action failed: %s", e)
            await db.scheduled_actions.update_one(
                {"id": doc["id"]},
                {"$set": {"state": "FAILED", "finished_at": now_iso(), "error": str(e)}},
            )
            await record_event(
                doc["lead_id"],
                "error",
                reason=f"scheduled.{doc.get('kind')}_failed",
                meta={"error": str(e)[:500], "action_id": doc["id"]},
            )
            summary["failed"] += 1

    cutoff = (started - timedelta(minutes=CALL_TIMEOUT_MINUTES)).isoformat()
    stuck = await db.leads.find(
        {"status": {"$in": ["CALLING", "IN_CONVERSATION"]}, "updated_at": {"$lt": cutoff}},
        {"_id": 0},
    ).to_list(50)

    for doc in stuck:
        lead_id = doc["id"]
        if doc.get("transcript"):
            # A transcript landed but qualification never ran (process died
            # mid-pipeline). Resume rather than discard the conversation.
            try:
                await qualify_and_route(lead_id)
                summary["requalified"] += 1
                summary["actions"].append({"lead_id": lead_id, "kind": "requalify"})
            except Exception as e:  # noqa: BLE001
                clog(lead_id).exception("tick requalify failed: %s", e)
                summary["failed"] += 1
            continue

        await record_event(
            lead_id,
            "error",
            reason="call.timeout",
            meta={
                "waited_minutes": CALL_TIMEOUT_MINUTES,
                "voice_call_id": doc.get("voice_call_id"),
                "detail": "no transcript received before timeout",
            },
        )
        try:
            await transition(lead_id, "NURTURE", "call.timeout")
            await touch(lead_id, awaiting_transcript=False)
            summary["rescued"] += 1
            summary["actions"].append({"lead_id": lead_id, "kind": "rescue"})
        except HTTPException as e:
            clog(lead_id).warning("tick rescue blocked: %s", e.detail)
            summary["failed"] += 1

    summary["took_ms"] = int((now() - started).total_seconds() * 1000)
    log.info(
        "tick drained=%s failed=%s rescued=%s requalified=%s",
        summary["drained"],
        summary["failed"],
        summary["rescued"],
        summary["requalified"],
    )
    return summary


# ---------- Qualification ----------


FIELD_ORDER = ("intent", "budget", "timeline", "financing", "area")

# Which qualification field a question is asking about. Checked in order, so the
# more specific patterns win over the catch-all "looking for".
_QUESTION_PATTERNS = [
    ("budget", r"budget|price range|how much|spend"),
    ("financing", r"financ|pre-?approv|mortgage|lender|loan"),
    ("timeline", r"timeline|how soon|move in|next few months|when are you"),
    ("area", r"neighbou?rhood|area|location|part of town|where are you look"),
    ("intent", r"kind of property|type of property|buy, rent|looking for|rent or buy"),
]


def _match_question(text: str) -> Optional[str]:
    low = text.lower()
    for field_name, pattern in _QUESTION_PATTERNS:
        if re.search(pattern, low):
            return field_name
    return None


def extract_answers(transcript: list[dict[str, str]]) -> dict[str, Optional[str]]:
    """Map the lead's replies onto qualification fields, deterministically.

    Aligning by position alone breaks on the opening pleasantry — "Sure, go
    ahead." lands in ``intent`` and shifts every real answer one field right,
    which scored every keyless-demo lead ~20 and dumped it into NURTURE. So pair
    each reply with the question that preceded it, and only fall back to
    positional assignment when no question was recognised (a free-form live call).
    """
    out: dict[str, Optional[str]] = {k: None for k in FIELD_ORDER}
    pending: Optional[str] = None
    unmatched: list[str] = []

    for turn in transcript:
        text = (turn.get("text") or "").strip()
        if not text:
            continue
        if turn.get("role") == "agent":
            pending = _match_question(text)
        else:
            if pending and out[pending] is None:
                out[pending] = text
            else:
                unmatched.append(text)
            pending = None

    if all(v is None for v in out.values()):
        for field_name, text in zip(FIELD_ORDER, unmatched):
            out[field_name] = text
    return out


def _fallback_score(q: Qualification) -> int:
    """Deterministic rubric. Also the scorer of record — the LLM extracts fields,
    this function scores them, so scoring stays explainable and reproducible."""
    score = 0
    if q.intent and any(k in q.intent.lower() for k in ("buy", "family", "invest")):
        score += 25
    m = re.search(r"([\d,.]+)\s*[km]?", (q.budget or "").lower())
    if m:
        num = float(m.group(1).replace(",", ""))
        if "m" in (q.budget or "").lower():
            num *= 1_000_000
        elif "k" in (q.budget or "").lower():
            num *= 1_000
        if num >= 500_000:
            score += 25
        elif num >= 250_000:
            score += 15
    if q.timeline and any(
        k in q.timeline.lower() for k in ("30 day", "month", "urgent", "asap")
    ):
        score += 20
    elif q.timeline and "6" in q.timeline:
        score += 5
    if q.financing and any(
        k in q.financing.lower() for k in ("pre-approved", "cash", "approved")
    ):
        score += 15
    if q.area and q.area.lower() not in ("undecided", "unsure", ""):
        score += 15
    return min(100, score)


async def qualify_with_llm(lead: Lead) -> tuple[Qualification, int, ProviderResult]:
    """Extract structured qualification from the transcript, then score it."""
    convo = "\n".join(f"{m['role'].upper()}: {m['text']}" for m in lead.transcript)
    fallback = {
        **extract_answers(lead.transcript),
        "reasoning": "Fallback extraction (LLM unavailable).",
    }

    parsed, result = await providers.llm_json(
        "You are an elite real-estate lead qualification analyst. Extract structured "
        "buyer qualification data from a conversation and return STRICT JSON only "
        "(no markdown, no prose).",
        "Given this real-estate lead conversation, return a JSON object with keys: "
        "intent, budget, timeline, financing, area, reasoning. Each is a short string. "
        "`reasoning` explains the qualification in 1-2 sentences.\n\n"
        f"Conversation:\n{convo}\n\nRespond with JSON only.",
        fallback,
        label=f"qualify-{lead.id}",
    )
    q = Qualification(
        **{
            k: (str(v) if v is not None else None)
            for k, v in parsed.items()
            if k in Qualification.model_fields
        }
    )
    return q, _fallback_score(q), result


def classify_score(score: int) -> str:
    if score >= 85:
        return "HOT"
    if score >= QUALIFICATION_RUBRIC["threshold_qualified"]:
        return "QUALIFIED"
    return "NURTURE"


# ---------- Pipeline ----------


async def _move_to_calling(lead: Lead) -> bool:
    """Try to put a lead into CALLING, honouring the state machine.

    A supervisor deciding to ``call`` a QUALIFIED lead used to raise HTTP 400 into
    a blanket ``except`` and surface as an opaque ``pipeline.error``. Now the
    refusal is explicit and visible in the audit log.
    """
    if lead.status == "CALLING":
        return True
    if is_legal(lead.status, "CALLING"):
        await transition(lead.id, "CALLING", "ai.dispatch")
        return True
    await record_event(
        lead.id,
        "error",
        from_status=lead.status,
        reason="call.blocked",
        meta={
            "detail": f"cannot dial from {lead.status}",
            "legal_next": sorted(ALLOWED_TRANSITIONS.get(lead.status, set())),
        },
    )
    clog(lead.id).info("call blocked from status=%s", lead.status)
    return False


async def run_ai_pipeline(lead_id: str) -> None:
    """Dial the lead, then qualify.

    Splits at the call boundary. With a mock provider the transcript is available
    immediately and we qualify in the same pass. With a live provider the call is
    only *dispatched* here — the lead parks in CALLING with
    ``awaiting_transcript`` until ``POST /api/webhooks/vapi`` delivers the real
    conversation. Qualifying an empty transcript scores every lead 0, so we never
    do it.
    """
    try:
        lead_doc = await db.leads.find_one({"id": lead_id})
        if not lead_doc:
            log.warning("pipeline: lead %s not found", lead_id)
            return
        lead = from_mongo(Lead, lead_doc)

        if not await _move_to_calling(lead):
            return

        delay = float(os.environ.get("DEMO_CALL_DELAY_SECONDS", "1.2" if providers.demo_mode() else "0"))
        if delay > 0:
            await asyncio.sleep(delay)  # visual beat for the demo only

        call = await providers.voice.start_call(
            lead_id=lead.id, name=lead.name, phone=lead.phone, profile=lead.sim_profile
        )

        if call.live_failure:
            # Do NOT synthesise a transcript for a real person whose call failed.
            # Record it, park the lead in NURTURE, and retry later.
            await record_provider(call, lead_id, reason="call.failed", kind="error")
            await transition(lead_id, "NURTURE", "call.failed")
            await schedule_action(
                lead_id,
                "supervisor",
                now() + timedelta(hours=2),
                reason="retry_after_call_failure",
            )
            return

        await record_provider(call, lead_id=None)
        attempts = list(lead.attempt_history) + [
            {
                "kind": "call",
                "provider": call.provider,
                "mode": call.mode,
                "ts": now_iso(),
            }
        ]
        transcript = call.data.get("transcript")

        if not transcript:
            # LIVE dispatch succeeded; the transcript arrives by webhook.
            await touch(
                lead_id,
                attempt_history=attempts,
                voice_call_id=call.data.get("call_id"),
                awaiting_transcript=True,
            )
            await record_event(
                lead_id,
                "call",
                reason="call.awaiting_transcript",
                meta={
                    **call.to_meta(),
                    "call_id": call.data.get("call_id"),
                    "timeout_minutes": CALL_TIMEOUT_MINUTES,
                },
            )
            clog(lead_id).info("live call in flight, awaiting webhook transcript")
            return

        await touch(
            lead_id,
            transcript=transcript,
            attempt_history=attempts,
            awaiting_transcript=False,
        )
        await record_event(
            lead_id, "call", reason="call.completed", meta={"turns": len(transcript), **call.to_meta()}
        )
        await qualify_and_route(lead_id)
    except Exception as e:  # noqa: BLE001
        clog(lead_id).exception("ai pipeline failed: %s", e)
        await record_event(
            lead_id, "error", reason="pipeline.error", meta={"error": str(e)[:500]}
        )


async def qualify_and_route(lead_id: str) -> dict:
    """Score an existing transcript, route the lead, sync CRM, follow up.

    The single path shared by the mock pipeline, the Vapi webhook, and /tick's
    recovery of a half-finished lead.
    """
    lead_doc = await db.leads.find_one({"id": lead_id})
    if not lead_doc:
        raise HTTPException(404, "Lead not found")
    lead = from_mongo(Lead, lead_doc)
    if not lead.transcript:
        raise HTTPException(409, "Cannot qualify a lead with no transcript")

    if lead.status == "CALLING":
        await transition(lead_id, "IN_CONVERSATION", "voice.completed")

    q, score, llm = await qualify_with_llm(lead)
    await record_provider(llm, lead_id=None)
    if llm.live_failure:
        await record_provider(
            llm, lead_id, reason="qualification.llm_failed", kind="error"
        )

    await touch(lead_id, qualification=q.model_dump(), score=score, awaiting_transcript=False)
    await record_event(
        lead_id,
        "note",
        reason="qualification.completed",
        meta={"score": score, "qualification": q.model_dump(), "llm": llm.to_meta()},
    )

    final_status = classify_score(score)
    lead_doc = await db.leads.find_one({"id": lead_id})
    lead = from_mongo(Lead, lead_doc)
    if is_legal(lead.status, final_status):
        await transition(lead_id, final_status, f"score={score}")
    else:
        await record_event(
            lead_id,
            "error",
            from_status=lead.status,
            reason="routing.blocked",
            meta={"wanted": final_status, "score": score},
        )

    lead_doc = await db.leads.find_one({"id": lead_id})
    lead = from_mongo(Lead, lead_doc)
    await sync_crm(lead)

    if lead.status in ("QUALIFIED", "HOT"):
        await send_notification(
            lead,
            "sms",
            "book_slot",
            {
                "body": f"Hi {lead.name}, I have viewing slots open this week — "
                "reply with a time that works and I'll lock it in."
            },
        )
    else:
        await send_notification(
            lead,
            "email",
            "nurture_sequence",
            {
                "subject": "A few listings worth watching",
                "body": f"Hi {lead.name}, no rush at all — here are a few listings "
                "in your range to keep an eye on.",
            },
        )
    return {"score": score, "lead_status": lead.status, "qualification": q.model_dump()}


# ---------- Supervisor ----------

# Keep strong references so fire-and-forget tasks are not garbage-collected
# mid-flight (asyncio only holds a weak reference to running tasks).
_background_tasks: set[asyncio.Task] = set()


def _dispatch_pipeline_sync(lead_id: str) -> None:
    """Fire-and-forget pipeline dispatch used by the graph's 'call' node."""
    task = asyncio.create_task(run_ai_pipeline(lead_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _schedule_supervisor_check(lead_id: str, hours: int | None = None) -> str:
    """Backs the supervisor's ``wait`` node with a real queued action."""
    run_at = now() + timedelta(hours=hours if hours is not None else SUPERVISOR_WAIT_HOURS)
    await schedule_action(lead_id, "supervisor", run_at, reason="supervisor.wait")
    await touch(lead_id, next_check_at=run_at.isoformat())
    return run_at.isoformat()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        from agents.supervisor import build_supervisor_graph  # local import

        _compiled_graph = build_supervisor_graph(
            db,
            send_notification,
            _dispatch_pipeline_sync,
            _schedule_supervisor_check,
        )
    return _compiled_graph


async def run_supervisor(lead_id: str, approve: bool | None = None) -> dict:
    """Invoke the compiled graph. If approve is set, resume from the interrupt."""
    lead_doc = await db.leads.find_one({"id": lead_id})
    if not lead_doc:
        raise HTTPException(404, "Lead not found")

    graph = get_graph()
    initial: dict = {"lead_id": lead_id}
    if approve is not None:
        initial["approved"] = approve
        state = await graph.ainvoke(initial, thread_id=lead_id, resume=True)
    else:
        state = await graph.ainvoke(initial, thread_id=lead_id)

    existing = lead_doc.get("supervisor_trace") or []
    merged_trace = existing + [s for s in state.get("trace", []) if s not in existing]
    await db.leads.update_one(
        {"id": lead_id},
        {
            "$set": {
                "supervisor_trace": merged_trace,
                "pending_approval": bool(
                    state.get("requires_approval") and state.get("_interrupt_at")
                ),
            }
        },
    )
    await record_event(
        lead_id,
        "supervisor",
        reason=f"next_action={state.get('next_action')}",
        meta={
            "trace_len": len(state.get("trace", [])),
            "requires_approval": bool(state.get("requires_approval")),
            "interrupt_at": state.get("_interrupt_at"),
            "approved": state.get("approved"),
        },
    )
    return {
        "next_action": state.get("next_action"),
        "trace": state.get("trace", []),
        "requires_approval": bool(
            state.get("requires_approval") and state.get("_interrupt_at")
        ),
        "enrichment": state.get("enrichment"),
        "followup_plan": state.get("followup_plan"),
    }


# ---------- App ----------


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await get_db().command("ping")
        log.info("mongo connected db=%s", os.environ.get("DB_NAME", "estatex_db"))
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


@api.get("/providers")
async def list_providers():
    """Per-provider mode plus the outcome of its last real call.

    Drives the dashboard status chips: grey = MOCK, green = LIVE and healthy,
    amber = LIVE but failing (with the real status code).
    """
    docs = await db.provider_health.find({}).to_list(50)
    health = {d["_id"]: d for d in docs}
    out = []
    for spec in providers.all_provider_status():
        h = health.get(spec["name"], {})
        out.append(
            {
                **spec,
                "last_ok": h.get("ok"),
                "last_status": h.get("status"),
                "last_error": h.get("error"),
                "last_provider": h.get("provider"),
                "last_call_at": h.get("at"),
                "calls": h.get("calls", 0),
                "failures": h.get("failures", 0),
            }
        )
    return {"demo_mode": providers.demo_mode(), "providers": out}


# ---------- Ingestion ----------


async def _ingest_lead(
    name: str,
    phone: str,
    email: str | None,
    source: str,
    bg: BackgroundTasks,
    extra_meta: dict | None = None,
) -> Lead:
    """Shared ingestion: dedupe by phone, insert, dispatch the AI pipeline."""
    existing = await db.leads.find_one({"phone": phone})
    if existing:
        return from_mongo(Lead, existing)
    lead = Lead(name=name, phone=phone, email=email, source=source)
    await db.leads.insert_one(to_mongo(lead))
    await record_event(
        lead.id, "note", reason="lead.captured", meta={"source": source, **(extra_meta or {})}
    )
    bg.add_task(run_ai_pipeline, lead.id)
    return lead


@api.post("/lead", response_model=Lead)
async def create_lead(payload: LeadCreate, bg: BackgroundTasks, request: Request):
    rate_limit(request, "lead")
    return await _ingest_lead(
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        source=payload.source,
        bg=bg,
    )


@api.post("/leads/bulk", dependencies=[Depends(require_admin)])
async def bulk_create_leads(payload: list[LeadCreate], bg: BackgroundTasks):
    results = []
    for p in payload:
        results.append(
            await _ingest_lead(
                name=p.name,
                phone=p.phone,
                email=p.email,
                source=p.source or "csv_import",
                bg=bg,
            )
        )
    return {"imported": len(results), "leads": results}


# ---------- Webhook: Google Ads Lead Form Extensions ----------
#
# Google POSTs a JSON body shaped like:
# {
#   "lead_id": "...", "api_version": "1.0", "form_id": 1234, "campaign_id": 5678,
#   "google_key": "<pre-shared secret>", "is_test": false,
#   "user_column_data": [
#       {"column_id": "FULL_NAME",    "string_value": "Jane Doe"},
#       {"column_id": "EMAIL",        "string_value": "jane@x.com"},
#       {"column_id": "PHONE_NUMBER", "string_value": "+14155550100"}
#   ]
# }
# Docs: https://support.google.com/google-ads/answer/7206379


class GoogleLeadColumn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    column_id: str
    string_value: str = ""


class GoogleLeadPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    google_key: str
    lead_id: Optional[str] = None
    api_version: Optional[str] = None
    form_id: Optional[int] = None
    campaign_id: Optional[int] = None
    is_test: bool = False
    user_column_data: list[GoogleLeadColumn] = Field(default_factory=list)


def _pick(cols: list[GoogleLeadColumn], key: str) -> str | None:
    key_up = key.upper()
    for c in cols:
        if (c.column_id or "").upper() == key_up:
            return (c.string_value or "").strip() or None
    return None


@api.post("/webhooks/google-leads")
async def google_leads_webhook(payload: GoogleLeadPayload, bg: BackgroundTasks):
    # No default key: an unconfigured webhook is closed, not guessable.
    if not GOOGLE_LEADS_WEBHOOK_KEY:
        log.warning("google-leads webhook rejected: GOOGLE_LEADS_WEBHOOK_KEY unset")
        raise HTTPException(503, "Webhook not configured")
    if not secrets.compare_digest(payload.google_key, GOOGLE_LEADS_WEBHOOK_KEY):
        log.warning("google-leads webhook rejected: bad key")
        raise HTTPException(401, "Invalid google_key")

    cols = payload.user_column_data
    name = _pick(cols, "FULL_NAME")
    if not name:
        first = _pick(cols, "FIRST_NAME") or ""
        last = _pick(cols, "LAST_NAME") or ""
        name = f"{first} {last}".strip() or None
    email = _pick(cols, "EMAIL")
    phone = _pick(cols, "PHONE_NUMBER")

    if not phone or not name:
        raise HTTPException(422, "Missing FULL_NAME or PHONE_NUMBER")

    source = "google-ads-test" if payload.is_test else "google-ads"
    lead = await _ingest_lead(
        name=name,
        phone=phone,
        email=email,
        source=source,
        bg=bg,
        extra_meta={
            "google_lead_id": payload.lead_id,
            "form_id": payload.form_id,
            "campaign_id": payload.campaign_id,
            "is_test": payload.is_test,
        },
    )
    log.info("google-leads accepted lead=%s source=%s form=%s", lead.id, source, payload.form_id)
    # Google Ads expects a 2xx within 5 seconds and does not read the body.
    return {"lead_id": lead.id, "status": "accepted"}


# ---------- Webhook: Vapi end-of-call report ----------


async def _claim_once(key: str, meta: dict | None = None) -> bool:
    """Idempotency latch. False means we already processed this message."""
    res = await db.webhook_receipts.update_one(
        {"_id": key},
        {"$setOnInsert": {"at": now_iso(), **(meta or {})}},
        upsert=True,
    )
    return res.upserted_id is not None


@api.post("/webhooks/vapi")
async def vapi_webhook(request: Request):
    """Receive the real call transcript and resume qualification.

    Without this endpoint, configuring Vapi made the product worse: the live call
    returned no transcript, qualification ran on nothing, and every lead scored 0
    and fell to NURTURE. Vapi sends several message types; only
    ``end-of-call-report`` carries the finished conversation.
    """
    secret = os.environ.get("VAPI_WEBHOOK_SECRET")
    if secret:
        sent = request.headers.get("x-vapi-secret") or request.headers.get("X-Vapi-Secret")
        if not sent or not secrets.compare_digest(sent, secret):
            raise HTTPException(401, "Invalid X-Vapi-Secret")

    body = await request.json()
    message = body.get("message") or body
    msg_type = message.get("type")
    if msg_type != "end-of-call-report":
        return {"status": "ignored", "type": msg_type}

    call = message.get("call") or {}
    call_id = call.get("id") or message.get("callId")
    lead_id = ((call.get("metadata") or {}).get("lead_id")) or (
        (message.get("metadata") or {}).get("lead_id")
    )

    lead_doc = None
    if lead_id:
        lead_doc = await db.leads.find_one({"id": lead_id})
    if not lead_doc and call_id:
        lead_doc = await db.leads.find_one({"voice_call_id": call_id})
    if not lead_doc:
        log.warning("vapi webhook: no lead for call=%s lead_id=%s", call_id, lead_id)
        raise HTTPException(404, "No lead matches this call")
    lead_id = lead_doc["id"]

    if not await _claim_once(
        f"vapi:{call_id or lead_id}", {"lead_id": lead_id, "kind": "end-of-call-report"}
    ):
        return {"status": "duplicate", "lead_id": lead_id}

    transcript = providers.parse_vapi_transcript(message)
    if not transcript:
        await record_event(
            lead_id,
            "error",
            reason="call.empty_transcript",
            meta={"call_id": call_id, "ended_reason": message.get("endedReason")},
        )
        await touch(lead_id, awaiting_transcript=False)
        if is_legal(lead_doc["status"], "NURTURE"):
            await transition(lead_id, "NURTURE", "call.empty_transcript")
        return {"status": "empty_transcript", "lead_id": lead_id}

    await touch(lead_id, transcript=transcript, awaiting_transcript=False, voice_call_id=call_id)
    await record_event(
        lead_id,
        "call",
        reason="call.transcript_received",
        meta={
            "turns": len(transcript),
            "provider": "vapi",
            "call_id": call_id,
            "duration_seconds": message.get("durationSeconds"),
            "ended_reason": message.get("endedReason"),
        },
    )
    result = await qualify_and_route(lead_id)
    return {"status": "qualified", "lead_id": lead_id, **result}


# ---------- Webhook: inbound Twilio SMS ----------

_STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "revoke", "optout"}


@api.post("/webhooks/twilio-sms")
async def twilio_sms_webhook(request: Request):
    """Inbound SMS. STOP opts the lead out; anything else feeds the supervisor.

    Returns TwiML, which is what Twilio expects as the reply body.
    """
    form = await request.form()
    from_number = (form.get("From") or "").strip()
    text = (form.get("Body") or "").strip()
    message_sid = form.get("MessageSid") or form.get("SmsSid")

    empty_twiml = Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )
    if not from_number:
        return empty_twiml

    lead_doc = await db.leads.find_one({"phone": from_number})
    if not lead_doc:
        log.info("inbound sms from unknown number")
        return empty_twiml
    lead_id = lead_doc["id"]

    if message_sid and not await _claim_once(
        f"twilio:{message_sid}", {"lead_id": lead_id, "kind": "inbound-sms"}
    ):
        return empty_twiml

    normalized = re.sub(r"[^a-z]", "", text.lower())
    if normalized in _STOP_WORDS:
        await db.leads.update_one({"id": lead_id}, {"$set": {"opted_out": True}})
        await record_event(
            lead_id, "note", reason="lead.opted_out", meta={"channel": "sms", "text": text}
        )
        return Response(
            content=(
                '<?xml version="1.0" encoding="UTF-8"?><Response><Message>'
                "You're unsubscribed from EstateX Realty. No further messages will be sent."
                "</Message></Response>"
            ),
            media_type="application/xml",
        )

    transcript = list(lead_doc.get("transcript") or [])
    transcript.append({"role": "lead", "text": text})
    await touch(lead_id, transcript=transcript)
    await record_event(
        lead_id, "note", reason="sms.inbound", meta={"text": text[:500], "sid": message_sid}
    )
    _dispatch_supervisor(lead_id)
    return empty_twiml


def _dispatch_supervisor(lead_id: str) -> None:
    task = asyncio.create_task(run_supervisor(lead_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# ---------- Reads ----------


@api.get("/leads", response_model=list[Lead])
async def list_leads():
    docs = await db.leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [from_mongo(Lead, d) for d in docs]


@api.get("/leads/{lead_id}", response_model=Lead)
async def get_lead(lead_id: str):
    doc = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lead not found")
    return from_mongo(Lead, doc)


@api.get("/leads/{lead_id}/events", response_model=list[Event])
async def get_events(lead_id: str):
    docs = await db.events.find({"lead_id": lead_id}, {"_id": 0}).sort("ts", 1).to_list(500)
    return [from_mongo(Event, d) for d in docs]


@api.get("/leads/{lead_id}/appointments", response_model=list[Appointment])
async def get_appointments(lead_id: str):
    docs = await db.appointments.find({"lead_id": lead_id}, {"_id": 0}).to_list(50)
    return [from_mongo(Appointment, d) for d in docs]


@api.get("/leads/{lead_id}/scheduled", response_model=list[ScheduledAction])
async def get_scheduled(lead_id: str):
    docs = (
        await db.scheduled_actions.find({"lead_id": lead_id}, {"_id": 0})
        .sort("run_at", 1)
        .to_list(50)
    )
    return [from_mongo(ScheduledAction, d) for d in docs]


@api.get("/leads/{lead_id}/slots")
async def get_slots(lead_id: str):
    return await fetch_slots(lead_id)


@api.get("/leads/{lead_id}/checkpoint")
async def get_checkpoint(lead_id: str):
    doc = await db.graph_checkpoints.find_one({"_id": lead_id})
    if not doc:
        return {"state": None, "current_node": None}
    return {"state": doc.get("state"), "current_node": doc.get("current_node")}


# ---------- Actions ----------


@api.post("/leads/{lead_id}/book", response_model=Appointment)
async def book(lead_id: str, req: BookSlotRequest):
    """Reserve a viewing.

    Order matters: legality is checked first, the provider is called second, and
    only a real success flips the lead to BOOKED. Previously the transition and
    the local Appointment happened regardless of what Cal.com returned, so a
    failed booking still rendered as "Booked".
    """
    doc = await db.leads.find_one({"id": lead_id})
    if not doc:
        raise HTTPException(404, "Lead not found")
    if not is_legal(doc["status"], "BOOKED"):
        raise HTTPException(400, f"Illegal transition {doc['status']} -> BOOKED")

    result = await providers.booker.book(
        slot_iso=req.slot_iso, name=doc.get("name", "Lead"), email=doc.get("email")
    )
    if not result.ok:
        await record_provider(result, lead_id, reason="booking.failed", kind="error")
        raise HTTPException(
            502,
            f"Booking rejected by Cal.com (HTTP {result.status}): {result.error}",
        )
    await record_provider(result, lead_id=None)

    appt = Appointment(
        lead_id=lead_id,
        slot_iso=req.slot_iso,
        provider=result.provider,
        external_id=result.data.get("booking_id"),
    )
    await db.appointments.insert_one(to_mongo(appt))
    await transition(lead_id, "BOOKED", "booking.confirmed")
    await record_event(
        lead_id,
        "booking",
        reason="booking.created",
        meta={
            "slot": req.slot_iso,
            "appointment_id": appt.id,
            "external_id": appt.external_id,
            **result.to_meta(),
        },
    )
    return appt


@api.post("/leads/{lead_id}/supervisor")
async def supervisor(lead_id: str):
    return await run_supervisor(lead_id)


@api.post("/leads/{lead_id}/rerun")
async def rerun(lead_id: str, bg: BackgroundTasks):
    """Re-run the pipeline from a clean slate, without lying to the audit log.

    NURTURE is reachable from every status and CALLING is reachable from NURTURE,
    so routing through it keeps the reset inside the state machine instead of
    writing ``status: NEW`` straight into Mongo.
    """
    doc = await db.leads.find_one({"id": lead_id})
    if not doc:
        raise HTTPException(404, "Lead not found")
    await record_event(
        lead_id, "note", from_status=doc["status"], reason="pipeline.reset"
    )
    await transition(lead_id, "NURTURE", "pipeline.reset")
    await touch(
        lead_id,
        score=0,
        qualification=None,
        transcript=[],
        awaiting_transcript=False,
        voice_call_id=None,
    )
    bg.add_task(run_ai_pipeline, lead_id)
    return {"ok": True}


@api.post("/leads/{lead_id}/approve")
async def approve_lead(lead_id: str):
    result = await run_supervisor(lead_id, approve=True)
    await db.leads.update_one({"id": lead_id}, {"$set": {"pending_approval": False}})
    return result


@api.post("/leads/{lead_id}/reject")
async def reject_lead(lead_id: str):
    result = await run_supervisor(lead_id, approve=False)
    await db.leads.update_one({"id": lead_id}, {"$set": {"pending_approval": False}})
    lead_doc = await db.leads.find_one({"id": lead_id})
    if lead_doc and lead_doc["status"] == "HOT":
        try:
            await transition(lead_id, "NURTURE", reason="escalation.rejected")
        except HTTPException:
            pass
    return result


@api.post("/leads/{lead_id}/opt-out")
async def opt_out(lead_id: str):
    result = await db.leads.update_one({"id": lead_id}, {"$set": {"opted_out": True}})
    if not result.matched_count:
        raise HTTPException(404, "Lead not found")
    await record_event(lead_id, "note", reason="lead.opted_out")
    return {"ok": True}


# ---------- Autonomy ----------


@api.post("/tick", dependencies=[Depends(require_admin)])
async def tick(limit: int = 25):
    """Drive one autonomy pass. Called by cron every ~10 minutes.

    The response is the demo artifact: it says exactly what the system did while
    nobody was watching.
    """
    return await run_tick(limit=limit)


# ---------- Analytics ----------

FUNNEL_ORDER = ["NEW", "CALLING", "IN_CONVERSATION", "QUALIFIED", "NURTURE", "HOT", "BOOKED"]


@api.get("/analytics")
async def analytics():
    rows = await db.leads.aggregate(
        [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    ).to_list(20)
    counts = {r["_id"]: r["count"] for r in rows if r.get("_id")}
    total = sum(counts.values())
    booked = counts.get("BOOKED", 0)
    return {
        "total": total,
        "booked": booked,
        "qualified": counts.get("QUALIFIED", 0) + counts.get("HOT", 0) + booked,
        "hot": counts.get("HOT", 0),
        "conversion_rate": round((booked / total) * 100, 1) if total else 0.0,
        "funnel": [{"status": s, "count": counts.get(s, 0)} for s in FUNNEL_ORDER],
    }


# ---------- Demo data ----------

SEED_LEADS = [
    ("Emily Chen", "+14155550101", "emily.chen@example.com"),
    ("Marcus Reed", "+14155550102", "marcus.reed@example.com"),
    ("Priya Sharma", "+919876543210", "priya.s@example.com"),
    ("Diego Alvarez", "+14155550104", "diego.a@example.com"),
    ("Aisha Bello", "+14155550105", "aisha.b@example.com"),
    ("Jonas Weber", "+14155550106", "jonas.w@example.com"),
    ("Sofia Rossi", "+14155550107", "sofia.r@example.com"),
    ("Kenji Tanaka", "+14155550108", "kenji.t@example.com"),
    ("Nadia Al-Farsi", "+14155550109", "nadia.a@example.com"),
    ("Owen Fitzgerald", "+14155550110", "owen.f@example.com"),
    ("Beatrice Laurent", "+14155550111", "bea.l@example.com"),
    ("Riya Kapoor", "+919812345678", "riya.k@example.com"),
    ("Samuel Okafor", "+14155550113", "sam.o@example.com"),
    ("Isabella Costa", "+14155550114", "isabella.c@example.com"),
    ("Theo Nakamura", "+14155550115", "theo.n@example.com"),
]


@api.post("/seed", dependencies=[Depends(require_admin)])
async def seed(bg: BackgroundTasks):
    created = 0
    for name, phone, email in SEED_LEADS:
        if await db.leads.find_one({"phone": phone}):
            continue
        lead = Lead(name=name, phone=phone, email=email, source="seed")
        await db.leads.insert_one(to_mongo(lead))
        await record_event(lead.id, "note", reason="lead.seeded")
        bg.add_task(run_ai_pipeline, lead.id)
        created += 1
    return {"created": created}


@api.delete("/reset", dependencies=[Depends(require_admin)])
async def reset():
    for coll in (
        "leads",
        "events",
        "appointments",
        "graph_checkpoints",
        "scheduled_actions",
        "webhook_receipts",
        "provider_health",
    ):
        await db[coll].delete_many({})
    return {"ok": True}


# ---------- Simulation harness ----------

SIM_LEADS = [
    ("Sim Alpha", "+14155551001", "a1@x.com"),
    ("Sim Bravo", "+14155551002", "a2@x.com"),
    ("Sim Charlie", "+14155551003", "a3@x.com"),
    ("Sim Delta", "+14155551004", "a4@x.com"),
    ("Sim Echo", "+14155551005", "a5@x.com"),
    ("Sim Foxtrot", "+14155551006", "a6@x.com"),
    ("Sim Golf", "+14155551007", "a7@x.com"),
    ("Sim Hotel", "+14155551008", "a8@x.com"),
    ("Sim India", "+14155551009", "a9@x.com"),
    ("Sim Juliet", "+14155551010", "a10@x.com"),
    ("Sim Kilo", "+14155551011", "a11@x.com"),
    ("Sim Lima", "+14155551012", "a12@x.com"),
    ("Sim Mike", "+14155551013", "a13@x.com"),
    ("Sim November", "+14155551014", "a14@x.com"),
    ("Sim Oscar", "+14155551015", "a15@x.com"),
]


@api.post("/simulate", dependencies=[Depends(require_admin)])
async def simulate(bg: BackgroundTasks):
    """Run 15 scripted leads through the pipeline for eval.

    Profiles are assigned round-robin rather than at random so every scripted
    conversation is covered and the run is reproducible.
    """
    created = 0
    for i, (name, phone, email) in enumerate(SIM_LEADS):
        if await db.leads.find_one({"phone": phone}):
            continue
        lead = Lead(
            name=name,
            phone=phone,
            email=email,
            source="sim",
            sim_profile=i % providers.MOCK_PROFILE_COUNT,
        )
        await db.leads.insert_one(to_mongo(lead))
        await record_event(
            lead.id, "note", reason="lead.simulated", meta={"profile": lead.sim_profile}
        )
        bg.add_task(run_ai_pipeline, lead.id)
        created += 1
    return {"created": created, "total": len(SIM_LEADS)}


@api.get("/eval")
async def eval_run():
    """Score the pipeline against the deterministic rubric on the same transcript.

    Ground truth is derived, not declared: for each simulated lead we re-extract
    the answers from its own transcript with :func:`extract_answers` and run the
    rubric. The graded number is therefore *agreement between the LLM-driven
    qualification and the rule-based baseline on identical input* — which is a
    real measurement of extraction fidelity.

    With no ``GROQ_API_KEY`` both sides are the same code path, so agreement is
    trivially 1.0. ``baseline_only`` says so rather than passing the figure off
    as model accuracy.
    """
    docs = await db.leads.find({"source": "sim"}, {"_id": 0}).to_list(100)
    agree = 0
    graded = 0
    hallucinated = 0
    disagreements = []

    for d in docs:
        transcript = d.get("transcript") or []
        if not transcript or d["status"] not in ("QUALIFIED", "HOT", "NURTURE", "BOOKED"):
            continue
        graded += 1
        baseline_q = Qualification(**extract_answers(transcript))
        expected = classify_score(_fallback_score(baseline_q))
        actual = "HOT" if d["status"] == "BOOKED" and expected == "HOT" else d["status"]
        if actual == expected:
            agree += 1
        else:
            disagreements.append(
                {"lead_id": d["id"], "expected": expected, "actual": d["status"], "score": d.get("score")}
            )

        # Cheap grounding check: a qualification value that appears nowhere in
        # the transcript was invented rather than extracted.
        text = " ".join(t.get("text", "") for t in transcript).lower()
        q = d.get("qualification") or {}
        for field_name in ("budget", "area", "timeline"):
            v = (q.get(field_name) or "").lower()
            if v and len(v) > 3 and v not in text:
                hallucinated += 1
                break

    return {
        "graded": graded,
        "agreements": agree,
        "rubric_agreement": round(agree / graded, 3) if graded else 0.0,
        "hallucination_rate": round(hallucinated / graded, 3) if graded else 0.0,
        "booking_rate": round(
            sum(1 for d in docs if d["status"] == "BOOKED") / len(docs), 3
        )
        if docs
        else 0.0,
        "sample_size": len(docs),
        "baseline_only": providers.provider_status("groq")["mode"] == "MOCK",
        "disagreements": disagreements[:10],
    }


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
