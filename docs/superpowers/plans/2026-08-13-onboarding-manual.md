# Business Onboarding and Manual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add versioned first-visit onboarding, admin-controlled replay, contextual page tours, and an embedded Chinese operations manual.

**Architecture:** Django owns only version/progress state and staff-only JSON APIs. React owns versioned guide/manual content, rendering, route navigation, and contextual highlights. Public pages never mount the guide controller.

**Tech Stack:** Django 5, Django Admin, React, TypeScript, Zustand, React Router, Tailwind/DaisyUI, Vitest.

---

### Task 1: Versioned guide state and staff APIs

**Files:**
- Modify: cigars/models.py
- Modify: cigars/admin.py
- Modify: cigars/auth_views.py
- Modify: cigardomtabaka_backend/urls.py
- Create: cigars/guide_views.py
- Create: cigars/migrations/0033_guideconfiguration_userguideprogress.py
- Create: cigars/tests/test_guides.py

- [ ] Write failing Django tests for first visit, completion, version upgrade, global disable, forced replay, staff-only access and idempotent completion.
- [ ] Run .venv/bin/python manage.py test cigars.tests.test_guides -v 1; expect failures because models and routes do not exist.
- [ ] Add singleton configuration, per-user progress, admin controls, status/complete/replay APIs and auth payload.
- [ ] Run the same tests; expect all pass.
- [ ] Commit with Chinese message.

### Task 2: OpenDesign prototype and frontend state

**Files:**
- Create: .opendesign/onboarding-manual.html
- Create: frontend/src/features/guides/guideContent.ts
- Create: frontend/src/features/guides/guideState.ts
- Create: frontend/src/features/guides/guideState.test.ts
- Modify: frontend/src/api.ts
- Modify: frontend/src/store/authStore.ts

- [ ] Build one responsive prototype covering the welcome overlay, contextual spotlight and manual layout using existing design tokens.
- [ ] Write failing Vitest cases for guide eligibility, step navigation, completion and manual route mapping.
- [ ] Run npm test -- --run; expect the new tests to fail because guide modules do not exist.
- [ ] Implement typed content/state helpers and API clients.
- [ ] Run frontend tests; expect all pass.
- [ ] Commit with Chinese message.

### Task 3: React onboarding and embedded manual

**Files:**
- Create: frontend/src/features/guides/GuideController.tsx
- Create: frontend/src/features/guides/WelcomeGuide.tsx
- Create: frontend/src/features/guides/ContextTour.tsx
- Create: frontend/src/pages/HelpPage.tsx
- Modify: frontend/src/App.tsx
- Modify: frontend/src/components/layout/AppLayout.tsx
- Modify: frontend/src/pages/SalesAccountingPage.tsx

- [ ] Write failing component/helper tests for close/skip behavior and chapter actions.
- [ ] Run the focused tests and verify expected RED failures.
- [ ] Implement the controller, six-step welcome flow, contextual spotlight, /help page and desktop/mobile entries.
- [ ] Add stable data-guide targets to the sales/accounting page without changing business behavior.
- [ ] Run tests, lint and build; expect all pass.
- [ ] Commit with Chinese message.

### Task 4: Review and final verification

**Files:**
- Modify only files required by valid review findings.

- [ ] Request independent Luna backend/security review.
- [ ] Request independent Luna frontend/accessibility review.
- [ ] Fix every Critical or Important finding with a failing regression test first.
- [ ] Run .venv/bin/python manage.py test cigars.tests.test_guides -v 1.
- [ ] Run .venv/bin/python manage.py makemigrations --check --dry-run and .venv/bin/python manage.py check.
- [ ] Run npm test -- --run, npm run lint, npm run build and git diff --check.
- [ ] Commit final fixes with a Chinese message and merge locally to main; do not push.
