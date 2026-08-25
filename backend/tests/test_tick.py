"""Pipeline, autonomy, webhook, and lockdown tests.

Runs entirely in-process against the in-memory database double from
``conftest.py`` — no server, no Mongo, no network. Every provider is forced to
MOCK via ``DEMO_MODE=1``.

These cover the five blockers the rewrite targeted:

1. a live voice call must park at CALLING instead of qualifying an empty transcript
2. "wait 6 hours" and quiet-hours deferrals must produce work that actually runs
3. a lead stranded mid-call must be rescued
4. a failed provider call must not read as success
5. destructive routes must refuse an unauthenticated caller
"""
from __future__ import annotations

from asyncio import run
from datetime import timedelta
from types import SimpleNamespace

import providers
import pytest
import server
from fastapi import BackgroundTasks, HTTPException
from providers import ProviderResult

TERMINAL = {"QUALIFIED", "HOT", "NURTURE", "BOOKED"}


# ---------- helpers ----------


def make_lead(fake_db, **overrides) -> str:
    lead = server.Lead(
        **{
            "name": "Emily Chen",
            "phone": "+14155550101",
            "email": "emily@example.com",
            **overrides,
        }
    )
    run(fake_db.leads.insert_one(server.to_mongo(lead)))
    return lead.id


def events(fake_db, lead_id: str) -> list[dict]:
    return run(fake_db.events.find({"lead_id": lead_id}).to_list(None))


def reasons(fake_db, lead_id: str) -> list[str]:
    return [e.get("reason") for e in events(fake_db, lead_id)]


def lead_doc(fake_db, lead_id: str) -> dict:
    return run(fake_db.leads.find_one({"id": lead_id}))


def fake_request(host: str = "10.0.0.1", headers: dict | None = None, body=None, form=None):
    async def _json():
        return body

    async def _form():
        return form or {}

    return SimpleNamespace(
        client=SimpleNamespace(host=host),
        headers=headers or {},
        json=_json,
        form=_form,
    )


def live_failure(spec: str, status: int = 500) -> ProviderResult:
    return ProviderResult(
        spec=spec, provider=spec, mode="LIVE", ok=False, status=status, error="boom"
    )


# ---------- the keyless demo actually works ----------


def test_mock_pipeline_reaches_a_terminal_status_with_a_real_score(fake_db):
    lead_id = make_lead(fake_db, name="Sim Alpha", sim_profile=0)
    run(server.run_ai_pipeline(lead_id))

    doc = lead_doc(fake_db, lead_id)
    assert doc["status"] in TERMINAL
    # Profile 0 is the strong buyer: this must not collapse to 0/NURTURE.
    assert doc["score"] == 100 and doc["status"] == "HOT"
    assert len(doc["transcript"]) >= 10
    assert doc["qualification"]["budget"] == "$650k-750k"
    assert "pipeline.error" not in reasons(fake_db, lead_id)


def test_pipeline_writes_a_complete_transition_chain(fake_db):
    lead_id = make_lead(fake_db, sim_profile=1)
    run(server.run_ai_pipeline(lead_id))
    chain = [
        (e["from_status"], e["to_status"])
        for e in events(fake_db, lead_id)
        if e["kind"] == "transition"
    ]
    assert chain[0] == ("NEW", "CALLING")
    assert ("CALLING", "IN_CONVERSATION") in chain
    # No gaps: each hop starts where the previous one ended.
    for (_, to_prev), (from_next, _) in zip(chain, chain[1:]):
        assert to_prev == from_next


def test_every_mock_profile_lands_in_its_expected_band(fake_db):
    """Guards the extraction alignment that the opening pleasantry used to break."""
    expected = {0: "HOT", 1: "NURTURE", 2: "HOT", 3: "NURTURE", 4: "QUALIFIED"}
    for profile in range(providers.MOCK_PROFILE_COUNT):
        lead_id = make_lead(
            fake_db, name=f"Lead {profile}", phone=f"+1415555{profile:04d}", sim_profile=profile
        )
        run(server.run_ai_pipeline(lead_id))
        assert lead_doc(fake_db, lead_id)["status"] == expected[profile], profile


# ---------- blocker #1: live voice must not qualify an empty transcript ----------


def test_live_call_parks_at_calling_and_waits_for_the_webhook(fake_db, monkeypatch):
    async def dispatched(**kwargs):
        return ProviderResult(
            spec="vapi",
            provider="vapi",
            mode="LIVE",
            ok=True,
            status=201,
            data={"call_id": "call_abc", "transcript": None},
        )

    monkeypatch.setattr(providers.voice, "start_call", dispatched)
    lead_id = make_lead(fake_db)
    run(server.run_ai_pipeline(lead_id))

    doc = lead_doc(fake_db, lead_id)
    assert doc["status"] == "CALLING"
    assert doc["awaiting_transcript"] is True
    assert doc["voice_call_id"] == "call_abc"
    # The whole point: no score, no routing, no CRM sync off an empty transcript.
    assert doc["score"] == 0 and doc["qualification"] is None
    assert "call.awaiting_transcript" in reasons(fake_db, lead_id)


def test_qualify_refuses_an_empty_transcript(fake_db):
    lead_id = make_lead(fake_db)
    with pytest.raises(HTTPException) as exc:
        run(server.qualify_and_route(lead_id))
    assert exc.value.status_code == 409


def test_failed_live_call_does_not_invent_a_transcript(fake_db, monkeypatch):
    """A real person's call failed — recording a fabricated conversation would be worse
    than recording the failure."""

    async def failed(**kwargs):
        return live_failure("vapi", 402)

    monkeypatch.setattr(providers.voice, "start_call", failed)
    lead_id = make_lead(fake_db)
    run(server.run_ai_pipeline(lead_id))

    doc = lead_doc(fake_db, lead_id)
    assert doc["transcript"] == []
    assert doc["status"] == "NURTURE"
    assert "call.failed" in reasons(fake_db, lead_id)
    # And a retry is queued rather than the lead being abandoned.
    queued = run(fake_db.scheduled_actions.find({"lead_id": lead_id}).to_list(None))
    assert [a["kind"] for a in queued] == ["supervisor"]


def test_vapi_webhook_delivers_the_transcript_and_qualifies(fake_db):
    lead_id = make_lead(fake_db, status="CALLING", awaiting_transcript=True, voice_call_id="c1")
    body = {
        "message": {
            "type": "end-of-call-report",
            "call": {"id": "c1", "metadata": {"lead_id": lead_id}},
            "durationSeconds": 91,
            "endedReason": "customer-ended-call",
            "artifact": {
                "messages": [
                    {"role": "assistant", "message": "What is your approximate budget range?"},
                    {"role": "user", "message": "$1.2M"},
                    {"role": "assistant", "message": "What kind of property are you looking for?"},
                    {"role": "user", "message": "buy family home"},
                    {"role": "assistant", "message": "Do you have financing in place?"},
                    {"role": "user", "message": "cash buyer"},
                    {"role": "assistant", "message": "What is your timeline?"},
                    {"role": "user", "message": "urgent, within 30 days"},
                    {"role": "assistant", "message": "Which neighborhoods?"},
                    {"role": "user", "message": "Riverside"},
                ]
            },
        }
    }
    result = run(server.vapi_webhook(fake_request(body=body)))
    assert result["status"] == "qualified"

    doc = lead_doc(fake_db, lead_id)
    assert doc["status"] == "HOT" and doc["score"] == 100
    assert doc["awaiting_transcript"] is False
    assert "call.transcript_received" in reasons(fake_db, lead_id)


def test_vapi_webhook_is_idempotent(fake_db):
    lead_id = make_lead(fake_db, status="CALLING", awaiting_transcript=True, voice_call_id="c2")
    body = {
        "message": {
            "type": "end-of-call-report",
            "call": {"id": "c2"},
            "artifact": {"transcript": "AI: Budget?\nUser: $300k"},
        }
    }
    first = run(server.vapi_webhook(fake_request(body=body)))
    second = run(server.vapi_webhook(fake_request(body=body)))
    assert first["status"] == "qualified"
    assert second == {"status": "duplicate", "lead_id": lead_id}


def test_vapi_webhook_ignores_other_message_types(fake_db):
    body = {"message": {"type": "status-update", "call": {"id": "zzz"}}}
    assert run(server.vapi_webhook(fake_request(body=body)))["status"] == "ignored"


def test_vapi_webhook_rejects_a_bad_secret(fake_db, monkeypatch):
    monkeypatch.setenv("VAPI_WEBHOOK_SECRET", "s3cret")
    req = fake_request(headers={"x-vapi-secret": "wrong"}, body={"message": {}})
    with pytest.raises(HTTPException) as exc:
        run(server.vapi_webhook(req))
    assert exc.value.status_code == 401


def test_vapi_empty_transcript_is_recorded_not_scored(fake_db):
    lead_id = make_lead(fake_db, status="CALLING", awaiting_transcript=True, voice_call_id="c3")
    body = {
        "message": {
            "type": "end-of-call-report",
            "call": {"id": "c3"},
            "endedReason": "customer-did-not-answer",
            "artifact": {},
        }
    }
    assert run(server.vapi_webhook(fake_request(body=body)))["status"] == "empty_transcript"
    doc = lead_doc(fake_db, lead_id)
    assert doc["status"] == "NURTURE" and doc["score"] == 0
    assert "call.empty_transcript" in reasons(fake_db, lead_id)


# ---------- blocker #2: scheduled work actually runs ----------


def test_tick_drains_a_due_action_and_leaves_future_ones_alone(fake_db):
    lead_id = make_lead(fake_db, status="NURTURE")
    run(
        server.schedule_action(
            lead_id, "notify", server.now() - timedelta(minutes=5), {"channel": "email"}, "due"
        )
    )
    run(
        server.schedule_action(
            lead_id, "notify", server.now() + timedelta(hours=3), {"channel": "email"}, "later"
        )
    )

    summary = run(server.run_tick())
    assert summary["drained"] == 1 and summary["failed"] == 0

    states = {
        a["reason"]: a["state"]
        for a in run(fake_db.scheduled_actions.find({}).to_list(None))
    }
    assert states == {"due": "DONE", "later": "PENDING"}


def test_tick_runs_a_due_supervisor_check(fake_db):
    lead_id = make_lead(fake_db, status="NURTURE", score=30)
    run(server.schedule_action(lead_id, "supervisor", server.now() - timedelta(hours=1)))
    summary = run(server.run_tick())
    assert summary["drained"] == 1
    assert any(e["kind"] == "supervisor" for e in events(fake_db, lead_id))


def test_supervisor_wait_queues_a_real_recheck(fake_db):
    """The old wait node wrote `next_check_at` and nothing ever read it."""
    lead_id = make_lead(fake_db, status="CALLING", awaiting_transcript=True)
    result = run(server.run_supervisor(lead_id))
    assert result["next_action"] == "wait"

    queued = run(fake_db.scheduled_actions.find({"lead_id": lead_id}).to_list(None))
    assert len(queued) == 1
    assert queued[0]["kind"] == "supervisor" and queued[0]["state"] == "PENDING"
    assert lead_doc(fake_db, lead_id)["next_check_at"] == queued[0]["run_at"]


def test_a_failing_action_is_marked_failed_not_retried_forever(fake_db):
    lead_id = make_lead(fake_db)
    run(fake_db.scheduled_actions.insert_one(
        server.to_mongo(
            server.ScheduledAction(
                lead_id=lead_id, kind="not_a_real_kind", run_at=server.now_iso()
            )
        )
    ))
    summary = run(server.run_tick())
    assert summary["failed"] == 1 and summary["drained"] == 0

    action = run(fake_db.scheduled_actions.find_one({"lead_id": lead_id}))
    assert action["state"] == "FAILED" and "not_a_real_kind" in action["error"]
    assert "scheduled.not_a_real_kind_failed" in reasons(fake_db, lead_id)


def test_concurrent_ticks_cannot_run_the_same_action_twice(fake_db):
    lead_id = make_lead(fake_db, status="NURTURE")
    run(server.schedule_action(lead_id, "notify", server.now() - timedelta(minutes=1)))
    first = run(server.run_tick())
    second = run(server.run_tick())
    assert first["drained"] == 1
    assert second["drained"] == 0  # already claimed and DONE


# ---------- blocker #3: leads stranded mid-call get rescued ----------


def test_tick_rescues_a_lead_stuck_in_calling(fake_db):
    stale = (server.now() - timedelta(hours=2)).isoformat()
    lead_id = make_lead(fake_db, status="CALLING", awaiting_transcript=True)
    run(fake_db.leads.update_one({"id": lead_id}, {"$set": {"updated_at": stale}}))

    summary = run(server.run_tick())
    assert summary["rescued"] == 1

    doc = lead_doc(fake_db, lead_id)
    assert doc["status"] == "NURTURE" and doc["awaiting_transcript"] is False
    assert "call.timeout" in reasons(fake_db, lead_id)


def test_tick_resumes_qualification_when_a_transcript_survived(fake_db):
    """Process died between 'transcript written' and 'qualification ran'."""
    stale = (server.now() - timedelta(hours=2)).isoformat()
    lead_id = make_lead(fake_db, status="CALLING")
    run(fake_db.leads.update_one(
        {"id": lead_id},
        {"$set": {"transcript": providers.mock_transcript("Emily Chen", 2), "updated_at": stale}},
    ))

    summary = run(server.run_tick())
    assert summary["requalified"] == 1
    assert lead_doc(fake_db, lead_id)["status"] == "HOT"


def test_tick_leaves_a_fresh_call_alone(fake_db):
    lead_id = make_lead(fake_db, status="CALLING", awaiting_transcript=True)
    summary = run(server.run_tick())
    assert summary["rescued"] == 0
    assert lead_doc(fake_db, lead_id)["status"] == "CALLING"


# ---------- blocker #4: providers cannot claim a success they did not get ----------


def test_a_failed_booking_does_not_mark_the_lead_booked(fake_db, monkeypatch):
    async def rejected(**kwargs):
        return live_failure("calcom", 422)

    monkeypatch.setattr(providers.booker, "book", rejected)
    lead_id = make_lead(fake_db, status="QUALIFIED", score=75)

    with pytest.raises(HTTPException) as exc:
        run(server.book(lead_id, server.BookSlotRequest(slot_iso="2026-09-01T10:00:00Z")))
    assert exc.value.status_code == 502

    assert lead_doc(fake_db, lead_id)["status"] == "QUALIFIED"
    assert run(fake_db.appointments.find({"lead_id": lead_id}).to_list(None)) == []
    assert "booking.failed" in reasons(fake_db, lead_id)


def test_a_successful_booking_transitions_and_records_the_appointment(fake_db):
    lead_id = make_lead(fake_db, status="QUALIFIED", score=75)
    appt = run(server.book(lead_id, server.BookSlotRequest(slot_iso="2026-09-01T10:00:00Z")))
    assert appt.slot_iso == "2026-09-01T10:00:00Z"
    assert lead_doc(fake_db, lead_id)["status"] == "BOOKED"
    assert len(run(fake_db.appointments.find({"lead_id": lead_id}).to_list(None))) == 1


def test_booking_an_illegal_status_is_refused_before_the_provider_is_called(fake_db, monkeypatch):
    called = []

    async def spy(**kwargs):
        called.append(kwargs)
        raise AssertionError("provider must not be called on an illegal transition")

    monkeypatch.setattr(providers.booker, "book", spy)
    lead_id = make_lead(fake_db, status="NEW")
    with pytest.raises(HTTPException) as exc:
        run(server.book(lead_id, server.BookSlotRequest(slot_iso="2026-09-01T10:00:00Z")))
    assert exc.value.status_code == 400 and called == []


def test_a_live_notification_failure_is_recorded_before_the_mock_fallback(fake_db, monkeypatch):
    async def failed(**kwargs):
        return live_failure("resend", 403)

    monkeypatch.setattr(providers.notifier, "send_email", failed)
    lead_id = make_lead(fake_db)
    result = run(server.send_notification(lead_doc(fake_db, lead_id), "email", "nurture_sequence"))

    assert result["provider"] == "mock-resend"
    reason_list = reasons(fake_db, lead_id)
    # Both the real failure and the fallback are in the log — not just the happy one.
    assert "email/nurture_sequence/provider_failed" in reason_list
    assert "email/nurture_sequence" in reason_list

    health = run(fake_db.provider_health.find_one({"_id": "resend"}))
    assert health["failures"] >= 1


def test_provider_health_tracks_calls_and_failures(fake_db):
    lead_id = make_lead(fake_db, sim_profile=0)
    run(server.run_ai_pipeline(lead_id))
    health = run(fake_db.provider_health.find({}).to_list(None))
    by_spec = {h["_id"]: h for h in health}
    assert by_spec["vapi"]["mode"] == "MOCK" and by_spec["vapi"]["ok"] is True
    assert by_spec["hubspot"]["failures"] == 0


# ---------- blocker #5: lockdown ----------


def test_admin_routes_are_locked_when_no_token_is_configured(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        run(server.require_admin(x_admin_token="anything"))
    assert exc.value.status_code == 401


def test_admin_rejects_a_wrong_token_and_accepts_the_right_one(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "correct-horse")
    with pytest.raises(HTTPException):
        run(server.require_admin(x_admin_token="wrong"))
    with pytest.raises(HTTPException):
        run(server.require_admin(x_admin_token=None))
    assert run(server.require_admin(x_admin_token="correct-horse")) is True


def test_lead_capture_is_rate_limited_per_ip(fake_db, monkeypatch):
    monkeypatch.setattr(server, "LEAD_RATE_LIMIT_PER_MIN", 2)
    server._rate_buckets.clear()
    payload = server.LeadCreate(name="Spammer", phone="+14155559999")

    for _ in range(2):
        run(server.create_lead(payload, BackgroundTasks(), fake_request(host="9.9.9.9")))
    with pytest.raises(HTTPException) as exc:
        run(server.create_lead(payload, BackgroundTasks(), fake_request(host="9.9.9.9")))
    assert exc.value.status_code == 429
    # A different IP has its own budget.
    run(server.create_lead(payload, BackgroundTasks(), fake_request(host="8.8.8.8")))


def test_google_webhook_is_closed_when_unconfigured(fake_db, monkeypatch):
    monkeypatch.setattr(server, "GOOGLE_LEADS_WEBHOOK_KEY", None)
    payload = server.GoogleLeadPayload(google_key="guess")
    with pytest.raises(HTTPException) as exc:
        run(server.google_leads_webhook(payload, BackgroundTasks()))
    assert exc.value.status_code == 503


def test_google_webhook_rejects_a_wrong_key(fake_db, monkeypatch):
    monkeypatch.setattr(server, "GOOGLE_LEADS_WEBHOOK_KEY", "real-key")
    payload = server.GoogleLeadPayload(google_key="wrong-key")
    with pytest.raises(HTTPException) as exc:
        run(server.google_leads_webhook(payload, BackgroundTasks()))
    assert exc.value.status_code == 401


def test_google_webhook_ingests_a_valid_lead(fake_db, monkeypatch):
    monkeypatch.setattr(server, "GOOGLE_LEADS_WEBHOOK_KEY", "real-key")
    payload = server.GoogleLeadPayload(
        google_key="real-key",
        lead_id="g-1",
        form_id=42,
        user_column_data=[
            {"column_id": "FULL_NAME", "string_value": "Marcus Reed"},
            {"column_id": "EMAIL", "string_value": "marcus@example.com"},
            {"column_id": "PHONE_NUMBER", "string_value": "+14155550102"},
        ],
    )
    result = run(server.google_leads_webhook(payload, BackgroundTasks()))
    doc = lead_doc(fake_db, result["lead_id"])
    assert doc["name"] == "Marcus Reed" and doc["source"] == "google-ads"


# ---------- compliance ----------


def test_opt_out_blocks_every_channel(fake_db):
    lead_id = make_lead(fake_db, opted_out=True)
    result = run(server.send_notification(lead_doc(fake_db, lead_id), "sms", "book_slot"))
    assert result == {"blocked": "opted_out"}


def test_quiet_hours_defer_and_a_later_tick_sends(fake_db, monkeypatch):
    """The deferral used to be a dead event. Now it is a queued send."""
    monkeypatch.setattr(server, "QUIET_HOURS_ENABLED", True)
    monkeypatch.setattr(server, "QUIET_HOURS_START", 0)
    monkeypatch.setattr(server, "QUIET_HOURS_END", 24)

    lead_id = make_lead(fake_db)
    result = run(server.send_notification(lead_doc(fake_db, lead_id), "sms", "book_slot"))
    assert "deferred_until" in result
    assert "sms/book_slot/deferred" in reasons(fake_db, lead_id)

    action = run(fake_db.scheduled_actions.find_one({"lead_id": lead_id}))
    assert action["kind"] == "notify" and action["payload"]["channel"] == "sms"

    # Quiet hours end; the queued send goes out for real.
    monkeypatch.setattr(server, "QUIET_HOURS_ENABLED", False)
    run(fake_db.scheduled_actions.update_one(
        {"id": action["id"]}, {"$set": {"run_at": server.now_iso()}}
    ))
    assert run(server.run_tick())["drained"] == 1
    assert "sms/book_slot" in reasons(fake_db, lead_id)


def test_inbound_stop_opts_the_lead_out(fake_db):
    lead_id = make_lead(fake_db, phone="+14155550101")
    resp = run(
        server.twilio_sms_webhook(
            fake_request(form={"From": "+14155550101", "Body": "STOP", "MessageSid": "SM1"})
        )
    )
    assert b"unsubscribed" in resp.body
    assert lead_doc(fake_db, lead_id)["opted_out"] is True
    assert "lead.opted_out" in reasons(fake_db, lead_id)


def test_inbound_reply_appends_to_the_transcript(fake_db):
    lead_id = make_lead(fake_db, phone="+14155550101", status="NURTURE")
    run(
        server.twilio_sms_webhook(
            fake_request(
                form={"From": "+14155550101", "Body": "Actually yes, $900k", "MessageSid": "SM2"}
            )
        )
    )
    doc = lead_doc(fake_db, lead_id)
    assert doc["transcript"][-1] == {"role": "lead", "text": "Actually yes, $900k"}
    assert "sms.inbound" in reasons(fake_db, lead_id)


def test_inbound_sms_is_idempotent_on_message_sid(fake_db):
    lead_id = make_lead(fake_db, phone="+14155550101", status="NURTURE")
    form = {"From": "+14155550101", "Body": "hello", "MessageSid": "SM3"}
    run(server.twilio_sms_webhook(fake_request(form=form)))
    run(server.twilio_sms_webhook(fake_request(form=form)))
    assert len(lead_doc(fake_db, lead_id)["transcript"]) == 1


def test_inbound_sms_from_an_unknown_number_is_a_no_op(fake_db):
    resp = run(
        server.twilio_sms_webhook(fake_request(form={"From": "+10000000000", "Body": "hi"}))
    )
    assert b"<Response></Response>" in resp.body


# ---------- state machine integrity ----------


def test_an_illegal_dial_is_recorded_instead_of_swallowed(fake_db):
    """CALLING is unreachable from BOOKED. The old code raised HTTP 400 into a
    blanket except and surfaced an opaque `pipeline.error`."""
    lead_id = make_lead(fake_db, status="BOOKED")
    run(server.run_ai_pipeline(lead_id))

    reason_list = reasons(fake_db, lead_id)
    assert "call.blocked" in reason_list
    assert "pipeline.error" not in reason_list
    assert lead_doc(fake_db, lead_id)["status"] == "BOOKED"


def test_rerun_goes_through_the_state_machine(fake_db):
    lead_id = make_lead(fake_db, status="BOOKED", score=90)
    run(server.rerun(lead_id, BackgroundTasks()))

    doc = lead_doc(fake_db, lead_id)
    assert doc["status"] == "NURTURE" and doc["score"] == 0 and doc["transcript"] == []
    # The audit log records the reset as a real transition, not a silent overwrite.
    assert ("BOOKED", "NURTURE") in [
        (e["from_status"], e["to_status"])
        for e in events(fake_db, lead_id)
        if e["kind"] == "transition"
    ]


def test_transition_rejects_an_illegal_hop(fake_db):
    lead_id = make_lead(fake_db, status="NEW")
    with pytest.raises(HTTPException) as exc:
        run(server.transition(lead_id, "BOOKED"))
    assert exc.value.status_code == 400


def test_transition_to_the_same_status_is_a_no_op(fake_db):
    lead_id = make_lead(fake_db, status="NEW")
    run(server.transition(lead_id, "NEW"))
    assert [e for e in events(fake_db, lead_id) if e["kind"] == "transition"] == []


# ---------- reporting ----------


def test_analytics_counts_the_funnel_in_one_aggregation(fake_db):
    for i, status in enumerate(["NEW", "HOT", "HOT", "BOOKED", "NURTURE"]):
        make_lead(fake_db, phone=f"+1415551{i:04d}", status=status)
    a = run(server.analytics())
    assert a["total"] == 5 and a["hot"] == 2 and a["booked"] == 1
    assert a["qualified"] == 3  # QUALIFIED + HOT + BOOKED
    assert a["conversion_rate"] == 20.0
    assert [f["status"] for f in a["funnel"]] == server.FUNNEL_ORDER


def test_health_reports_db_and_provider_modes(fake_db):
    h = run(server.health())
    assert h["status"] == "ok" and h["db"] == "ok"
    assert h["demo_mode"] is True
    assert set(h["providers"].values()) == {"MOCK"}


def test_providers_endpoint_reports_last_call_outcome(fake_db):
    lead_id = make_lead(fake_db, sim_profile=0)
    run(server.run_ai_pipeline(lead_id))
    payload = run(server.list_providers())
    by_name = {p["name"]: p for p in payload["providers"]}
    assert payload["demo_mode"] is True
    assert by_name["vapi"]["mode"] == "MOCK" and by_name["vapi"]["last_ok"] is True
    assert by_name["vapi"]["calls"] >= 1
    # Every registered provider is reported, even ones never called.
    assert set(by_name) == set(providers.PROVIDER_SPECS)


def test_eval_grades_against_the_rubric_and_flags_baseline_mode(fake_db):
    for i in range(providers.MOCK_PROFILE_COUNT):
        lead = server.Lead(
            name=f"Sim {i}", phone=f"+1415556{i:04d}", email=f"s{i}@x.com",
            source="sim", sim_profile=i,
        )
        run(fake_db.leads.insert_one(server.to_mongo(lead)))
        run(server.run_ai_pipeline(lead.id))

    report = run(server.eval_run())
    assert report["graded"] == providers.MOCK_PROFILE_COUNT
    assert report["rubric_agreement"] == 1.0
    assert report["hallucination_rate"] == 0.0
    # Honest labelling: with no LLM key both sides are the same code path.
    assert report["baseline_only"] is True
    assert report["disagreements"] == []
