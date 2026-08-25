"""Provider-layer unit tests.

These are pure functions and mock-mode calls — no network, no database. They
cover the parsing and mode-derivation bugs that made adding a real API key make
the product *worse*:

* a Cal.com payload shape the old code KeyError'd on, then silently mocked
* a Vapi ``end-of-call-report`` whose transcript was never read at all
* HubSpot/Resend reporting ``ok: True`` regardless of HTTP status
"""
from __future__ import annotations

from asyncio import run

import providers
from providers import ProviderResult


# ---------- ProviderResult honesty ----------


def test_live_failure_only_when_live_and_not_ok():
    live_bad = ProviderResult(spec="calcom", provider="calcom", mode="LIVE", ok=False, status=500)
    live_ok = ProviderResult(spec="calcom", provider="calcom", mode="LIVE", ok=True, status=200)
    mocked = ProviderResult(spec="calcom", provider="mock-calcom", mode="MOCK", ok=True)
    assert live_bad.live_failure is True
    assert live_ok.live_failure is False
    # A mock is not a failure — it is the documented no-key behaviour.
    assert mocked.live_failure is False


def test_to_meta_carries_status_and_truncates_error():
    r = ProviderResult(
        spec="hubspot", provider="hubspot", mode="LIVE", ok=False, status=409, error="x" * 900
    )
    meta = r.to_meta()
    assert meta["ok"] is False and meta["status"] == 409
    assert len(meta["error"]) == 500


# ---------- mode derivation ----------


def test_demo_mode_forces_every_provider_to_mock(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_pretend")
    status = {p["name"]: p for p in providers.all_provider_status()}
    assert all(p["mode"] == "MOCK" for p in status.values())
    # Still reported as configured — DEMO_MODE overrides use, not presence.
    assert status["groq"]["configured"] is True
    assert status["groq"]["missing_env"] == []


def test_keys_without_the_gate_stay_mock(monkeypatch):
    """Having Twilio credentials is not the same as being allowed to text.

    US SMS needs A2P 10DLC approval, so SMS_ENABLED is a separate opt-in.
    """
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "+15550000000")
    monkeypatch.delenv("SMS_ENABLED", raising=False)
    st = providers.provider_status("twilio")
    assert st["configured"] is True and st["gate_open"] is False and st["mode"] == "MOCK"

    monkeypatch.setenv("SMS_ENABLED", "1")
    assert providers.provider_status("twilio")["mode"] == "LIVE"


def test_missing_env_is_reported_per_key(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("VAPI_API_KEY", "k")
    monkeypatch.delenv("VAPI_PHONE_NUMBER_ID", raising=False)
    st = providers.provider_status("vapi")
    assert st["configured"] is False
    assert st["missing_env"] == ["VAPI_PHONE_NUMBER_ID"]


# ---------- Cal.com slot parsing (the silent-mock bug) ----------


def test_cal_slots_accepts_v2_start_key():
    payload = {"data": {"2026-09-01": [{"start": "2026-09-01T10:00:00Z"}]}}
    assert providers._parse_cal_slots(payload) == ["2026-09-01T10:00:00Z"]


def test_cal_slots_accepts_v1_time_key():
    payload = {"slots": {"2026-09-01": [{"time": "2026-09-01T10:00:00Z"}]}}
    assert providers._parse_cal_slots(payload) == ["2026-09-01T10:00:00Z"]


def test_cal_slots_accepts_flat_list_and_bare_strings():
    assert providers._parse_cal_slots({"data": ["2026-09-01T10:00:00Z"]}) == [
        "2026-09-01T10:00:00Z"
    ]
    assert providers._parse_cal_slots(
        {"data": [{"startTime": "2026-09-01T11:00:00Z"}]}
    ) == ["2026-09-01T11:00:00Z"]


def test_cal_slots_empty_payload_is_empty_not_an_exception():
    assert providers._parse_cal_slots({}) == []
    assert providers._parse_cal_slots({"data": {}}) == []


# ---------- Vapi transcript parsing (blocker #1) ----------


def test_vapi_structured_messages_drop_system_and_map_roles():
    message = {
        "artifact": {
            "messages": [
                {"role": "system", "message": "you are ava"},
                {"role": "assistant", "message": "Hi, is now a good time?"},
                {"role": "user", "message": "Yes, looking to buy."},
            ]
        }
    }
    turns = providers.parse_vapi_transcript(message)
    assert turns == [
        {"role": "agent", "text": "Hi, is now a good time?"},
        {"role": "lead", "text": "Yes, looking to buy."},
    ]


def test_vapi_flat_transcript_string_is_split_by_speaker():
    message = {"artifact": {"transcript": "AI: What is your budget?\nUser: About 1.2 million."}}
    turns = providers.parse_vapi_transcript(message)
    assert [t["role"] for t in turns] == ["agent", "lead"]
    assert turns[1]["text"] == "About 1.2 million."


def test_vapi_empty_report_yields_no_turns():
    """The case that must never reach the scorer — an empty transcript scores 0."""
    assert providers.parse_vapi_transcript({"artifact": {}}) == []
    assert providers.parse_vapi_transcript({"artifact": {"transcript": "   "}}) == []


# ---------- DEMO_EMAIL redirection ----------


def test_demo_email_redirects_only_undeliverable_domains(monkeypatch):
    monkeypatch.setenv("DEMO_EMAIL", "me@mydomain.dev")
    assert providers.NotificationProvider.resolve_email("emily@example.com") == (
        "me@mydomain.dev",
        True,
    )
    # A real address is left alone — the override is for seed data, not a hijack.
    assert providers.NotificationProvider.resolve_email("real@gmail.com") == (
        "real@gmail.com",
        False,
    )


def test_no_demo_email_leaves_recipient_untouched(monkeypatch):
    monkeypatch.delenv("DEMO_EMAIL", raising=False)
    assert providers.NotificationProvider.resolve_email("emily@example.com") == (
        "emily@example.com",
        False,
    )


# ---------- mock mode is complete, not a stub ----------


def test_mock_voice_call_returns_a_usable_transcript():
    res = run(providers.voice.start_call(lead_id="l1", name="Emily", phone="+14155550101"))
    assert res.mode == "MOCK" and res.ok
    transcript = res.data["transcript"]
    assert len(transcript) >= 2
    assert {t["role"] for t in transcript} == {"agent", "lead"}


def test_mock_slots_are_future_iso_timestamps():
    slots = providers.mock_slots(4)
    assert len(slots) == 4
    assert all("T" in s for s in slots)


def test_llm_json_without_a_key_returns_the_fallback(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    fallback = {"intent": "buy"}
    data, res = run(providers.llm_json("sys", "prompt", fallback, label="t"))
    assert data == fallback
    assert res.mode == "MOCK" and res.live_failure is False
