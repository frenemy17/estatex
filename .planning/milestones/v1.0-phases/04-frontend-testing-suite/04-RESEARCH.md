# Phase 4: Frontend Testing Suite — Research & Architecture Analysis

## Overview

The purpose of Phase 4 is to establish a comprehensive automated testing suite for the EstateX React frontend application (`frontend/`), satisfying requirement `UI-01`.
The frontend is built on:
- React 19.0.0 & React DOM 19.0.0
- React Scripts 5.0.1 + CRACO 5.9.0 (with Tailwind CSS 3.4.17)
- Lucide React & Phosphor Icons
- Radix UI & Sonner toast library
- Axios API layer with JWT/Admin Token headers

Currently, `npm --prefix frontend test -- --watchAll=false` runs Jest via CRACO, but 0 test suites exist.

---

## Codebase Analysis & Testing Targets

### 1. Test Runner & Dependencies
- **Jest Environment:** `craco test` provides Jest 27/28 test runner in jsdom environment.
- **Testing Library Packages:**
  - `@testing-library/react` (v16.3+ supports React 19)
  - `@testing-library/jest-dom` (v7.0+ provides DOM matchers like `toBeInTheDocument()`, `toHaveTextContent()`)
  - `@testing-library/user-event` (v14.6+ simulates browser interactions)
  - Pre-flight dry-run confirmed `npm install --save-dev @testing-library/react @testing-library/jest-dom @testing-library/user-event` resolves cleanly with 0 dependency conflicts.

### 2. Client API & Utility Layer (`frontend/src/lib/`)
- **`lib/api.js`**:
  - Token handling: `getAdminToken`, `setAdminToken`, `onAdminTokenChange`.
  - Status metadata: `STATUSES`, `STATUS_META`.
  - Lead scoring: `scoreBand(score)` (Elite >= 85, Qualified >= 70, Nurture >= 40, Cold < 40).
  - Provider health helpers: `providerTone(p)`, `providerHint(p)`.
  - Event filtering: `isErrorEvent(e)`.
  - Axios interceptor: Request token injection (`X-Admin-Token`).
- **`lib/utils.js`**:
  - `cn(...inputs)` class name merging utility.

### 3. Core Component Layer (`frontend/src/components/`)
- **`ProviderStatus.jsx`**:
  - Fetches `/providers` status using `usePoll` or direct API call.
  - Renders provider badges (`Groq`, `Cal.com`, `Resend`, `Twilio Voice`, `Twilio SMS`, `HubSpot`).
  - Verifies tooltip / tone colors (`bg-emerald-400`, `bg-yellow-500`, `bg-red-500`).
- **`AdminTokenButton.jsx`**:
  - Renders admin status button (`data-testid="btn-admin-token"`).
  - Opens modal dialog to view/update `estatex_admin_token` in `localStorage`.
  - Emits `estatex:admin-token` event on save and clear.
- **`Layout.jsx`**:
  - Sidebar navigation links (`Dashboard`, `Capture`, `Analytics`, `Compare`).
  - Seed leads action trigger (`data-testid="btn-seed-leads"`).

### 4. Kanban Pipeline & Page Layer (`frontend/src/pages/`)
- **`Dashboard.jsx` (Agency Command Center & Kanban Board)**:
  - Top-level KPI counts (Total Hot, Booked, In-Flight, Pending Approvals, Conversion Rate).
  - Search filter: filters leads by name, phone, email, and area.
  - Category tabs: `all`, `hot`, `inflight`, `booked`, `approval`.
  - Kanban Board (`data-testid="kanban-board"`): Renders 7 status columns (`NEW`, `CALLING`, `IN_CONVERSATION`, `QUALIFIED`, `HOT`, `NURTURE`, `BOOKED`).
  - Lead cards (`data-testid="lead-card-{id}"`): displays lead name, score badge, qualification area, phone, tags, and status.
  - Seeding trigger (`handleSeed`).
- **`LeadDetail.jsx`**:
  - Displays lead overview, contact details, qualification summary.
  - Escalation approval banner with `btn-approve-escalation` and `btn-reject-escalation`.
  - Appointment slots booking and cancellation.
  - Action buttons: Run Supervisor, Rerun Pipeline, Opt-Out.
  - AI Event Trace timeline and transcript viewer.
- **`Capture.jsx`**:
  - Lead intake form with input validation: `input-name`, `input-phone`, `input-email`.
  - Submits lead to `POST /lead` via `api.post`.

---

## Validation Architecture (Dimension 8)

### Test Configuration (`setupTests.js`)
- Add `frontend/src/setupTests.js` importing `@testing-library/jest-dom`.
- Configure mocks for browser APIs:
  - `window.matchMedia`
  - `IntersectionObserver` / `ResizeObserver`
  - Mock `api` (Axios instance) for deterministic network isolation.

### Automated Test Command
- Single verification command:
  ```bash
  npm --prefix frontend test -- --watchAll=false
  ```
- Fast execution (< 10 seconds), 0 flakes, running cleanly in CI/headless environments.

---

## Plan Decomposition

### Wave 1: Test Infrastructure & Unit/Client Testing (`04-01-PLAN.md`)
- Install `@testing-library/react`, `@testing-library/jest-dom`, and `@testing-library/user-event`.
- Create `frontend/src/setupTests.js` with required DOM polyfills and Jest matchers.
- Author unit tests for `src/lib/api.test.js` and `src/lib/utils.test.js`.
- Author component tests for `src/components/AdminTokenButton.test.jsx` and `src/components/ProviderStatus.test.jsx`.

### Wave 2: Kanban Board & Application Page Integration Testing (`04-02-PLAN.md`)
- Author component and integration tests for `src/pages/Dashboard.test.jsx`:
  - Test Kanban column rendering across all 7 statuses (`kanban-column-*`).
  - Test KPI card calculations and display.
  - Test lead card score badge colors and details.
  - Test search input filtering by name/phone/area.
  - Test category tab filtering (`hot`, `inflight`, `booked`, `approval`).
  - Test seed button trigger and toast feedback.
- Author integration tests for `src/pages/Capture.test.jsx` and `src/pages/LeadDetail.test.jsx`:
  - Lead capture form submission and error handling.
  - Lead escalation approval/rejection button interactions.
- Run complete test suite and verify 100% green execution.
