# Business Onboarding and Manual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox () syntax for tracking.

**Goal:** Add versioned first-visit onboarding, admin-controlled replay, contextual page tours, and an embedded Chinese operations manual.

**Architecture:** Django owns only version/progress state and staff-only JSON APIs. React owns versioned guide/manual content, rendering, route navigation, and contextual highlights. Public pages never mount the guide controller.

**Tech Stack:** Django 5, Django Admin, React, TypeScript, Zustand, React Router, Tailwind/DaisyUI, Vitest.

---

### Task 1: Versioned guide state and staff APIs

**Files:**
- Modify: 
- Modify: 
- Modify: 
- Modify: 
- Create: 
- Create: 
- Create: 

- [ ] Write failing Django tests for first visit, completion, version upgrade, global disable, forced replay, staff-only access and idempotent completion.
- [ ] Run ; expect failures because models and routes do not exist.
- [ ] Add singleton configuration, per-user progress, admin controls, status/complete/replay APIs and auth payload.
- [ ] Run the same tests; expect all pass.
- [ ] Commit with Chinese message.

### Task 2: OpenDesign prototype and frontend state

**Files:**
- Create: 
- Create: 
- Create: 
- Create: 
- Modify: 
- Modify: 

- [ ] Build one responsive prototype covering the welcome overlay, contextual spotlight and manual layout using existing design tokens.
- [ ] Write failing Vitest cases for guide eligibility, step navigation, completion and manual route mapping.
- [ ] Run ; expect the new tests to fail because guide modules do not exist.
- [ ] Implement typed content/state helpers and API clients.
- [ ] Run frontend tests; expect all pass.
- [ ] Commit with Chinese message.

### Task 3: React onboarding and embedded manual

**Files:**
- Create: 
- Create: 
- Create: 
- Create: 
- Modify: 
- Modify: 
- Modify: 

- [ ] Write failing component/helper tests for close/skip behavior and chapter actions.
- [ ] Run the focused tests and verify expected RED failures.
- [ ] Implement the controller, six-step welcome flow, contextual spotlight,  page and desktop/mobile entries.
- [ ] Add stable  targets to the sales/accounting page without changing business behavior.
- [ ] Run tests, lint and build; expect all pass.
- [ ] Commit with Chinese message.

### Task 4: Review and final verification

**Files:**
- Modify only files required by valid review findings.

- [ ] Request independent Luna backend/security review.
- [ ] Request independent Luna frontend/accessibility review.
- [ ] Fix every Critical or Important finding with a failing regression test first.
- [ ] Run .
- [ ] Run  and .
- [ ] Run , ,  and .
- [ ] Commit final fixes with a Chinese message and merge locally to ; do not push.
