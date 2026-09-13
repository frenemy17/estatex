---
last_mapped_commit: 722da52125826f52cb0781fbfb78ec823fc64055
---

# Technology Stack

**Analysis Date:** 2026-09-09

## Languages

**Primary:**
- **Python 3.14.2** (Python 3.10+ compatible) - Backend API, LangGraph supervisor agent, external provider integrations, autonomous tick worker, and unit tests (`backend/`).
- **JavaScript (ES6+ / JSX)** - Frontend single-page application (SPA), dashboard components, interactive visualizers, analytics, and API client (`frontend/src/`).

**Secondary:**
- **Shell / Bash / Make** - Local development helpers, setup scripts, GSD tools (`gsd-tools.cjs`).
- **Markdown / YAML / JSON** - System documentation (`docs/PRD.md`, `README.md`), deployment descriptors (`render.yaml`, `vercel.json`), and CI workflows (`.github/workflows/tick.yml`).

## Runtime

**Environment:**
- **Backend:** Python virtualenv (`backend/.venv/`), executing under CPython 3.14.2 on macOS / Linux.
- **Frontend:** Node.js v20+ with npm (lockfile v3 present in `frontend/package-lock.json`).

**Package Manager:**
- **Python:** `pip` managing dependencies declared in `backend/requirements.txt`.
- **Node:** `npm` v10+ with lockfile `frontend/package-lock.json`.
- `.npmrc` present in root and frontend defining registry resolution.

## Frameworks

**Core:**
- **FastAPI 0.110.1** (`backend/requirements.txt`) - Async ASGI web framework powering `/api` endpoints, webhooks, rate limiting, and background tasks.
- **Uvicorn 0.25.0** (`backend/requirements.txt`) - High-performance ASGI server for hosting FastAPI.
- **Motor 3.3.1 / PyMongo 4.6.3** (`backend/requirements.txt`) - Asynchronous Python driver for MongoDB persistence.
- **React 19.0.0** (`frontend/package.json`) - Declarative UI library running the client-side SPA.
- **CRA / Craco 5.9.0** (`frontend/craco.config.js`) - Create React App build pipeline customized with Craco for path aliases and PostCSS/Tailwind configuration.
- **Tailwind CSS 3.4.17** (`frontend/tailwind.config.js`) - Utility-first styling system with `@tailwindcss/animate` and Radix UI compatibility.

**Testing:**
- **pytest 9.1.1 (pytest >= 8.0.0)** (`backend/pytest.ini`, `backend/requirements.txt`) - Offline test runner with zero-network fixtures.
- **pytest-xdist 3.8.0** - Parallelized test worker execution across multiple CPU cores.
- **Craco Test / Jest** - Configured test script in `frontend/package.json` (`npm test` via `craco test`).

**Build & Dev:**
- **Craco** (`frontend/craco.config.js`) - Webpack bundler wrapper for the React application.
- **PostCSS 8.5.10 & Autoprefixer 10.4.20** - CSS processing pipeline.

## Key Dependencies

**Backend Critical:**
- `fastapi==0.110.1`: Async REST API routing, query/body validation, exception handling, and `BackgroundTasks`.
- `motor==3.3.1`: Async MongoDB persistence for leads, event logs, scheduled actions, and agent checkpoints.
- `pydantic>=2.6.4`: Schema validation for API payloads, lead models, and provider responses.
- `requests>=2.31.0`: Synchronous HTTP client executed in worker threads via `asyncio.to_thread` for external SaaS API calls.
- `google-generativeai`: Optional fallback LLM integration when Groq is unavailable or Google AI Studio key is provided.
- `python-multipart>=0.0.9`: Form-data parsing for Twilio inbound webhook payloads.
- `python-dotenv>=1.0.1`: Local environment variable loading from `backend/.env`.

**Frontend Critical:**
- `react-router-dom ^7.18.2`: Client-side routing across Landing, Dashboard, Lead Detail, Analytics, Compare, and Capture pages.
- `@tanstack/react-query 5.56.2` & `swr 2.3.8`: Data fetching and client-side cache management.
- `axios 1.18.0`: HTTP client configured in `frontend/src/lib/api.js` with admin token injection and error handling.
- `framer-motion 11.18.0`: Page transitions, Kanban card dragging, and interactive pipeline micro-animations.
- `lucide-react 0.516.0` & `@phosphor-icons/react ^2.1.10`: Unified iconography across the interface.
- `@radix-ui/react-*`: Accessible primitives (Dialog, Dropdown, Tabs, Popover, Tooltip, Switch, Slider).
- `recharts 3.6.0`: Analytics and conversion funnel visualization charts.
- `sonner 2.0.3`: Toast notification system for user actions and system alerts.

## Configuration

**Environment Configuration:**
- `backend/.env` (and template `backend/.env.example`):
  - Database: `MONGO_URL`, `DB_NAME`
  - Auth: `ADMIN_TOKEN`, `CORS_ORIGINS`
  - Demo mode: `DEMO_MODE`, `DEMO_CALL_DELAY_SECONDS`
  - AI Providers: `GROQ_API_KEY`, `GOOGLE_API_KEY`
  - Voice / Booking / CRM / Messaging: `VAPI_API_KEY`, `VAPI_PHONE_NUMBER_ID`, `VOICE_ENABLED`, `CAL_API_KEY`, `CAL_EVENT_TYPE_ID`, `RESEND_API_KEY`, `FROM_EMAIL`, `DEMO_EMAIL`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `SMS_ENABLED`, `HUBSPOT_ACCESS_TOKEN`
  - Webhooks: `GOOGLE_LEADS_WEBHOOK_KEY`, `VAPI_WEBHOOK_SECRET`
- `frontend/.env`:
  - `REACT_APP_API_URL` or `VITE_API_URL` pointing to backend host (defaulting to `http://localhost:8000`).

**Build & Tooling Configuration:**
- `frontend/craco.config.js`: Path aliases mapping `@/` to `frontend/src/`.
- `frontend/tailwind.config.js`: Custom color palette, container configurations, typography, and animation keyframes.
- `backend/pytest.ini`: Test discovery settings, asyncio mode, and warning filters.
- `render.yaml`: Infrastructure specification for Render web service running FastAPI.
- `vercel.json`: Single-page app routing rules and static build outputs for Vercel.

## Platform Requirements

**Development:**
- Python 3.10+ (tested with Python 3.14.2).
- Node.js 18+ / npm 10+.
- MongoDB: Local instance (`mongodb://localhost:27017`) or cloud Atlas cluster. The offline pytest test suite runs entirely without a database using an in-memory test double.

**Production:**
- **Backend:** Hosted on Render as an always-on Python Web Service (`render.yaml`).
- **Frontend:** Hosted on Vercel as a static Single Page Application (`vercel.json`).
- **Database:** MongoDB Atlas M0 free-tier or dedicated cluster.

---

*Stack analysis: 2026-09-09*
*Update after major dependency changes*
