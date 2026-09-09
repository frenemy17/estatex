---
last_mapped_commit: 722da52125826f52cb0781fbfb78ec823fc64055
---

# Coding Conventions

**Analysis Date:** 2026-09-09

## Naming Patterns

**Files & Directories:**
- **Python Files:** `snake_case.py` (e.g., `server.py`, `providers.py`, `test_state_machine.py`).
- **React Components & Pages:** `PascalCase.jsx` (e.g., `Dashboard.jsx`, `LeadDetail.jsx`, `Layout.jsx`).
- **JavaScript Utilities & Hooks:** `camelCase.js` (e.g., `api.js`, `usePoll.js`, `utils.js`).
- **Directories:** Lowercase, single words or hyphenated (e.g., `backend/agents`, `frontend/src/components/ui`).

**Functions & Variables (Python):**
- **Functions:** `snake_case` (e.g., `qualify_and_route()`, `compute_score()`, `require_admin()`).
- **Variables:** `snake_case` (e.g., `lead_id`, `scheduled_actions`, `correlation_id`).
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `ALLOWED_TRANSITIONS`, `PROVIDER_SPECS`, `CALL_TIMEOUT_MINUTES`).
- **Internal / Private Helpers:** Leading underscore (e.g., `_matches()`, `_project()`, `_env_ready()`, `_llm_json()`).

**Functions & Variables (JavaScript):**
- **Components:** `PascalCase` matching file name (e.g., `export default function Dashboard()`).
- **Event Handlers:** `handle` prefix (e.g., `handleAction()`, `handleSimulate()`, `handleSaveToken()`).
- **State & Hooks:** Standard React camelCase (e.g., `const [loading, setLoading] = useState(false)`).

**Types & Schemas:**
- **Pydantic Models:** `PascalCase` with descriptive suffix (e.g., `LeadCaptureIn`, `LeadDetailOut`, `ProviderResult`).
- **Graph State:** Standard dictionary schemas passed across nodes (`dict[str, Any]`).

## Code Style & Formatting

**Python:**
- Modern Python 3.10+ conventions:
  - Mandatory `from __future__ import annotations` at the top of every file.
  - Native union syntax: `int | None`, `dict[str, Any]`, `list[dict]` instead of `Union` / `List` / `Dict`.
  - Type annotations on all public functions, dataclasses, and endpoint parameters.
  - Dataclasses for structured value objects (`@dataclass class ProviderResult:`).
  - Explicit async/await syntax for all I/O operations touching the database.
  - Blocking network I/O executed using `asyncio.to_thread(func, *args)`.

**JavaScript / React:**
- Functional components exclusively; class components are forbidden.
- Strict React 19 compatibility without deprecated lifecycle hooks.
- Styling driven entirely by Tailwind CSS utility classes using `cn(...)` from `frontend/src/lib/utils.js` for dynamic merging.
- Sonner toasts (`toast.success()`, `toast.error()`) for immediate user feedback.

## Import Organization

**Python Order:**
1. Future imports: `from __future__ import annotations`.
2. Standard library imports: `os`, `sys`, `json`, `logging`, `datetime`, `secrets`, `asyncio`.
3. Third-party packages: `fastapi`, `pydantic`, `motor`, `requests`, `pytest`.
4. Internal application modules: `import providers`, `from .graph import StateGraph, MongoCheckpointer`.

**JavaScript Order:**
1. React core imports: `import React, { useState, useEffect, useMemo } from "react";`
2. Routing & third-party libraries: `import { Link, useNavigate } from "react-router-dom";`
3. Icons: `import { Phone, Calendar, Mail, CheckCircle } from "lucide-react";`
4. UI Primitives & Components: `import { Button } from "@/components/ui/button";`
5. Internal utilities & API client: `import { api } from "@/lib/api";`

## Error Handling

**Provider Contract Patterns:**
- External service calls never raise unhandled exceptions across module boundaries.
- Every provider returns an explicit `ProviderResult`:
  ```python
  @dataclass
  class ProviderResult:
      spec: str
      provider: str
      mode: str  # "LIVE" | "MOCK"
      ok: bool
      status: Optional[int] = None
      error: Optional[str] = None
      data: dict[str, Any] = field(default_factory=dict)
  ```
- If an integration fails live, the real status and error are recorded in `db.provider_health`. The application never reports a failed live call as a mock success.

**API Boundary Errors:**
- Inbound invalid requests raise explicit FastAPI `HTTPException`:
  ```python
  if not lead:
      raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
  ```
- Authentication failures fail closed with 401 Unauthorized via constant-time token comparison:
  ```python
  if not admin_token or not secrets.compare_digest(provided_token, admin_token):
      raise HTTPException(status_code=401, detail="Invalid admin token")
  ```

**Frontend Network Handling:**
- Centralized Axios interceptor in `frontend/src/lib/api.js` captures errors, formats server error messages, and automatically prompts for an admin token when encountering HTTP 401 on protected actions.

## Logging & Observability

- Standard library `logging` instances per module:
  ```python
  log = logging.getLogger("server")
  ```
- Append-only audit logs persisted in MongoDB `events` collection for state transitions, scoring, external provider calls, and human approvals:
  ```python
  await db.events.insert_one({
      "lead_id": lead_id,
      "event": "state_transition",
      "from_status": prev_status,
      "to_status": new_status,
      "ts": datetime.now(timezone.utc).isoformat(),
      "correlation_id": correlation_id,
  })
  ```

## Documentation & Docstrings

- Every module begins with a comprehensive module docstring describing:
  1. Primary responsibility and architectural boundaries.
  2. Operating contracts and fallback behaviors.
  3. Associated configuration flags and endpoints.
- Code patterns emphasize self-documenting naming and architectural assertions (e.g. `assert self.entry is not None`).

---

*Conventions analysis: 2026-09-09*
*Update after establishing or altering team conventions*
