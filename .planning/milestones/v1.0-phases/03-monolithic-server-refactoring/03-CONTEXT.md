# Phase 3: Monolithic Server Refactoring — Context & Decisions

## Executive Summary

Phase 3 deconstructs the 2,284-line monolithic `backend/server.py` into clean, single-responsibility domain modules (`backend/core/`) and route controllers (`backend/routes/`). 

The refactoring is purely architectural and preserves 100% of external API behavior, route paths, payload schemas, and response formats. Crucially, it preserves backward compatibility with the test suite by having `server.py` re-export all domain models, database handles, pipeline functions, and route handlers.

---

## Locked Architectural Decisions

### D-01: Modular Directory Architecture
```
backend/
├── core/
│   ├── __init__.py
│   ├── database.py       # Async Mongo connection, _DBProxy, get_db, close_db, to_mongo, now, now_iso
│   ├── models.py         # Pydantic models (Lead, Event, CallLog, ScheduledAction, DTOs)
│   ├── state_machine.py  # Lead status transitions, invariants, record_event, transition helper
│   ├── scoring.py        # Rubric scoring, Groq/OpenAI prompts, score_and_route, qualify_and_route
│   ├── pipeline.py       # LangGraph multi-agent orchestration (dialer, qualifier, enricher, router)
│   ├── tick.py           # Background autonomy scheduler, exponential backoff, DLQ, stranded rescues
│   └── rate_limit.py     # MongoDB-backed sliding window rate limiter with in-memory fallback
├── routes/
│   ├── __init__.py
│   ├── leads.py          # /api/lead, /api/leads, /api/leads/bulk, /api/leads/:id/* (actions & details)
│   ├── webhooks.py       # /api/webhooks/google-leads, /api/webhooks/vapi, /api/voice/twiml, /api/voice/gather, /api/webhooks/twilio-sms
│   ├── admin.py          # /api/tick, /api/queue/dead-letter/*, /api/analytics, /api/seed, /api/reset, /api/simulate
│   └── providers.py      # /api/providers, /api/providers/:name/test
└── server.py             # FastAPI app shell mounting APIRouter modules + backward-compatible symbol re-exports
```

### D-02: Zero Breaking Changes & Test Harness Compatibility
- `backend/tests/test_tick.py` and `backend/tests/test_providers.py` directly import symbols from `server` (e.g. `import server`, `server.db`, `server.Lead`, `server.run_tick`, `server.run_ai_pipeline`, etc.).
- `conftest.py` uses `monkeypatch.setattr(server, "_db", db, raising=False)` and `server._compiled_graph = None`.
- `core/database.py` checks both local `_db` and `sys.modules["server"]._db` to guarantee test harness transparent compatibility.
- `server.py` re-exports all public symbols from `core.*` and `routes.*`.

### D-03: Separation of Concerns
- **`core/`**: Pure domain logic and infrastructure. Does not depend on FastAPI routes or HTTP request objects (except `rate_limit` which inspects `request.client`).
- **`routes/`**: FastAPI routers (`APIRouter`). Handles request validation, HTTP exceptions, dependency injection (`require_admin`), and delegates business logic to `core/` services.
- **`server.py`**: Assembly shell. Configures FastAPI, CORS, lifespan, mounts routers, and serves as top-level entry point for Uvicorn (`server:app`).

---

## Requirements Traceability

| Requirement | Description | Delivered in Plan |
|-------------|-------------|-------------------|
| **MOD-01** | Split monolithic `backend/server.py` into modular route controllers (`routes/leads.py`, `routes/webhooks.py`, `routes/admin.py`, `routes/providers.py`) | `03-02-PLAN.md` |
| **MOD-02** | Extract state machine and rubric scoring logic into `backend/core/` (`state_machine.py`, `scoring.py`, `tick.py`, `pipeline.py`, `database.py`, `models.py`) | `03-01-PLAN.md` |

---

## Test & Verification Guarantees
- 100% of existing 78 unit/integration tests in `backend/tests/` continue to pass without editing test files.
- `server:app` boots cleanly with uvicorn and all route endpoints retain identical signatures and status codes.
