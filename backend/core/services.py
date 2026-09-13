from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import providers
from core.database import clog, db, now, now_iso, _flag
from core.models import Lead
from core.state_machine import record_event
from providers import ProviderResult

QUIET_HOURS_ENABLED = _flag("QUIET_HOURS_ENABLED", True)
QUIET_HOURS_START = int(os.environ.get("QUIET_HOURS_START", "21"))  # 9pm UTC
QUIET_HOURS_END = int(os.environ.get("QUIET_HOURS_END", "8"))  # 8am UTC
CALL_TIMEOUT_MINUTES = int(os.environ.get("CALL_TIMEOUT_MINUTES", "20"))
SUPERVISOR_WAIT_HOURS = int(os.environ.get("SUPERVISOR_WAIT_HOURS", "6"))


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
    import sys
    srv = sys.modules.get("server")
    enabled = getattr(srv, "QUIET_HOURS_ENABLED", QUIET_HOURS_ENABLED) if srv else QUIET_HOURS_ENABLED
    if not enabled:
        return False
    start = getattr(srv, "QUIET_HOURS_START", QUIET_HOURS_START) if srv else QUIET_HOURS_START
    end = getattr(srv, "QUIET_HOURS_END", QUIET_HOURS_END) if srv else QUIET_HOURS_END
    h = (at or now()).hour
    if start <= end:
        return start <= h < end
    return h >= start or h < end


def quiet_hours_end_at(at: datetime | None = None) -> datetime:
    import sys
    srv = sys.modules.get("server")
    end = getattr(srv, "QUIET_HOURS_END", QUIET_HOURS_END) if srv else QUIET_HOURS_END
    ref = at or now()
    # `% 24` so a config of QUIET_HOURS_END=24 means midnight rather than crashing.
    target = ref.replace(hour=end % 24, minute=0, second=0, microsecond=0)
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
    from core.tick import schedule_action  # deferred import to avoid circular dep

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
