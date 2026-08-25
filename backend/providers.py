"""Provider integrations with honest, inspectable results.

Every provider follows one contract:

* required env vars absent  -> MOCK path, ``ProviderResult(mode="MOCK", ok=True)``
* required env vars present -> LIVE path. The real HTTP status is checked. On
  failure we return the LIVE failure with its status code and error text; the
  caller decides whether to fall back to a mock. Nothing ever claims a success
  it did not get.

Providers here are pure I/O — they never touch Mongo. The caller (``server.py``)
owns policy (opt-out, quiet hours) and persistence (events, provider health).
That keeps this module trivially unit-testable without a database.

``GET /api/providers`` reports each provider's mode plus the outcome of its last
call, which is what the dashboard's status chips render. Setting ``DEMO_MODE=1``
forces every provider to MOCK so the public demo is deterministic and free.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

log = logging.getLogger("providers")


def demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")


# ---------- Result type ----------


@dataclass
class ProviderResult:
    """The outcome of one provider call. ``ok`` is never assumed."""

    spec: str  # registry key: "vapi", "calcom", "resend", ...
    provider: str  # what actually ran: "vapi" or "mock-vapi"
    mode: str  # LIVE | MOCK
    ok: bool
    status: Optional[int] = None
    error: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def live_failure(self) -> bool:
        """True when a configured provider was tried and genuinely failed."""
        return self.mode == "LIVE" and not self.ok

    def to_meta(self) -> dict[str, Any]:
        """Audit-log shape. Excludes ``data`` — callers add what matters."""
        meta = {"provider": self.provider, "mode": self.mode, "ok": self.ok}
        if self.status is not None:
            meta["status"] = self.status
        if self.error:
            meta["error"] = self.error[:500]
        return meta


def _mock(spec: str, **data: Any) -> ProviderResult:
    return ProviderResult(
        spec=spec, provider=f"mock-{spec}", mode="MOCK", ok=True, data=data
    )


def _live_ok(spec: str, status: int, **data: Any) -> ProviderResult:
    return ProviderResult(
        spec=spec, provider=spec, mode="LIVE", ok=True, status=status, data=data
    )


def _live_err(spec: str, status: int | None, error: str) -> ProviderResult:
    return ProviderResult(
        spec=spec, provider=spec, mode="LIVE", ok=False, status=status, error=error
    )


def _body(res: requests.Response, limit: int = 300) -> str:
    try:
        return json.dumps(res.json())[:limit]
    except Exception:  # noqa: BLE001
        return (res.text or "")[:limit]


# ---------- Capability registry ----------

PROVIDER_SPECS: dict[str, dict[str, Any]] = {
    "groq": {
        "label": "Groq LLM",
        "capability": "Qualification + supervisor reasoning",
        "env": ["GROQ_API_KEY"],
    },
    "vapi": {
        "label": "Vapi Voice",
        "capability": "Outbound AI phone calls",
        "env": ["VAPI_API_KEY", "VAPI_PHONE_NUMBER_ID"],
        "gate": "VOICE_ENABLED",
    },
    "calcom": {
        "label": "Cal.com",
        "capability": "Viewing slots + booking",
        "env": ["CAL_API_KEY", "CAL_EVENT_TYPE_ID"],
    },
    "resend": {
        "label": "Resend",
        "capability": "Nurture email",
        "env": ["RESEND_API_KEY"],
    },
    "twilio": {
        "label": "Twilio SMS",
        "capability": "Follow-up SMS + inbound STOP",
        "env": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"],
        "gate": "SMS_ENABLED",
    },
    "hubspot": {
        "label": "HubSpot",
        "capability": "CRM contact + deal sync",
        "env": ["HUBSPOT_ACCESS_TOKEN"],
    },
}


def _env_ready(spec: str) -> bool:
    return all(os.environ.get(k) for k in PROVIDER_SPECS[spec]["env"])


def _gate_open(spec: str) -> bool:
    """Some providers need an explicit opt-in even when keys are present.

    Twilio US SMS needs A2P 10DLC approval and Vapi bills per minute, so having
    a key is not the same as wanting to use it.
    """
    gate = PROVIDER_SPECS[spec].get("gate")
    if not gate:
        return True
    return os.environ.get(gate, "").lower() in ("1", "true", "yes")


def is_live(spec: str) -> bool:
    return not demo_mode() and _env_ready(spec) and _gate_open(spec)


def provider_status(spec: str) -> dict[str, Any]:
    meta = PROVIDER_SPECS[spec]
    configured = _env_ready(spec)
    return {
        "name": spec,
        "label": meta["label"],
        "capability": meta["capability"],
        "configured": configured,
        "mode": "LIVE" if is_live(spec) else "MOCK",
        "missing_env": [k for k in meta["env"] if not os.environ.get(k)],
        "gate": meta.get("gate"),
        "gate_open": _gate_open(spec),
    }


def all_provider_status() -> list[dict[str, Any]]:
    return [provider_status(s) for s in PROVIDER_SPECS]


# ---------- LLM ----------

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"


def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    match = re.search(r"\{[\s\S]*\}", cleaned)
    return json.loads(match.group(0) if match else cleaned)


async def llm_json(
    system: str, prompt: str, fallback: dict, *, label: str = "llm"
) -> tuple[dict, ProviderResult]:
    """Ask an LLM for a JSON object.

    Returns ``(parsed, result)``. On any failure ``parsed`` is ``fallback`` and
    ``result`` carries the real error, so the caller can log why the deterministic
    path was used instead of silently pretending the LLM ran.

    Single source of truth for LLM access — ``server.qualify_with_llm`` and
    ``agents.supervisor`` both route through here.
    """
    key = os.environ.get("GROQ_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")

    if demo_mode() or not key:
        return fallback, _mock("groq", reason="no_key" if not key else "demo_mode")

    if key.startswith("gsk_"):
        try:
            res = await asyncio.to_thread(
                requests.post,
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
                timeout=15,
            )
            if res.status_code != 200:
                log.warning("groq %s -> %s %s", label, res.status_code, _body(res))
                return fallback, _live_err("groq", res.status_code, _body(res))
            content = res.json()["choices"][0]["message"]["content"]
            return json.loads(content), _live_ok("groq", res.status_code, model=GROQ_MODEL)
        except Exception as e:  # noqa: BLE001
            log.warning("groq %s failed: %s", label, e)
            return fallback, _live_err("groq", None, str(e))

    # Non-Groq key: treat as a Gemini key.
    try:
        import google.generativeai as genai

        genai.configure(api_key=key)
        model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=system)
        resp = await model.generate_content_async(prompt)
        return _extract_json(resp.text), _live_ok("groq", 200, model=GEMINI_MODEL)
    except Exception as e:  # noqa: BLE001
        log.warning("gemini %s failed: %s", label, e)
        return fallback, _live_err("groq", None, str(e))


# ---------- Voice ----------

QUESTIONS = [
    "What kind of property are you looking for (buy, rent, invest)?",
    "What is your approximate budget range?",
    "What is your timeline — are you looking to move in the next few months?",
    "Do you already have financing/pre-approval in place?",
    "Which neighborhoods or areas are you focused on?",
]

_MOCK_ANSWERS = [
    {
        "intent": "buy primary residence",
        "budget": "$650k-750k",
        "timeline": "next 2 months",
        "financing": "pre-approved",
        "area": "Downtown / East Village",
    },
    {
        "intent": "investment property",
        "budget": "$300k",
        "timeline": "just researching",
        "financing": "not yet",
        "area": "Suburbs",
    },
    {
        "intent": "buy family home",
        "budget": "$1.2M",
        "timeline": "urgent, within 30 days",
        "financing": "cash buyer",
        "area": "Riverside, Oak Park",
    },
    {
        "intent": "rent",
        "budget": "unsure",
        "timeline": "6+ months",
        "financing": "renting",
        "area": "undecided",
    },
    {
        "intent": "buy townhouse",
        "budget": "$460k",
        "timeline": "in about 2 months",
        "financing": "pre-approved",
        "area": "undecided",
    },
]

MOCK_PROFILE_COUNT = len(_MOCK_ANSWERS)

ASSISTANT_SYSTEM = (
    "You are Ava, a real-estate concierge for EstateX Realty. Qualify the buyer by "
    "asking property type (buy, rent, invest), budget, timeline, financing "
    "pre-approval, and target neighborhood. Keep it to one question at a time."
)


def mock_transcript(name: str, profile: int | None = None) -> list[dict[str, str]]:
    """A scripted qualification call.

    The profile is chosen by a stable hash of the lead's name rather than
    ``random.choice`` — the same lead must produce the same transcript on every
    run, or the demo funnel reshuffles on each reset and ``/api/eval`` measures
    noise. Pass ``profile`` to pin one explicitly.
    """
    if profile is None:
        profile = zlib.crc32(name.encode()) % MOCK_PROFILE_COUNT
    s = _MOCK_ANSWERS[profile % MOCK_PROFILE_COUNT]
    turns = [
        {"role": "agent", "text": f"Hi {name}, this is Ava from EstateX Realty."},
        {"role": "lead", "text": "Sure, go ahead."},
    ]
    for question, key in zip(
        QUESTIONS, ("intent", "budget", "timeline", "financing", "area")
    ):
        turns.append({"role": "agent", "text": question})
        turns.append({"role": "lead", "text": s[key]})
    return turns


class VoiceProvider:
    """Outbound AI phone calls.

    LIVE returns a ``call_id`` and ``transcript=None`` — a real call has not
    happened yet when this returns. The transcript arrives later on
    ``POST /api/webhooks/vapi``. Callers MUST NOT qualify on a ``None``
    transcript; that was the bug where adding a Vapi key scored every lead 0.
    """

    async def start_call(
        self, *, lead_id: str, name: str, phone: str, profile: int | None = None
    ) -> ProviderResult:
        if not is_live("vapi"):
            return _mock(
                "vapi", transcript=mock_transcript(name, profile), call_id=None
            )

        assistant_id = os.environ.get("VAPI_ASSISTANT_ID")
        payload: dict[str, Any] = {
            "phoneNumberId": os.environ["VAPI_PHONE_NUMBER_ID"],
            "customer": {"number": phone, "name": name},
            "metadata": {"lead_id": lead_id},
        }
        if assistant_id:
            payload["assistantId"] = assistant_id
        else:
            payload["assistant"] = {
                "firstMessage": (
                    f"Hi {name}, this is Ava from EstateX Realty. Do you have a "
                    "moment to discuss your home search?"
                ),
                "model": {
                    "provider": "groq",
                    "model": GROQ_MODEL,
                    "messages": [{"role": "system", "content": ASSISTANT_SYSTEM}],
                },
            }

        try:
            res = await asyncio.to_thread(
                requests.post,
                "https://api.vapi.ai/call",
                headers={
                    "Authorization": f"Bearer {os.environ['VAPI_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15,
            )
            if res.status_code not in (200, 201):
                return _live_err("vapi", res.status_code, _body(res))
            call_id = (res.json() or {}).get("id")
            log.info("vapi call dispatched lead=%s call=%s", lead_id, call_id)
            # transcript=None is the signal to wait for the webhook.
            return _live_ok("vapi", res.status_code, call_id=call_id, transcript=None)
        except Exception as e:  # noqa: BLE001
            return _live_err("vapi", None, str(e))


def parse_vapi_transcript(message: dict) -> list[dict[str, str]]:
    """Normalise a Vapi ``end-of-call-report`` into our transcript shape.

    Vapi has shipped several payload shapes, so try each: structured
    ``artifact.messages`` first (best fidelity), then a flat transcript string
    with ``AI:``/``User:`` line prefixes.
    """
    artifact = message.get("artifact") or {}

    for msgs in (artifact.get("messages"), message.get("messages")):
        if isinstance(msgs, list) and msgs:
            turns = []
            for m in msgs:
                role = (m.get("role") or "").lower()
                text = m.get("message") or m.get("content") or ""
                if role == "system" or not text:
                    continue
                turns.append(
                    {
                        "role": "agent" if role in ("assistant", "bot", "agent") else "lead",
                        "text": str(text),
                    }
                )
            if turns:
                return turns

    raw = artifact.get("transcript") or message.get("transcript") or ""
    if not isinstance(raw, str) or not raw.strip():
        return []

    turns = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(AI|Assistant|Agent|Bot|User|Human|Customer)\s*:\s*(.+)$", line, re.I)
        if m:
            speaker, text = m.group(1).lower(), m.group(2)
            role = "agent" if speaker in ("ai", "assistant", "agent", "bot") else "lead"
            turns.append({"role": role, "text": text})
        else:
            turns.append({"role": "lead", "text": line})
    return turns


# ---------- Booking ----------

# Cal.com pins behaviour to a date-versioned header. Bump these if Cal ships a
# breaking change; the parser below tolerates either payload shape meanwhile.
CAL_SLOTS_API_VERSION = "2024-09-04"
CAL_BOOKINGS_API_VERSION = "2024-08-13"


def _parse_cal_slots(payload: Any) -> list[str]:
    """Pull ISO start times out of Cal's slots response.

    v1 keyed each slot by ``time``, v2 by ``start``, and the container has been
    both a date-keyed dict and a flat list. Accept all of them rather than
    KeyError into a silent mock — that was the original bug.
    """
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        data = data.get("slots", data)

    buckets: list[Any] = []
    if isinstance(data, dict):
        for v in data.values():
            buckets.extend(v if isinstance(v, list) else [v])
    elif isinstance(data, list):
        buckets = data

    out = []
    for slot in buckets:
        if isinstance(slot, str):
            out.append(slot)
        elif isinstance(slot, dict):
            when = slot.get("start") or slot.get("time") or slot.get("startTime")
            if when:
                out.append(str(when))
    return out


def mock_slots(count: int = 9) -> list[str]:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return [
        (now + timedelta(days=d, hours=h)).isoformat()
        for d in (1, 2, 3)
        for h in (10, 14, 16)
    ][:count]


class BookingProvider:
    async def get_slots(self) -> ProviderResult:
        if not is_live("calcom"):
            return _mock("calcom", slots=mock_slots())

        start = datetime.now(timezone.utc)
        try:
            res = await asyncio.to_thread(
                requests.get,
                "https://api.cal.com/v2/slots",
                headers={
                    "Authorization": f"Bearer {os.environ['CAL_API_KEY']}",
                    "cal-api-version": CAL_SLOTS_API_VERSION,
                },
                params={
                    "eventTypeId": os.environ["CAL_EVENT_TYPE_ID"],
                    "start": start.date().isoformat(),
                    "end": (start + timedelta(days=7)).date().isoformat(),
                },
                timeout=15,
            )
            if res.status_code != 200:
                return _live_err("calcom", res.status_code, _body(res))
            slots = _parse_cal_slots(res.json())
            if not slots:
                return _live_err(
                    "calcom", res.status_code, "no slots in response — check event type availability"
                )
            return _live_ok("calcom", res.status_code, slots=slots[:9])
        except Exception as e:  # noqa: BLE001
            return _live_err("calcom", None, str(e))

    async def book(
        self, *, slot_iso: str, name: str, email: str | None
    ) -> ProviderResult:
        """Reserve a slot. A non-2xx here means the lead is NOT booked."""
        if not is_live("calcom"):
            return _mock("calcom", booking_id=None)

        try:
            res = await asyncio.to_thread(
                requests.post,
                "https://api.cal.com/v2/bookings",
                headers={
                    "Authorization": f"Bearer {os.environ['CAL_API_KEY']}",
                    "cal-api-version": CAL_BOOKINGS_API_VERSION,
                    "Content-Type": "application/json",
                },
                json={
                    "start": slot_iso,
                    "eventTypeId": int(os.environ["CAL_EVENT_TYPE_ID"]),
                    "attendee": {
                        "name": name,
                        "email": email or "lead@example.com",
                        "timeZone": "UTC",
                    },
                },
                timeout=15,
            )
            if res.status_code not in (200, 201):
                return _live_err("calcom", res.status_code, _body(res))
            data = (res.json() or {}).get("data") or {}
            return _live_ok("calcom", res.status_code, booking_id=data.get("uid") or data.get("id"))
        except Exception as e:  # noqa: BLE001
            return _live_err("calcom", None, str(e))


# ---------- Notification ----------


class NotificationProvider:
    """Email + SMS transport. Opt-out and quiet-hours policy live in the caller."""

    @staticmethod
    def resolve_email(to: str | None) -> tuple[str | None, bool]:
        """Apply the DEMO_EMAIL override.

        Seed and simulation leads use ``@example.com`` addresses that can never
        deliver. With an unverified Resend domain you can only mail your own
        signup address anyway, so DEMO_EMAIL makes live email actually
        demonstrable. Returns ``(recipient, was_redirected)``.
        """
        override = os.environ.get("DEMO_EMAIL")
        if not override:
            return to, False
        if to and not to.lower().endswith(("@example.com", "@x.com")):
            return to, False
        return override, True

    async def send_email(self, *, to: str | None, subject: str, body: str) -> ProviderResult:
        recipient, redirected = self.resolve_email(to)
        if not is_live("resend"):
            return _mock("resend", to=recipient, subject=subject, redirected=redirected)
        if not recipient:
            return _live_err("resend", None, "no recipient address on lead")

        try:
            res = await asyncio.to_thread(
                requests.post,
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": os.environ.get("FROM_EMAIL", "onboarding@resend.dev"),
                    "to": [recipient],
                    "subject": subject,
                    "html": f"<p>{body}</p>",
                },
                timeout=15,
            )
            if res.status_code not in (200, 201):
                # 403 here is almost always "domain not verified / can only send
                # to the account owner" — surface it instead of hiding it.
                return _live_err("resend", res.status_code, _body(res))
            return _live_ok(
                "resend",
                res.status_code,
                to=recipient,
                redirected=redirected,
                message_id=(res.json() or {}).get("id"),
            )
        except Exception as e:  # noqa: BLE001
            return _live_err("resend", None, str(e))

    async def send_sms(self, *, to: str | None, body: str) -> ProviderResult:
        if not is_live("twilio"):
            return _mock("twilio", to=to)
        if not to:
            return _live_err("twilio", None, "no phone number on lead")

        sid = os.environ["TWILIO_ACCOUNT_SID"]
        try:
            res = await asyncio.to_thread(
                requests.post,
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]),
                data={
                    "From": os.environ["TWILIO_PHONE_NUMBER"],
                    "To": to,
                    "Body": body,
                },
                timeout=15,
            )
            if res.status_code not in (200, 201):
                # 21608 = unverified number on a trial account.
                # 30034 = sender not A2P 10DLC registered.
                return _live_err("twilio", res.status_code, _body(res))
            return _live_ok(
                "twilio", res.status_code, to=to, message_id=(res.json() or {}).get("sid")
            )
        except Exception as e:  # noqa: BLE001
            return _live_err("twilio", None, str(e))


# ---------- CRM ----------


class CRMProvider:
    async def upsert_contact(
        self, *, name: str, phone: str, email: str | None
    ) -> ProviderResult:
        """Idempotent contact sync.

        Uses the batch upsert endpoint keyed on email so running the pipeline
        twice updates rather than 409-ing. The previous implementation POSTed to
        the plain create endpoint and reported success regardless of status.
        """
        if not is_live("hubspot"):
            return _mock("hubspot", contact_id=None)

        parts = (name or "").split()
        props = {
            "firstname": parts[0] if parts else "",
            "lastname": " ".join(parts[1:]) if len(parts) > 1 else "",
            "phone": phone,
        }
        headers = {
            "Authorization": f"Bearer {os.environ['HUBSPOT_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
        }

        try:
            if email:
                props["email"] = email
                res = await asyncio.to_thread(
                    requests.post,
                    "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert",
                    headers=headers,
                    json={"inputs": [{"idProperty": "email", "id": email, "properties": props}]},
                    timeout=15,
                )
                if res.status_code not in (200, 201, 207):
                    return _live_err("hubspot", res.status_code, _body(res))
                results = (res.json() or {}).get("results") or []
                return _live_ok(
                    "hubspot",
                    res.status_code,
                    contact_id=(results[0].get("id") if results else None),
                )

            # No email means no upsert key; create and treat a duplicate as fine.
            res = await asyncio.to_thread(
                requests.post,
                "https://api.hubapi.com/crm/v3/objects/contacts",
                headers=headers,
                json={"properties": props},
                timeout=15,
            )
            if res.status_code == 409:
                return _live_ok("hubspot", res.status_code, contact_id=None, duplicate=True)
            if res.status_code not in (200, 201):
                return _live_err("hubspot", res.status_code, _body(res))
            return _live_ok(
                "hubspot", res.status_code, contact_id=(res.json() or {}).get("id")
            )
        except Exception as e:  # noqa: BLE001
            return _live_err("hubspot", None, str(e))

    async def create_deal(
        self, *, name: str, status: str, score: int, contact_id: str | None
    ) -> ProviderResult:
        if not is_live("hubspot"):
            return _mock("hubspot", deal_id=None, score=score)

        payload: dict[str, Any] = {
            "properties": {
                "dealname": f"Deal — {name}",
                "pipeline": "default",
                "dealstage": "appointmentscheduled" if status == "HOT" else "qualifiedtobuy",
            }
        }
        if contact_id:
            # associationTypeId 3 is the HubSpot-defined deal -> contact link.
            payload["associations"] = [
                {
                    "to": {"id": contact_id},
                    "types": [
                        {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}
                    ],
                }
            ]

        try:
            res = await asyncio.to_thread(
                requests.post,
                "https://api.hubapi.com/crm/v3/objects/deals",
                headers={
                    "Authorization": f"Bearer {os.environ['HUBSPOT_ACCESS_TOKEN']}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15,
            )
            if res.status_code not in (200, 201):
                return _live_err("hubspot", res.status_code, _body(res))
            return _live_ok(
                "hubspot",
                res.status_code,
                deal_id=(res.json() or {}).get("id"),
                associated=bool(contact_id),
            )
        except Exception as e:  # noqa: BLE001
            return _live_err("hubspot", None, str(e))


voice = VoiceProvider()
booker = BookingProvider()
notifier = NotificationProvider()
crm = CRMProvider()
