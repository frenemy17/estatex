# Phase 3: Monolithic Server Refactoring — Research & Dependency Analysis

## Overview

The purpose of Phase 3 is to refactor `backend/server.py` (currently 2,284 lines) into clean modular packages:
- `backend/core/`: Database connections, domain models, finite state machine, rubric scoring, LangGraph multi-agent pipeline, and autonomous background tick loop.
- `backend/routes/`: FastAPI `APIRouter` modules grouped by domain (leads, webhooks, admin, providers).
- `backend/server.py`: Lightweight application entry point that mounts the routers and re-exports symbols for backward compatibility with the test suite.

---

## Codebase Analysis & Coupling Points

### 1. In-Memory Database Swap in Tests (`fake_db` fixture)
`backend/tests/conftest.py` contains:
```python
@pytest.fixture
def fake_db(monkeypatch):
    import server

    db = FakeDB()
    monkeypatch.setattr(server, "_db", db, raising=False)
    monkeypatch.setattr(server, "_client", None, raising=False)
    server._compiled_graph = None  # rebuild against the fake db
    yield db
    server._compiled_graph = None
```
**Research Finding:**
The test harness directly patches `server._db`. To ensure zero breakage without modifying tests:
- `core/database.py`'s `get_db()` must check `sys.modules.get("server")._db` first if `server._db` is not None.
- `server.py` defines `_db = None` and `_client = None` at module level, re-exporting `db = core.database.db`.
- `_compiled_graph` in `core/pipeline.py` should be exposed or synchronized on `server._compiled_graph`.

### 2. Direct Symbol Imports in `backend/tests/`
Tests in `test_tick.py` and `test_providers.py` import symbols directly:
```python
import server
server.Lead(...)
server.ScheduledAction(...)
server.to_mongo(...)
server.now_iso()
server.now()
server.run_tick()
server.run_ai_pipeline(...)
server.create_lead(...)
server.list_dead_letter()
server.retry_dead_letter(...)
server.voice_twiml_endpoint(...)
server.voice_gather_endpoint(...)
server.google_leads_webhook(...)
server.vapi_webhook(...)
server.inbound_sms_webhook(...)
server.require_admin(...)
server.LEAD_RATE_LIMIT_PER_MIN
server._rate_buckets
server.GOOGLE_LEADS_WEBHOOK_KEY
server.VAPI_WEBHOOK_SECRET
server.ADMIN_TOKEN
```
**Research Finding:**
By re-exporting all of these variables, functions, and models from `server.py`, external importers see no change in module interface, enabling 100% test compatibility.

### 3. Acyclic Module Hierarchy
To avoid circular imports between `core/` and `routes/`:
```
core/database.py      (lowest level: Mongo connection, _DBProxy, timestamps, to_mongo)
      ▲
core/models.py        (Pydantic schemas)
      ▲
core/state_machine.py (FSM transitions, events)
      ▲
core/scoring.py       (Rubric analysis, Groq/OpenAI calls)
      ▲
core/pipeline.py      (LangGraph orchestration)
      ▲
core/tick.py          (Autonomous scheduler loop & DLQ)
      ▲
routes/*              (FastAPI endpoints referencing core)
      ▲
server.py             (Mounts routes & re-exports symbols)
```

---

## Plan Decomposition

### Wave 1: Domain Logic Extraction (`03-01-PLAN.md`)
- Create `backend/core/database.py` with dynamic `server._db` fallback in `get_db()`.
- Create `backend/core/models.py` with all Pydantic document schemas and request models.
- Create `backend/core/state_machine.py` with transition rules, guards, and `record_event()`.
- Create `backend/core/rate_limit.py` with MongoDB sliding-window and in-memory fallback.
- Create `backend/core/scoring.py` with rubric prompt and scoring extraction.
- Create `backend/core/pipeline.py` with LangGraph nodes (`dialer`, `qualifier`, `enricher`, `router`) and `run_ai_pipeline`.
- Create `backend/core/tick.py` with `run_tick`, backoff calculation, DLQ transitions, stranded lead rescue, and nurture check.
- Verify that `core/` imports cleanly and passes isolated tests.

### Wave 2: Route Extraction & Server Assembly (`03-02-PLAN.md`)
- Create `backend/routes/auth.py` with `require_admin`.
- Create `backend/routes/leads.py` with lead capture, CRUD, and manual action triggers.
- Create `backend/routes/webhooks.py` with Google, Vapi, and Twilio voice/SMS handlers.
- Create `backend/routes/admin.py` with tick, dead-letter queue management, analytics, seed, reset, and simulation.
- Create `backend/routes/providers.py` with provider status queries and test triggers.
- Refactor `backend/server.py` to assemble routers and re-export all domain symbols.
- Execute full test suite (`backend/.venv/bin/pytest backend/tests/`) to verify 100% green pass.
