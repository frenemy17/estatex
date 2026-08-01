"""AI Real-Estate Lead Qualifier — FastAPI backend.

Deterministic backbone: state machine + audit log.
Agentic layer: LLM qualification via Groq API (llama-3.3-70b-versatile).
Providers (Voice, Booking, Notification, CRM) are mocked but pluggable.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from dotenv import load_dotenv
import google.generativeai as genai
import requests
from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("lead-qualifier")

# ---------- DB ----------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
GOOGLE_LEADS_WEBHOOK_KEY = os.environ.get("GOOGLE_LEADS_WEBHOOK_KEY", "change-me-in-google-ads")
QUIET_HOURS_START = int(os.environ.get("QUIET_HOURS_START", "21"))  # 9pm UTC
QUIET_HOURS_END = int(os.environ.get("QUIET_HOURS_END", "8"))  # 8am UTC


def clog(lead_id: str | None = None) -> logging.LoggerAdapter:
    """Correlation-id logger — every message tagged with [lead=<id>]."""
    return logging.LoggerAdapter(log, {"lead_id": lead_id or "-"})


# Patch base formatter to include lead_id when present
for handler in logging.getLogger().handlers:
    handler.setFormatter(
        logging.Formatter("%(asctime)s [lead=%(lead_id)s] %(name)s %(levelname)s %(message)s", defaults={"lead_id": "-"})
    )


# ---------- Constants: state machine ----------
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
    "weights": {
        "intent": 25,
        "budget": 25,
        "timeline": 20,
        "financing": 15,
        "area": 15,
    },
}

QUESTIONS = [
    "What kind of property are you looking for (buy, rent, invest)?",
    "What is your approximate budget range?",
    "What is your timeline — are you looking to move in the next few months?",
    "Do you already have financing/pre-approval in place?",
    "Which neighborhoods or areas are you focused on?",
]

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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LeadCreate(BaseModel):
    name: str
    phone: str
    email: Optional[EmailStr] = None
    source: str = "web"
    notes: Optional[str] = None


class Event(BaseDoc):
    lead_id: str
    kind: str  # transition | note | call | booking | followup | supervisor
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    reason: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Appointment(BaseDoc):
    lead_id: str
    slot_iso: str
    duration_min: int = 30
    provider: str = "mock-calcom"
    status: str = "BOOKED"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BookSlotRequest(BaseModel):
    slot_iso: str


# ---------- Serialization helpers ----------


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


# ---------- State machine ----------


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


async def transition(lead_id: str, new_status: str, reason: str = "") -> Lead:
    lead_doc = await db.leads.find_one({"id": lead_id})
    if not lead_doc:
        raise HTTPException(404, "Lead not found")
    lead = from_mongo(Lead, lead_doc)
    if new_status == lead.status:
        return lead
    if new_status not in ALLOWED_TRANSITIONS.get(lead.status, set()):
        raise HTTPException(
            400,
            f"Illegal transition {lead.status} -> {new_status}",
        )
    old = lead.status
    lead.status = new_status  # type: ignore[assignment]
    lead.updated_at = datetime.now(timezone.utc)
    await db.leads.update_one(
        {"id": lead_id},
        {"$set": {"status": new_status, "updated_at": lead.updated_at.isoformat()}},
    )
    await record_event(lead_id, "transition", old, new_status, reason)
    log.info("lead=%s transition %s -> %s (%s)", lead_id, old, new_status, reason)
    return lead


# ---------- Providers (mocked, pluggable) ----------


class VoiceProvider:
    async def start_call(self, lead: Lead) -> dict:
        vapi_key = os.environ.get("VAPI_API_KEY")
        phone_id = os.environ.get("VAPI_PHONE_NUMBER_ID")
        assistant_id = os.environ.get("VAPI_ASSISTANT_ID")
        
        if vapi_key and phone_id:
            try:
                payload = {
                    "phoneNumberId": phone_id,
                    "customer": {"number": lead.phone, "name": lead.name},
                }
                if assistant_id:
                    payload["assistantId"] = assistant_id
                else:
                    payload["assistant"] = {
                        "firstMessage": f"Hi {lead.name}, this is Ava from EstateX Realty. Do you have a moment to discuss your home search?",
                        "model": {
                            "provider": "groq",
                            "model": "llama-3.3-70b-versatile",
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "You are Ava, a real-estate concierge for EstateX Realty. Qualify the buyer by asking property type (buy, rent, invest), budget, timeline, financing pre-approval, and target neighborhood."
                                }
                            ]
                        }
                    }

                res = await asyncio.to_thread(
                    requests.post,
                    "https://api.vapi.ai/call/phone",
                    headers={
                        "Authorization": f"Bearer {vapi_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=10,
                )
                data = res.json()
                log.info("vapi call dispatched: %s", data.get("id"))
                return {"transcript": [], "provider": "vapi", "call_id": data.get("id")}
            except Exception as e:
                log.warning("vapi call failed, falling back to mock: %s", e)

        # Mock a realistic sample transcript
        samples = [
            {
                "budget": "$650k-750k",
                "intent": "buy primary residence",
                "timeline": "next 2 months",
                "financing": "pre-approved",
                "area": "Downtown / East Village",
            },
            {
                "budget": "$300k",
                "intent": "investment property",
                "timeline": "just researching",
                "financing": "not yet",
                "area": "Suburbs",
            },
            {
                "budget": "$1.2M",
                "intent": "buy family home",
                "timeline": "urgent, within 30 days",
                "financing": "cash buyer",
                "area": "Riverside, Oak Park",
            },
            {
                "budget": "unsure",
                "intent": "rent",
                "timeline": "6+ months",
                "financing": "renting",
                "area": "undecided",
            },
        ]
        s = random.choice(samples)
        transcript = [
            {"role": "agent", "text": f"Hi {lead.name}, this is Ava from EstateX Realty."},
            {"role": "lead", "text": "Sure, go ahead."},
            {"role": "agent", "text": QUESTIONS[0]},
            {"role": "lead", "text": s["intent"]},
            {"role": "agent", "text": QUESTIONS[1]},
            {"role": "lead", "text": s["budget"]},
            {"role": "agent", "text": QUESTIONS[2]},
            {"role": "lead", "text": s["timeline"]},
            {"role": "agent", "text": QUESTIONS[3]},
            {"role": "lead", "text": s["financing"]},
            {"role": "agent", "text": QUESTIONS[4]},
            {"role": "lead", "text": s["area"]},
        ]
        return {"transcript": transcript, "provider": "mock-vapi"}


class BookingProvider:
    async def get_slots(self, lead_id: str) -> list[str]:
        cal_key = os.environ.get("CAL_API_KEY")
        event_type_id = os.environ.get("CAL_EVENT_TYPE_ID")

        if cal_key and event_type_id:
            try:
                start = datetime.now(timezone.utc).isoformat()
                end = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
                res = await asyncio.to_thread(
                    requests.get,
                    f"https://api.cal.com/v1/slots?apiKey={cal_key}&eventTypeId={event_type_id}&startTime={start}&endTime={end}",
                    timeout=10,
                )
                data = res.json()
                slots = [s["start"] for day in data.get("slots", {}).values() for s in day]
                if slots:
                    return slots[:9]
            except Exception as e:
                log.warning("cal.com slots failed, falling back to mock: %s", e)

        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        return [
            (now + timedelta(days=d, hours=h)).isoformat()
            for d in (1, 2, 3)
            for h in (10, 14, 16)
        ]

    async def book(self, lead_id: str, slot_iso: str) -> Appointment:
        cal_key = os.environ.get("CAL_API_KEY")
        event_type_id = os.environ.get("CAL_EVENT_TYPE_ID")
        provider_name = "mock-calcom"

        if cal_key and event_type_id:
            try:
                lead_doc = await db.leads.find_one({"id": lead_id})
                res = await asyncio.to_thread(
                    requests.post,
                    f"https://api.cal.com/v1/bookings?apiKey={cal_key}",
                    json={
                        "eventTypeId": int(event_type_id),
                        "start": slot_iso,
                        "responses": {
                            "name": lead_doc.get("name", "Lead"),
                            "email": lead_doc.get("email", "lead@example.com"),
                        },
                    },
                    timeout=10,
                )
                if res.status_code in (200, 201):
                    provider_name = "cal.com"
            except Exception as e:
                log.warning("cal.com booking failed, falling back to mock: %s", e)

        appt = Appointment(lead_id=lead_id, slot_iso=slot_iso, provider=provider_name)
        await db.appointments.insert_one(to_mongo(appt))
        return appt


class NotificationProvider:
    def _in_quiet_hours(self) -> bool:
        h = datetime.now(timezone.utc).hour
        if QUIET_HOURS_START <= QUIET_HOURS_END:
            return QUIET_HOURS_START <= h < QUIET_HOURS_END
        return h >= QUIET_HOURS_START or h < QUIET_HOURS_END

    async def send(
        self, lead, channel: str, template: str, ctx: dict | None = None
    ) -> dict:
        lead_id = getattr(lead, "id", None) or (lead.get("id") if isinstance(lead, dict) else None)
        # Enforce opt-out
        doc = await db.leads.find_one({"id": lead_id}, {"opted_out": 1})
        if doc and doc.get("opted_out"):
            await record_event(
                lead_id, "followup", reason=f"{channel}/{template}",
                meta={"blocked": "opted_out", "provider": "notifier"},
            )
            return {"blocked": "opted_out"}

        # Enforce quiet hours
        if self._in_quiet_hours():
            defer_until = datetime.now(timezone.utc).replace(hour=QUIET_HOURS_END, minute=0, second=0, microsecond=0)
            if defer_until < datetime.now(timezone.utc):
                defer_until += timedelta(days=1)
            payload = {
                "channel": channel,
                "template": template,
                "deferred_until": defer_until.isoformat(),
                "provider": "notifier",
                "ctx": ctx or {},
            }
            await record_event(
                lead_id, "followup", meta=payload, reason=f"{channel}/{template}/deferred"
            )
            return payload

        provider_used = "mock-notif"
        recipient = getattr(lead, "phone", None) if channel == "sms" else getattr(lead, "email", None)

        # Real Email via Resend
        if channel == "email" and os.environ.get("RESEND_API_KEY"):
            try:
                resend_key = os.environ["RESEND_API_KEY"]
                from_email = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")
                body = (ctx or {}).get("body", f"Hello {(getattr(lead, 'name', 'there'))}, following up on your property search.")
                subject = (ctx or {}).get("subject", "Real Estate Update")
                res = await asyncio.to_thread(
                    requests.post,
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                    json={"from": from_email, "to": [recipient], "subject": subject, "html": f"<p>{body}</p>"},
                    timeout=10,
                )
                if res.status_code in (200, 201):
                    provider_used = "resend"
            except Exception as e:
                log.warning("resend email failed: %s", e)

        # Real SMS via Twilio
        elif channel == "sms" and os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN"):
            try:
                sid = os.environ["TWILIO_ACCOUNT_SID"]
                token = os.environ["TWILIO_AUTH_TOKEN"]
                from_phone = os.environ["TWILIO_PHONE_NUMBER"]
                body = (ctx or {}).get("body", f"Hi {(getattr(lead, 'name', 'there'))}, thanks for reaching out to EstateX Realty!")
                res = await asyncio.to_thread(
                    requests.post,
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                    auth=(sid, token),
                    data={"From": from_phone, "To": recipient, "Body": body},
                    timeout=10,
                )
                if res.status_code in (200, 201):
                    provider_used = "twilio"
            except Exception as e:
                log.warning("twilio sms failed: %s", e)

        payload = {
            "channel": channel,
            "template": template,
            "to": recipient,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider_used,
            "ctx": ctx or {},
        }
        await record_event(
            lead_id, "followup", meta=payload, reason=f"{channel}/{template}"
        )
        return payload


class CRMProvider:
    async def upsert_contact(self, lead: Lead) -> dict:
        token = os.environ.get("HUBSPOT_ACCESS_TOKEN")
        if token:
            try:
                first = lead.name.split()[0] if lead.name else ""
                last = " ".join(lead.name.split()[1:]) if len(lead.name.split()) > 1 else ""
                res = await asyncio.to_thread(
                    requests.post,
                    "https://api.hubspot.com/crm/v3/objects/contacts",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={
                        "properties": {
                            "firstname": first,
                            "lastname": last,
                            "phone": lead.phone,
                            "email": lead.email or "",
                        }
                    },
                    timeout=10,
                )
                log.info("hubspot contact upserted: %s", res.status_code)
                await record_event(lead.id, "note", reason="crm.contact_upserted", meta={"provider": "hubspot"})
                return {"ok": True, "provider": "hubspot"}
            except Exception as e:
                log.warning("hubspot upsert failed: %s", e)

        await record_event(
            lead.id, "note", reason="crm.contact_upserted", meta={"provider": "mock-hubspot"}
        )
        return {"ok": True, "provider": "mock-hubspot"}

    async def create_deal(self, lead: Lead) -> dict:
        token = os.environ.get("HUBSPOT_ACCESS_TOKEN")
        if token:
            try:
                res = await asyncio.to_thread(
                    requests.post,
                    "https://api.hubspot.com/crm/v3/objects/deals",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={
                        "properties": {
                            "dealname": f"Deal — {lead.name}",
                            "pipeline": "default",
                            "dealstage": "appointmentscheduled" if lead.status == "HOT" else "qualifiedtobuy",
                        }
                    },
                    timeout=10,
                )
                log.info("hubspot deal created: %s", res.status_code)
                await record_event(lead.id, "note", reason="crm.deal_created", meta={"provider": "hubspot", "score": lead.score})
                return {"ok": True, "provider": "hubspot"}
            except Exception as e:
                log.warning("hubspot deal failed: %s", e)

        await record_event(
            lead.id,
            "note",
            reason="crm.deal_created",
            meta={"provider": "mock-hubspot", "score": lead.score},
        )
        return {"ok": True, "provider": "mock-hubspot"}


voice = VoiceProvider()
booker = BookingProvider()
notifier = NotificationProvider()
crm = CRMProvider()


# ---------- LLM Qualifier ----------


def _fallback_score(q: Qualification) -> int:
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


async def qualify_with_llm(lead: Lead) -> tuple[Qualification, int]:
    """Call LLM (Groq or Gemini) to extract structured qualification + reasoning."""
    convo = "\n".join(f"{m['role'].upper()}: {m['text']}" for m in lead.transcript)
    sys_msg = (
        "You are an elite real-estate lead qualification analyst. "
        "Extract structured buyer qualification data from a conversation "
        "and return STRICT JSON only (no markdown, no prose)."
    )
    user_text = (
        "Given this real-estate lead conversation, return a JSON object with "
        "keys: intent, budget, timeline, financing, area, reasoning. "
        "Each is a short string. `reasoning` explains the qualification in 1-2 sentences.\n\n"
        f"Conversation:\n{convo}\n\nRespond with JSON only."
    )

    lead_answers = [m["text"] for m in lead.transcript if m["role"] == "lead"]
    fallback_q = Qualification(
        intent=lead_answers[0] if len(lead_answers) > 0 else None,
        budget=lead_answers[1] if len(lead_answers) > 1 else None,
        timeline=lead_answers[2] if len(lead_answers) > 2 else None,
        financing=lead_answers[3] if len(lead_answers) > 3 else None,
        area=lead_answers[4] if len(lead_answers) > 4 else None,
        reasoning="Fallback extraction (LLM unavailable).",
    )

    key = os.environ.get("GROQ_API_KEY") or EMERGENT_LLM_KEY
    if key and key.startswith("gsk_"):
        try:
            res = await asyncio.to_thread(
                requests.post,
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_text},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
                timeout=10,
            )
            data = res.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            q = Qualification(**{k: str(v) for k, v in parsed.items() if k in Qualification.model_fields})
        except Exception as e:  # noqa: BLE001
            log.warning("Groq qualification fallback for lead=%s: %s", lead.id, e)
            q = fallback_q
    else:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-2.0-flash", system_instruction=sys_msg)
            resp = await model.generate_content_async(user_text)
            text = resp.text
            cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
            match = re.search(r"\{[\s\S]*\}", cleaned)
            data = json.loads(match.group(0) if match else cleaned)
            q = Qualification(**{k: str(v) for k, v in data.items() if k in Qualification.model_fields})
        except Exception as e:  # noqa: BLE001
            log.warning("LLM qualification fallback for lead=%s: %s", lead.id, e)
            q = fallback_q

    score = _fallback_score(q)
    return q, score


def classify_score(score: int) -> str:
    if score >= 85:
        return "HOT"
    if score >= QUALIFICATION_RUBRIC["threshold_qualified"]:
        return "QUALIFIED"
    if score < QUALIFICATION_RUBRIC["threshold_nurture"]:
        return "NURTURE"
    return "NURTURE"


# ---------- Background pipeline ----------


async def run_ai_pipeline(lead_id: str) -> None:
    """v1 automation: CALLING -> IN_CONVERSATION -> qualify -> classify -> follow-up."""
    try:
        await transition(lead_id, "CALLING", "ai.dispatch")
        await asyncio.sleep(1.2)  # simulate call latency
        lead_doc = await db.leads.find_one({"id": lead_id})
        lead = from_mongo(Lead, lead_doc)
        call = await voice.start_call(lead)
        lead.transcript = call["transcript"]
        lead.attempt_history.append(
            {"kind": "call", "provider": call["provider"], "ts": datetime.now(timezone.utc).isoformat()}
        )
        await db.leads.update_one(
            {"id": lead_id},
            {"$set": {"transcript": lead.transcript, "attempt_history": lead.attempt_history}},
        )
        await record_event(lead_id, "call", meta={"turns": len(lead.transcript)})
        await transition(lead_id, "IN_CONVERSATION", "voice.completed")

        q, score = await qualify_with_llm(lead)
        final_status = classify_score(score)
        await db.leads.update_one(
            {"id": lead_id},
            {
                "$set": {
                    "qualification": q.model_dump(),
                    "score": score,
                }
            },
        )
        await record_event(
            lead_id,
            "note",
            reason="qualification.completed",
            meta={"score": score, "qualification": q.model_dump()},
        )
        await transition(lead_id, final_status, f"score={score}")

        # CRM sync + follow up
        lead_doc = await db.leads.find_one({"id": lead_id})
        lead = from_mongo(Lead, lead_doc)
        await crm.upsert_contact(lead)
        if final_status in ("QUALIFIED", "HOT"):
            await crm.create_deal(lead)
            await notifier.send(
                lead, "sms", "book_slot", {"suggestion": "tomorrow 2pm"}
            )
        else:
            await notifier.send(lead, "email", "nurture_sequence")
    except Exception as e:  # noqa: BLE001
        log.exception("ai pipeline failed: %s", e)
        await record_event(lead_id, "note", reason=f"pipeline.error: {e}")


# ---------- Supervisor (v2: real LangGraph-style graph) ----------


def _dispatch_pipeline_sync(lead_id: str) -> None:
    """Fire-and-forget pipeline dispatch used by the graph 'call' node."""
    asyncio.create_task(run_ai_pipeline(lead_id))


# Compiled graph is built lazily so the DB + notifier are ready.
_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        from agents.supervisor import build_supervisor_graph  # local import

        _compiled_graph = build_supervisor_graph(db, notifier, _dispatch_pipeline_sync)
    return _compiled_graph


async def run_supervisor(lead_id: str, approve: bool | None = None) -> dict:
    """Invoke the compiled graph. If approve is set, resume from interrupt with approval."""
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

    # Persist trace + pending_approval on the lead doc for UI
    existing = lead_doc.get("supervisor_trace") or []
    merged_trace = existing + [s for s in state.get("trace", []) if s not in existing]
    await db.leads.update_one(
        {"id": lead_id},
        {"$set": {
            "supervisor_trace": merged_trace,
            "pending_approval": bool(state.get("requires_approval") and state.get("_interrupt_at")),
        }},
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
        "requires_approval": bool(state.get("requires_approval") and state.get("_interrupt_at")),
        "enrichment": state.get("enrichment"),
        "followup_plan": state.get("followup_plan"),
    }


# ---------- API ----------


app = FastAPI(title="AI Lead Qualifier")
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"service": "ai-lead-qualifier", "status": "ok"}


async def _ingest_lead(
    name: str,
    phone: str,
    email: str | None,
    source: str,
    bg: BackgroundTasks,
    extra_meta: dict | None = None,
) -> Lead:
    """Shared ingestion pipeline: dedupe by phone, insert, dispatch AI."""
    existing = await db.leads.find_one({"phone": phone})
    if existing:
        return from_mongo(Lead, existing)
    lead = Lead(name=name, phone=phone, email=email, source=source)
    await db.leads.insert_one(to_mongo(lead))
    await record_event(
        lead.id,
        "note",
        reason="lead.captured",
        meta={"source": source, **(extra_meta or {})},
    )
    bg.add_task(run_ai_pipeline, lead.id)
    return lead


@api.post("/lead", response_model=Lead)
async def create_lead(payload: LeadCreate, bg: BackgroundTasks):
    return await _ingest_lead(
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        source=payload.source,
        bg=bg,
    )


@api.post("/leads/bulk")
async def bulk_create_leads(payload: list[LeadCreate], bg: BackgroundTasks):
    results = []
    for p in payload:
        lead = await _ingest_lead(
            name=p.name,
            phone=p.phone,
            email=p.email,
            source=p.source or "csv_import",
            bg=bg,
        )
        results.append(lead)
    return {"imported": len(results), "leads": results}


# ---------- Webhook: Google Ads Lead Form Extensions ----------
#
# Google POSTs a JSON body shaped like:
# {
#   "lead_id": "...",
#   "api_version": "1.0",
#   "form_id": 1234,
#   "campaign_id": 5678,
#   "google_key": "<pre-shared secret>",
#   "is_test": false,
#   "user_column_data": [
#       {"column_id": "FULL_NAME",    "column_name": "Full name", "string_value": "Jane Doe"},
#       {"column_id": "EMAIL",        "column_name": "Email",     "string_value": "jane@x.com"},
#       {"column_id": "PHONE_NUMBER", "column_name": "Phone",     "string_value": "+14155550100"}
#   ]
# }
#
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
    # 1. Verify the pre-shared key
    if payload.google_key != GOOGLE_LEADS_WEBHOOK_KEY:
        log.warning("google-leads webhook rejected: bad key")
        raise HTTPException(status_code=401, detail="Invalid google_key")

    # 2. Extract fields (Google uses FULL_NAME / EMAIL / PHONE_NUMBER column ids;
    #    fall back to FIRST_NAME + LAST_NAME if a FULL_NAME isn't sent).
    cols = payload.user_column_data
    name = _pick(cols, "FULL_NAME")
    if not name:
        first = _pick(cols, "FIRST_NAME") or ""
        last = _pick(cols, "LAST_NAME") or ""
        name = f"{first} {last}".strip() or None
    email = _pick(cols, "EMAIL")
    phone = _pick(cols, "PHONE_NUMBER")

    if not phone or not name:
        raise HTTPException(status_code=422, detail="Missing FULL_NAME or PHONE_NUMBER")

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
    log.info(
        "google-leads webhook accepted: lead=%s source=%s form=%s",
        lead.id, source, payload.form_id,
    )
    # Google Ads expects a 2xx within 5 seconds and does not read the body.
    return {"lead_id": lead.id, "status": "accepted"}


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


@api.get("/leads/{lead_id}/slots")
async def get_slots(lead_id: str):
    slots = await booker.get_slots(lead_id)
    return {"slots": slots}


@api.post("/leads/{lead_id}/book", response_model=Appointment)
async def book(lead_id: str, req: BookSlotRequest):
    doc = await db.leads.find_one({"id": lead_id})
    if not doc:
        raise HTTPException(404, "Lead not found")
    # transition first (validates legal)
    await transition(lead_id, "BOOKED", "booking.confirmed")
    appt = await booker.book(lead_id, req.slot_iso)
    await record_event(
        lead_id, "booking", meta={"slot": req.slot_iso, "appointment_id": appt.id}
    )
    return appt


@api.post("/leads/{lead_id}/supervisor")
async def supervisor(lead_id: str):
    return await run_supervisor(lead_id)


@api.post("/leads/{lead_id}/rerun")
async def rerun(lead_id: str, bg: BackgroundTasks):
    # Reset for demo comparison
    await db.leads.update_one(
        {"id": lead_id},
        {"$set": {"status": "NEW", "score": 0, "qualification": None, "transcript": []}},
    )
    await record_event(lead_id, "note", reason="pipeline.reset")
    bg.add_task(run_ai_pipeline, lead_id)
    return {"ok": True}


@api.get("/analytics")
async def analytics():
    total = await db.leads.count_documents({})
    booked = await db.leads.count_documents({"status": "BOOKED"})
    qualified = await db.leads.count_documents({"status": {"$in": ["QUALIFIED", "HOT", "BOOKED"]}})
    hot = await db.leads.count_documents({"status": "HOT"})
    # Funnel counts
    statuses = ["NEW", "CALLING", "IN_CONVERSATION", "QUALIFIED", "NURTURE", "HOT", "BOOKED"]
    funnel = []
    for s in statuses:
        c = await db.leads.count_documents({"status": s})
        funnel.append({"status": s, "count": c})
    return {
        "total": total,
        "booked": booked,
        "qualified": qualified,
        "hot": hot,
        "conversion_rate": round((booked / total) * 100, 1) if total else 0.0,
        "funnel": funnel,
    }


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


@api.post("/seed")
async def seed(bg: BackgroundTasks):
    created = 0
    for name, phone, email in SEED_LEADS:
        exists = await db.leads.find_one({"phone": phone})
        if exists:
            continue
        lead = Lead(name=name, phone=phone, email=email, source="seed")
        await db.leads.insert_one(to_mongo(lead))
        await record_event(lead.id, "note", reason="lead.seeded")
        bg.add_task(run_ai_pipeline, lead.id)
        created += 1
    return {"created": created}


@api.delete("/reset")
async def reset():
    await db.leads.delete_many({})
    await db.events.delete_many({})
    await db.appointments.delete_many({})
    await db.graph_checkpoints.delete_many({})
    return {"ok": True}


# ---------- Approval / opt-out / supervisor helpers ----------


@api.post("/leads/{lead_id}/approve")
async def approve_lead(lead_id: str):
    result = await run_supervisor(lead_id, approve=True)
    await db.leads.update_one({"id": lead_id}, {"$set": {"pending_approval": False}})
    return result


@api.post("/leads/{lead_id}/reject")
async def reject_lead(lead_id: str):
    result = await run_supervisor(lead_id, approve=False)
    await db.leads.update_one({"id": lead_id}, {"$set": {"pending_approval": False}})
    # Reverting: move a HOT lead back to NURTURE
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


@api.get("/leads/{lead_id}/checkpoint")
async def get_checkpoint(lead_id: str):
    doc = await db.graph_checkpoints.find_one({"_id": lead_id})
    if not doc:
        return {"state": None, "current_node": None}
    return {"state": doc.get("state"), "current_node": doc.get("current_node")}


# ---------- Simulation harness ----------


SIM_LEADS = [
    # (name, phone, email, ground_truth_class)
    ("Sim Alpha", "+14155551001", "a1@x.com", "HOT"),
    ("Sim Bravo", "+14155551002", "a2@x.com", "QUALIFIED"),
    ("Sim Charlie", "+14155551003", "a3@x.com", "NURTURE"),
    ("Sim Delta", "+14155551004", "a4@x.com", "HOT"),
    ("Sim Echo", "+14155551005", "a5@x.com", "QUALIFIED"),
    ("Sim Foxtrot", "+14155551006", "a6@x.com", "NURTURE"),
    ("Sim Golf", "+14155551007", "a7@x.com", "HOT"),
    ("Sim Hotel", "+14155551008", "a8@x.com", "QUALIFIED"),
    ("Sim India", "+14155551009", "a9@x.com", "NURTURE"),
    ("Sim Juliet", "+14155551010", "a10@x.com", "HOT"),
    ("Sim Kilo", "+14155551011", "a11@x.com", "QUALIFIED"),
    ("Sim Lima", "+14155551012", "a12@x.com", "NURTURE"),
    ("Sim Mike", "+14155551013", "a13@x.com", "HOT"),
    ("Sim November", "+14155551014", "a14@x.com", "QUALIFIED"),
    ("Sim Oscar", "+14155551015", "a15@x.com", "NURTURE"),
]


@api.post("/simulate")
async def simulate(bg: BackgroundTasks):
    """Run 15 scripted leads through the pipeline for eval."""
    created = 0
    for name, phone, email, _gt in SIM_LEADS:
        if await db.leads.find_one({"phone": phone}):
            continue
        lead = Lead(name=name, phone=phone, email=email, source="sim")
        await db.leads.insert_one(to_mongo(lead))
        await record_event(lead.id, "note", reason="lead.simulated")
        bg.add_task(run_ai_pipeline, lead.id)
        created += 1
    return {"created": created, "total": len(SIM_LEADS)}


@api.get("/eval")
async def eval_run():
    """Return qualification accuracy, booking rate, and hallucination proxy."""
    sim_phones = [p for _, p, _, _ in SIM_LEADS]
    gt = {p: cls for _, p, _, cls in SIM_LEADS}
    docs = await db.leads.find({"phone": {"$in": sim_phones}}, {"_id": 0}).to_list(50)
    correct = 0
    total_graded = 0
    hallucination_hits = 0
    for d in docs:
        actual = d["status"]
        expected = gt[d["phone"]]
        # Grade only if pipeline finished at a terminal class (not CALLING/IN_CONV)
        if actual in ("QUALIFIED", "HOT", "NURTURE", "BOOKED"):
            total_graded += 1
            terminal = "HOT" if expected == "HOT" and actual in ("HOT", "BOOKED") else expected
            if actual == terminal or (expected == "HOT" and actual == "BOOKED"):
                correct += 1
        # Cheap hallucination proxy: any qualification field containing tokens
        # not present in the transcript
        transcript_text = " ".join(t.get("text", "") for t in d.get("transcript", [])).lower()
        q = d.get("qualification") or {}
        for field in ("budget", "area", "timeline"):
            v = (q.get(field) or "").lower()
            if v and v not in transcript_text and len(v) > 3:
                # Very rough: assume the LLM invented it
                hallucination_hits += 1
                break
    accuracy = round(correct / total_graded, 3) if total_graded else 0.0
    booking_rate = round(
        sum(1 for d in docs if d["status"] == "BOOKED") / max(1, len(docs)), 3
    )
    return {
        "graded": total_graded,
        "correct": correct,
        "qualification_accuracy": accuracy,
        "booking_rate": booking_rate,
        "hallucination_rate": round(hallucination_hits / max(1, len(docs)), 3),
        "sample_size": len(docs),
    }


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def _shutdown():
    client.close()
