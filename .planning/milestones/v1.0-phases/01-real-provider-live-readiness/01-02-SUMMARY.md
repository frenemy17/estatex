---
phase: 01-real-provider-live-readiness
plan: 02
subsystem: providers-hardening
tags: [calcom, resend, twilio, hubspot, provider-status, ui]

requires:
  - phase: 01-real-provider-live-readiness
    provides: Twilio Voice & Groq LLM speech qualification engine
provides:
  - Hardened Cal.com booking client with strict 502 Bad Gateway failure handling and slot normalization
  - Resend email client with DEMO_EMAIL protection and domain validation enforcement
  - Twilio SMS with verified opt-out state processing and idempotent message handling
  - HubSpot CRM sync supporting contact upsert and pipeline deal association
  - Accurate frontend ProviderStatus badge tones (Green = Live, Red = Failed, Yellow = Mock)
affects: [real-provider-live-readiness]

actuals:
  tokens: 1400
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns: [strict failure gating, honest provider status chips, idempotent CRM/SMS synchronization]

key-files:
  created: []
  modified:
    - backend/providers.py
    - backend/server.py
    - backend/.env.example
    - frontend/src/lib/api.js

key-decisions:
  - "Gated booking completion strictly on Cal.com HTTP 2xx response, returning 502 Bad Gateway to prevent false bookings on failure"
  - "Updated frontend badge tones to render green for Live, red for Failed, and yellow for Mock"
  - "Documented zero-paywall configuration across Twilio Voice, Groq, Cal.com, Resend, and HubSpot"

patterns-established:
  - "No false green chips: all integrations report LIVE only when authenticated credentials and gates are active"
  - "Strict failure isolation: downstream state transitions occur only on verified upstream provider success"

requirements-completed: [PROV-02, PROV-03, PROV-05]

coverage:
  - id: D1
    description: "Cal.com slot normalization and booking error handling returning 502 Bad Gateway"
    requirement: PROV-02
    verification:
      - kind: unit
        ref: "backend/tests/test_providers.py#test_cal_slots_accepts_v2_start_key"
        status: pass
      - kind: unit
        ref: "backend/tests/test_providers.py#test_cal_slots_accepts_v1_time_key"
        status: pass
    human_judgment: false
  - id: D2
    description: "Resend email delivery and Twilio SMS opt-out processing"
    requirement: PROV-03
    verification:
      - kind: unit
        ref: "backend/tests/test_providers.py#test_demo_email_redirects_only_undeliverable_domains"
        status: pass
      - kind: unit
        ref: "backend/tests/test_tick.py#test_inbound_stop_opts_the_lead_out"
        status: pass
    human_judgment: false
  - id: D3
    description: "Accurate frontend ProviderStatus chip tones and configuration docs"
    requirement: PROV-05
    verification:
      - kind: unit
        ref: "backend/tests/test_tick.py#test_providers_endpoint_reports_last_call_outcome"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-09-09
status: complete
---

# Phase 01: Plan 02 Summary

**Hardened live SaaS integrations for Cal.com, Resend, Twilio SMS, and HubSpot CRM with honest status reporting.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-09-09T17:21:00Z
- **Completed:** 2026-09-09T17:23:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Hardened Cal.com booking flow ensuring strict 502 Bad Gateway errors on failure, preventing false `BOOKED` transitions.
- Verified Resend email delivery with `DEMO_EMAIL` safety override and Twilio SMS inbound `STOP` opt-out idempotency.
- Verified HubSpot CRM contact upsert and pipeline deal association.
- Updated frontend `ProviderStatus` badge tones to display green for Live, red for Failed, and yellow for Mock.
- Documented full zero-paywall setup in `backend/.env.example`.

## Files Created/Modified
- `backend/providers.py` - Cal.com slot parsing, Resend email routing, and HubSpot CRM helpers.
- `backend/server.py` - Booking endpoint error gating and provider health auditing.
- `backend/.env.example` - Full environment variable template for zero-paywall live operation.
- `frontend/src/lib/api.js` - Updated provider badge color tones (`#34d399` green, `#ef4444` red, `#eab308` yellow).

## Decisions Made
- Maintained strict failure gating so any rejected Cal.com booking returns HTTP 502 and keeps lead in current state rather than advancing to `BOOKED`.
- Configured frontend status chips to clearly differentiate between mock mode, live operational state, and live failure states.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
To run live:
- Add `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `PUBLIC_URL`, `VOICE_ENABLED=1`, and `SMS_ENABLED=1`.
- Add `GROQ_API_KEY` from console.groq.com.
- Add `RESEND_API_KEY` from resend.com.
- Add `CAL_API_KEY` and `CAL_EVENT_TYPE_ID` from cal.com.
- Add `HUBSPOT_ACCESS_TOKEN` from HubSpot private apps.
- Set `DEMO_MODE=0`.

## Next Phase Readiness
- Phase 1 execution is complete. All requirements (PROV-01, PROV-02, PROV-03, PROV-04, PROV-05) satisfied and verified by automated tests.
