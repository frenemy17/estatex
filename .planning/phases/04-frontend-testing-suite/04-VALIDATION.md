---
phase: "04"
slug: "frontend-testing-suite"
status: draft
nyquist_compliant: true
wave_0_complete: false
created: "2026-09-10"
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Jest 27+ (via CRACO / React Scripts) + React Testing Library 16.3 + jest-dom |
| **Config file** | `frontend/craco.config.js` and `frontend/src/setupTests.js` |
| **Quick run command** | `npm --prefix frontend test -- --watchAll=false src/lib/` |
| **Full suite command** | `npm --prefix frontend test -- --watchAll=false` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `npm --prefix frontend test -- --watchAll=false`
- **After every plan wave:** Run `npm --prefix frontend test -- --watchAll=false`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | UI-01 | — | N/A | setup | `npm --prefix frontend test -- --watchAll=false` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | UI-01 | — | Admin token headers protected | unit | `npm --prefix frontend test -- --watchAll=false src/lib/` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | UI-01 | — | Admin token storage and event dispatch | component | `npm --prefix frontend test -- --watchAll=false src/components/` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 2 | UI-01 | — | Kanban board status column isolation | component | `npm --prefix frontend test -- --watchAll=false src/pages/Dashboard.test.jsx` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 2 | UI-01 | — | Lead actions and escalation triggers | integration | `npm --prefix frontend test -- --watchAll=false src/pages/` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Install `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`
- [ ] Create `frontend/src/setupTests.js` with DOM polyfills (matchMedia, ResizeObserver)
- [ ] Establish mock helper for `api` (Axios instance)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| None | UI-01 | All phase behaviors have automated verification | `npm --prefix frontend test -- --watchAll=false` |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-10
