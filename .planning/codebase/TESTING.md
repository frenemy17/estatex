---
last_mapped_commit: 722da52125826f52cb0781fbfb78ec823fc64055
---

# Testing Patterns

**Analysis Date:** 2026-09-09

## Test Framework

**Backend Runner & Tools:**
- **Framework:** `pytest 9.1.1` (`pytest>=8.0.0` in `backend/requirements.txt`).
- **Parallelization:** `pytest-xdist 3.8.0` distributing tests across worker processes.
- **Config:** `backend/pytest.ini` configuring test paths, options (`-n auto`), and warning filters.

**Frontend Runner:**
- **Framework:** Jest via `craco test` (`npm test` in `frontend/package.json`).
- **Status:** Currently, no unit tests are authored under `frontend/src/`. All existing test coverage resides in the backend suite.

**Run Commands:**
```bash
# Run entire backend test suite in parallel (69 tests, ~1.3s)
backend/.venv/bin/pytest backend/tests/

# Run a specific test module
backend/.venv/bin/pytest backend/tests/test_state_machine.py
backend/.venv/bin/pytest backend/tests/test_providers.py
backend/.venv/bin/pytest backend/tests/test_tick.py
backend/.venv/bin/pytest backend/tests/test_v2_api.py

# Run a single test case
backend/.venv/bin/pytest backend/tests/test_tick.py -k test_tick_drains_due_scheduled_actions
```

## Test Architecture & Philosophy

The test suite in `backend/tests/` was specifically designed with a strict zero-network, zero-database philosophy:
- **Zero Running Server:** Endpoint async functions are invoked directly in-process.
- **Zero Real Database:** An in-memory Motor double (`FakeDatabase` in `backend/tests/conftest.py`) simulates MongoDB collections, queries, projections, upserts, cursors, and single-stage aggregations.
- **Zero Live Network Calls:** `conftest.py` automatically sets `DEMO_MODE=1` and sets external delays to 0 (`DEMO_CALL_DELAY_SECONDS=0`) prior to importing server modules.

## In-Memory Database Double (`backend/tests/conftest.py`)

The test double implements the exact subset of the Motor API utilized by `server.py` and `agents/graph.py`:
- Query operators: `$in`, `$nin`, `$lt`, `$lte`, `$gt`, `$gte`, `$ne`.
- Update operators: `$set`, `$inc`, `$setOnInsert` (with `upsert=True` support).
- Cursor operations: `.sort(...)`, `.to_list(...)`, and projection `{ "_id": 0, ... }`.
- Unsupported query patterns deliberately raise `NotImplementedError` rather than returning empty sets, preventing silent false-positive test passes.

## Test Suites & Coverage

| Test File | Focus Area | What It Validates |
|:---|:---|:---|
| `backend/tests/test_state_machine.py` | Core Lifecycle & Invariants | `ALLOWED_TRANSITIONS` rules, invalid transition rejection, deterministic 0–100 rubric calculation. |
| `backend/tests/test_providers.py` | Integration Contracts | Mock mode fallback, provider result metadata (`ProviderResult`), provider status detection, and provider health logs. |
| `backend/tests/test_tick.py` | Autonomy & Ingestion | IP rate limiting, Google Ads lead ingestion, webhook signature check, scheduled action claiming, stuck call rescue, and requalification. |
| `backend/tests/test_v2_api.py` | Agentic Graph & Handoff | Multi-agent supervisor routing, `MongoCheckpointer` save/load/clear, human interrupt `{_interrupt: True}`, and `/approve` / `/reject` resuming. |

## Mocking & Isolation Patterns

**1. Provider Isolation:**
- Providers are isolated by environment variable overrides in `conftest.py`:
  ```python
  os.environ["DEMO_MODE"] = "1"
  os.environ.setdefault("DEMO_CALL_DELAY_SECONDS", "0")
  os.environ.setdefault("QUIET_HOURS_ENABLED", "0")
  ```

**2. Asynchronous Endpoint Execution:**
- Tests directly execute async route handlers using the fake database context:
  ```python
  @pytest.mark.anyio
  async def test_lead_capture_creates_new_lead(fakedb):
      payload = LeadCaptureIn(
          name="Jane Doe",
          phone="+15551234567",
          email="jane@example.com"
      )
      res = await create_lead(payload, background_tasks=BackgroundTasks(), db=fakedb)
      assert res["status"] == "NEW"
  ```

**3. Simulating External Failures:**
- Tests verify that external live failures return HTTP 502 and do not advance state:
  ```python
  # When Cal.com returns a failure, verify state machine refuses to commit BOOKED
  result = await book_appointment(lead_id="test-1", slot="2026-09-10T10:00:00Z", db=fakedb)
  assert lead["status"] != "BOOKED"
  ```

---

*Testing analysis: 2026-09-09*
*Update after adding test suites or modifying test harnesses*
