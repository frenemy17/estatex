---
last_mapped_commit: 722da52125826f52cb0781fbfb78ec823fc64055
---

# Codebase Structure

**Analysis Date:** 2026-09-09

## Directory Layout

```
estatex-main/
├── backend/                  # FastAPI async application & agent engine
│   ├── agents/               # LangGraph-style state graph & agent nodes
│   │   ├── __init__.py       # Package init
│   │   ├── graph.py          # StateGraph, CompiledGraph, MongoCheckpointer
│   │   └── supervisor.py     # Supervisor node, sub-agents, human interrupt
│   ├── tests/                # Offline unit test suite (no database required)
│   │   ├── __init__.py       # Package init
│   │   ├── conftest.py       # In-memory Motor MongoDB test double
│   │   ├── test_providers.py # Provider contract & mock/live verification
│   │   ├── test_state_machine.py # Transition invariants & scoring guards
│   │   ├── test_tick.py      # Autonomy worker, action claims, rate limits
│   │   └── test_v2_api.py    # V2 supervisor endpoints & interrupt resume
│   ├── .env.example          # Comprehensive configuration template
│   ├── providers.py          # I/O integrations (Groq, Vapi, Cal, Resend, etc.)
│   ├── pytest.ini            # Test discovery and warning configurations
│   ├── requirements.txt      # Pinned Python package dependencies
│   └── server.py             # Main FastAPI app, routes, state machine, tick
├── docs/                     # Product requirements & design guidelines
│   ├── PRD.md                # System specification, roadmap, and backlog
│   └── design_guidelines.json # UI/UX styling principles and specifications
├── frontend/                 # React 19 single-page application
│   ├── public/               # Static HTML shell and public assets
│   ├── src/                  # Application source code
│   │   ├── components/       # Shared UI components & status badges
│   │   │   ├── ui/           # Radix / shadcn/ui primitive library (48 components)
│   │   │   ├── AdminTokenButton.jsx # Admin authentication modal & state
│   │   │   ├── Layout.jsx    # Persistent header, navigation bar, and footer
│   │   │   └── ProviderStatus.jsx   # Real-time health badge indicator
│   │   ├── hooks/            # Custom React hooks
│   │   ├── lib/              # Client utilities and networking
│   │   │   ├── api.js        # Axios instance configured with auth headers
│   │   │   ├── usePoll.js    # Adaptive polling hook for live dashboard updates
│   │   │   └── utils.js      # ClassName merge utility (`clsx` + `twMerge`)
│   │   ├── pages/            # Page-level route views
│   │   │   ├── Analytics.jsx # Conversion funnel and velocity charts
│   │   │   ├── Capture.jsx   # Public lead acquisition form
│   │   │   ├── Compare.jsx   # V1 vs V2 architectural comparison view
│   │   │   ├── Dashboard.jsx # Real-time Kanban pipeline board
│   │   │   ├── Landing.jsx   # Conversion-focused marketing landing page
│   │   │   └── LeadDetail.jsx # Deep-dive lead inspection, audio, and actions
│   │   ├── App.css           # Global layout adjustments
│   │   ├── App.js            # Client router configuration & route tree
│   │   ├── index.css         # Tailwind base styles and CSS variables
│   │   └── index.js          # React DOM root initialization
│   ├── craco.config.js       # Craco configuration for path aliases
│   ├── package.json          # Node dependencies and scripts
│   └── tailwind.config.js    # Tailwind theme, typography, and animation tokens
├── .github/                  # CI/CD workflows
│   └── workflows/
│       └── tick.yml          # 10-minute scheduled cron for /api/tick
├── render.yaml               # Render Web Service specification
├── vercel.json               # Vercel SPA routing and build configuration
└── README.md                 # System overview and quickstart guide
```

## Directory Purposes

**`backend/`:**
- **Purpose:** Houses all server-side application logic, REST endpoints, database access, background queues, and AI integrations.
- **Key files:** `server.py`, `providers.py`, `requirements.txt`.
- **Subdirectories:**
  - `agents/`: Micro-graph orchestration framework and agent logic.
  - `tests/`: 69 offline unit and integration tests executing in under 2 seconds.

**`backend/agents/`:**
- **Purpose:** Encapsulates the V2 multi-agent supervisor system.
- **Key files:**
  - `graph.py`: Implements `StateGraph`, `CompiledGraph`, and `MongoCheckpointer` without external heavy dependencies.
  - `supervisor.py`: Supervisor prompt, heuristic safety net, sub-agents (`enrichment_agent`, `followup_agent`), and human approval gates.

**`frontend/src/pages/`:**
- **Purpose:** Primary view controllers corresponding to application routes.
- **Key files:**
  - `Dashboard.jsx`: Live Kanban tracking column changes and lead velocity.
  - `LeadDetail.jsx`: Comprehensive view of an individual lead, displaying qualification dimensions, event log timeline, call recording audio player, and admin actions.
  - `Landing.jsx`: High-polish marketing page communicating platform capabilities.

**`frontend/src/components/ui/`:**
- **Purpose:** Reusable, accessible UI components based on Radix UI and Tailwind CSS (buttons, dialogs, badges, cards, tabs, tooltips, separators).

**`frontend/src/lib/`:**
- **Purpose:** Frontend network clients, shared hooks, and utility functions.
- **Key files:** `api.js` (handles API base URL resolution and admin token header injection), `usePoll.js` (handles interval polling with visibility pause).

## Key File Locations

**Entry Points:**
- `backend/server.py`: FastAPI server initialization (`app = FastAPI(...)`) and ASGI entry point.
- `frontend/src/index.js`: Browser entry point mounting React root into `public/index.html`.
- `frontend/src/App.js`: Root React component configuring BrowserRouter and route definitions.

**Configuration:**
- `backend/.env`: Local environment variables for database URLs, API keys, and operational modes.
- `backend/pytest.ini`: Pytest test suite configuration.
- `frontend/craco.config.js`: Webpack path alias setup (`@/` -> `src/`).
- `frontend/tailwind.config.js`: Theme customization, custom color ramps, and animations.
- `render.yaml` & `vercel.json`: Cloud deployment specifications.

**Core Logic:**
- `backend/server.py`: Ingestion endpoints, state machine transitions (`ALLOWED_TRANSITIONS`), rubric calculator (`compute_score`), qualification router (`qualify_and_route`), and tick worker (`/api/tick`).
- `backend/providers.py`: Pure I/O integration contracts (`ProviderResult`, `is_live`, provider functions).
- `backend/agents/graph.py`: State graph traversal engine.

**Testing:**
- `backend/tests/conftest.py`: In-memory Motor database stand-in simulating queries, projections, updates, and sorting.
- `backend/tests/test_*.py`: Automated test cases covering providers, state transitions, tick worker, and V2 agent APIs.

## Naming Conventions

**Backend (Python):**
- **Files:** `snake_case.py` (e.g. `server.py`, `providers.py`, `test_state_machine.py`).
- **Classes:** `PascalCase` (e.g. `StateGraph`, `MongoCheckpointer`, `ProviderResult`, `LeadCaptureIn`).
- **Functions & Methods:** `snake_case` (e.g. `qualify_and_route`, `require_admin`, `compute_score`).
- **Constants:** `UPPER_SNAKE_CASE` (e.g. `ALLOWED_TRANSITIONS`, `PROVIDER_SPECS`, `CALL_TIMEOUT_MINUTES`).

**Frontend (JavaScript / React):**
- **Components & Pages:** `PascalCase.jsx` (e.g. `Dashboard.jsx`, `LeadDetail.jsx`, `ProviderStatus.jsx`).
- **Utilities & Hooks:** `camelCase.js` (e.g. `api.js`, `usePoll.js`, `utils.js`).
- **CSS Classes:** Utility classes following Tailwind CSS conventions (e.g. `flex items-center justify-between p-4 rounded-xl border border-slate-800`).

## Where to Add New Code

**Adding a New External Integration:**
- Add capability and environment specifications to `PROVIDER_SPECS` in `backend/providers.py`.
- Implement provider I/O function in `backend/providers.py` returning a `ProviderResult`.
- Update `backend/.env.example` with required keys.
- Add unit tests in `backend/tests/test_providers.py`.

**Adding a New Agent Node or Workflow:**
- Define node function in `backend/agents/supervisor.py`.
- Wire into the graph in `create_supervisor_graph()` in `backend/agents/supervisor.py`.
- Add test coverage in `backend/tests/test_v2_api.py`.

**Adding a New API Route:**
- Define Pydantic request/response schemas in `backend/server.py`.
- Register route on `app` with appropriate security dependency (`Depends(require_admin)` if protected).
- Add corresponding API method in `frontend/src/lib/api.js`.

**Adding a New Frontend View:**
- Create page component in `frontend/src/pages/NewPage.jsx`.
- Register route in `frontend/src/App.js`.
- Add navigation link in `frontend/src/components/Layout.jsx`.

---

*Structure analysis: 2026-09-09*
*Update after directory reorganizations or file movements*
