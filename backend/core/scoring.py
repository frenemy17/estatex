from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException

import providers
from core.database import db, from_mongo
from core.models import Lead, Qualification
from core.services import record_provider, send_notification, sync_crm
from core.state_machine import is_legal, record_event, touch, transition
from providers import ProviderResult

QUALIFICATION_RUBRIC = {
    "threshold_qualified": 70,
    "threshold_nurture": 40,
    "weights": {"intent": 25, "budget": 25, "timeline": 20, "financing": 15, "area": 15},
}

FIELD_ORDER = ("intent", "budget", "timeline", "financing", "area")

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
    """Map the lead's replies onto qualification fields, deterministically."""
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
    """Deterministic rubric. Also the scorer of record."""
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


async def qualify_and_route(lead_id: str) -> dict:
    """Score an existing transcript, route the lead, sync CRM, follow up."""
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
                "that fit your search. Let me know if any catch your eye.",
            },
        )

    lead_doc = await db.leads.find_one({"id": lead_id})
    lead = from_mongo(Lead, lead_doc)
    return {
        "status": lead.status,
        "score": score,
        "qualification": q.model_dump(),
        "llm": llm.to_meta(),
    }
