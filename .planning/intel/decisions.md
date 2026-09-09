# Extracted Architectural & Design Decisions

## ADR-0001: The Agent Proposes, The State Machine Enforces
- source: docs/PRD.md
- status: locked (Accepted)
- decision: The agent proposes, the state machine enforces. The LLM extracts fields and picks next actions; scoring, transitions, CRM writes, and booking commits are deterministic code.
- scope: agentic boundary, state machine, lifecycle enforcement

## ADR-0002: Queue-less Asynchronous Architecture
- source: docs/PRD.md
- status: locked (Accepted)
- decision: No Redis, no Celery. Use FastAPI BackgroundTasks for the fast reactive path, and a MongoDB `scheduled_actions` collection plus cron-driven `/api/tick` for the slow autonomous path.
- scope: background workers, job queues, task scheduling

## ADR-0003: Single Unified Qualification Code Path
- source: docs/PRD.md
- status: locked (Accepted)
- decision: Both the mock demo path and live webhook path must converge on `qualify_and_route(lead_id)` — one single code path so live integrations cannot drift from the demo. Qualification never runs on an empty transcript.
- scope: pipeline routing, mock/live convergence, transcript handling

## ADR-0004: Fail-Closed Admin Security Model
- source: docs/PRD.md
- status: locked (Accepted)
- decision: Destructive and administrative endpoints (/api/seed, /api/simulate, /api/tick, /api/reset) must fail closed with HTTP 401 when `ADMIN_TOKEN` is unset or mismatched using constant-time string comparison (`secrets.compare_digest`). The public deploy is read-only by default.
- scope: authentication, security, admin endpoints
