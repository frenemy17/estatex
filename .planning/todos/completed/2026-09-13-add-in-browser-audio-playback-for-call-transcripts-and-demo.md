---
created: 2026-09-13T07:06:22.121Z
title: Add in-browser audio playback for call transcripts and demo mode
area: ui
severity: minor
files:
  - frontend/src/pages/LeadDetail.jsx:295
  - backend/.env:28
---

## Problem

Real cellular telephone network calls via Twilio or Vapi are restricted internationally (e.g., Indian phone numbers are blocked on Twilio trial accounts due to regulatory/carrier constraints) and subject to carrier latency. For portfolio demonstrations, live pitches, and resume presentations, presenters need a zero-friction, audible demonstration of the AI voice concierge without relying on international phone carriers.

## Solution

1. Add a speech synthesizer / audio playback button ("🔊 Play Call Audio") in `frontend/src/pages/LeadDetail.jsx` that reads the conversation turns out loud using the browser Web Speech API (`window.speechSynthesis`) with distinct voices for the AI Agent and the prospective home buyer.
2. Ensure the demo mode cleanly coordinates live providers: Live Groq LLM qualification, Live HubSpot CRM deal creation, Live Cal.com appointment booking, and Live Resend email notification, while bypassing cellular carrier gates via `VOICE_ENABLED=0` and `SMS_ENABLED=0`.
