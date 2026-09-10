from __future__ import annotations

import asyncio
import os
import re
import secrets
import sys
from typing import Any, Optional
from xml.sax.saxutils import escape

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

import providers
from core.database import db, log, now_iso
from core.models import GoogleLeadColumn, GoogleLeadPayload
from core.pipeline import _background_tasks, run_supervisor
from core.scoring import qualify_and_route
from core.state_machine import is_legal, record_event, touch, transition
from routes.leads import _ingest_lead

GOOGLE_LEADS_WEBHOOK_KEY = os.environ.get("GOOGLE_LEADS_WEBHOOK_KEY")
VAPI_WEBHOOK_SECRET = os.environ.get("VAPI_WEBHOOK_SECRET")

_STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "revoke", "optout"}

router = APIRouter(tags=["webhooks"])


async def _claim_once(key: str, meta: dict | None = None) -> bool:
    """Idempotency latch. False means we already processed this message."""
    res = await db.webhook_receipts.update_one(
        {"_id": key},
        {"$setOnInsert": {"at": now_iso(), **(meta or {})}},
        upsert=True,
    )
    return res.upserted_id is not None


def _pick(cols: list[GoogleLeadColumn], key: str) -> str | None:
    key_up = key.upper()
    for c in cols:
        if (c.column_id or "").upper() == key_up:
            return (c.string_value or "").strip() or None
    return None


@router.post("/webhooks/google-leads")
async def google_leads_webhook(payload: GoogleLeadPayload, bg: BackgroundTasks):
    srv = sys.modules.get("server")
    webhook_key = (
        getattr(srv, "GOOGLE_LEADS_WEBHOOK_KEY", None)
        if srv and hasattr(srv, "GOOGLE_LEADS_WEBHOOK_KEY")
        else GOOGLE_LEADS_WEBHOOK_KEY
    )
    if webhook_key is None:
        webhook_key = os.environ.get("GOOGLE_LEADS_WEBHOOK_KEY")

    if not webhook_key:
        log.warning("google-leads webhook rejected: GOOGLE_LEADS_WEBHOOK_KEY unset")
        raise HTTPException(503, "Webhook not configured")
    if not secrets.compare_digest(payload.google_key, webhook_key):
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
    return {"lead_id": lead.id, "status": "accepted"}


@router.post("/webhooks/vapi")
async def vapi_webhook(request: Request):
    """Receive the real call transcript and resume qualification."""
    srv = sys.modules.get("server")
    secret = (
        getattr(srv, "VAPI_WEBHOOK_SECRET", None)
        if srv and hasattr(srv, "VAPI_WEBHOOK_SECRET")
        else VAPI_WEBHOOK_SECRET
    )
    if secret is None:
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


async def _finalize_twilio_voice_call(
    lead_id: str, transcript: list[dict[str, str]], call_sid: Optional[str] = None
):
    """Save finalized voice call transcript, record audit event, and trigger qualification."""
    await touch(
        lead_id,
        transcript=transcript,
        awaiting_transcript=False,
        voice_call_id=call_sid,
    )
    await record_event(
        lead_id,
        "call",
        reason="call.transcript_received",
        meta={
            "turns": len(transcript),
            "provider": "twilio-voice",
            "call_id": call_sid,
            "ended_reason": "completed",
        },
    )
    try:
        await qualify_and_route(lead_id)
    except Exception as e:  # noqa: BLE001
        log.exception("qualify_and_route failed for %s: %s", lead_id, e)


@router.api_route("/voice/twiml", methods=["GET", "POST"])
async def voice_twiml_endpoint(request: Request, lead_id: Optional[str] = None):
    """Twilio Voice webhook for outbound call initialisation."""
    if not lead_id:
        params = dict(request.query_params)
        lead_id = params.get("lead_id")
    if not lead_id:
        try:
            form = await request.form()
            lead_id = form.get("lead_id")
        except Exception:  # noqa: BLE001
            pass

    lead_name = "there"
    if lead_id:
        lead_doc = await db.leads.find_one({"id": lead_id})
        if lead_doc:
            lead_name = lead_doc.get("name", "there")

    greeting = (
        f"Hi {lead_name}, this is Sarah from EstateX Realty. Thanks for your inquiry! "
        "Do you have a quick moment to discuss what you are looking for in a home?"
    )
    gather_url = f"/api/voice/gather?lead_id={lead_id or ''}&step=1"

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f'    <Say voice="Polly.Joanna">{escape(greeting)}</Say>\n'
        f'    <Gather input="speech" action="{escape(gather_url)}" method="POST" speechTimeout="auto" timeout="6">\n'
        '        <Say voice="Polly.Joanna">Please tell me what kind of property you have in mind.</Say>\n'
        "    </Gather>\n"
        '    <Say voice="Polly.Joanna">We did not hear anything. We will follow up by text or email. Goodbye!</Say>\n'
        "    <Hangup/>\n"
        "</Response>"
    )
    return Response(content=twiml, media_type="application/xml")


@router.post("/voice/gather")
async def voice_gather_endpoint(
    request: Request, lead_id: Optional[str] = None, step: int = 1
):
    """Twilio Voice webhook called after speech is captured."""
    form_data: dict[str, Any] = {}
    try:
        form = await request.form()
        form_data = dict(form)
    except Exception:  # noqa: BLE001
        pass

    if not lead_id:
        lead_id = form_data.get("lead_id") or request.query_params.get("lead_id")

    speech_result = (form_data.get("SpeechResult") or "").strip()
    call_sid = form_data.get("CallSid")

    if not lead_id:
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<Response>\n"
            '    <Say voice="Polly.Joanna">Thank you. Goodbye!</Say>\n'
            "    <Hangup/>\n"
            "</Response>"
        )
        return Response(content=twiml, media_type="application/xml")

    lead_doc = await db.leads.find_one({"id": lead_id})
    if not lead_doc:
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<Response>\n"
            '    <Say voice="Polly.Joanna">Thank you. Goodbye!</Say>\n'
            "    <Hangup/>\n"
            "</Response>"
        )
        return Response(content=twiml, media_type="application/xml")

    lead_name = lead_doc.get("name", "there")
    history = list(lead_doc.get("transcript") or [])

    if not history:
        history.append({
            "role": "agent",
            "text": (
                f"Hi {lead_name}, this is Sarah from EstateX Realty. Thanks for your inquiry! "
                "Do you have a quick moment to discuss what you are looking for in a home?"
            ),
        })

    if speech_result:
        history.append({"role": "lead", "text": speech_result})
    else:
        if step >= 3:
            await _finalize_twilio_voice_call(lead_id, history, call_sid)
            twiml = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                "<Response>\n"
                '    <Say voice="Polly.Joanna">Thank you for your time. Have a wonderful day!</Say>\n'
                "    <Hangup/>\n"
                "</Response>"
            )
            return Response(content=twiml, media_type="application/xml")

        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<Response>\n"
            '    <Say voice="Polly.Joanna">I am sorry, I did not catch that. Could you repeat?</Say>\n'
            f'    <Gather input="speech" action="/api/voice/gather?lead_id={lead_id}&amp;step={step}" method="POST" speechTimeout="auto" timeout="6"/>\n'
            '    <Say voice="Polly.Joanna">Thank you. Goodbye!</Say>\n'
            "    <Hangup/>\n"
            "</Response>"
        )
        return Response(content=twiml, media_type="application/xml")

    agent_turn = await providers.conversational_agent_turn(lead_name, history, step=step)
    reply_text = agent_turn.get("reply", "Thank you for sharing that.")
    is_done = agent_turn.get("done", False) or step >= 4

    history.append({"role": "agent", "text": reply_text})

    if is_done:
        conclude_text = (
            f"{reply_text} Thank you! I have recorded your preferences and our senior advisor will follow up shortly. Have a wonderful day!"
        )
        history.append({
            "role": "agent",
            "text": "Thank you! I have recorded your preferences and our senior advisor will follow up shortly. Have a wonderful day!",
        })
        await _finalize_twilio_voice_call(lead_id, history, call_sid)
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<Response>\n"
            f'    <Say voice="Polly.Joanna">{escape(conclude_text)}</Say>\n'
            "    <Hangup/>\n"
            "</Response>"
        )
        return Response(content=twiml, media_type="application/xml")

    await touch(lead_id, transcript=history)
    next_step = step + 1
    next_gather_url = f"/api/voice/gather?lead_id={lead_id}&step={next_step}"
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f'    <Say voice="Polly.Joanna">{escape(reply_text)}</Say>\n'
        f'    <Gather input="speech" action="{escape(next_gather_url)}" method="POST" speechTimeout="auto" timeout="6"/>\n'
        '    <Say voice="Polly.Joanna">Thank you, we will follow up shortly. Goodbye!</Say>\n'
        "    <Hangup/>\n"
        "</Response>"
    )
    return Response(content=twiml, media_type="application/xml")


def _dispatch_supervisor(lead_id: str) -> None:
    task = asyncio.create_task(run_supervisor(lead_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@router.post("/webhooks/twilio-sms")
async def twilio_sms_webhook(request: Request):
    """Inbound SMS. STOP opts the lead out; anything else feeds the supervisor."""
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
