# PromptVault Working Prototype Plan

## Goal

Deliver a working end-to-end PromptVault prototype in which a user can register, manage projects and prompt versions, test a prompt, deploy it through an approval workflow, fetch the active prompt through the Serve API, roll back a deployment, and view costs and audit history. A Super Admin must be able to review production deployments and manage the prototype's governance data.

This plan is based on the current repository and the v1 scope in `requirements-matrix.md`, `route-map.md`, `api-contracts.md`, and `demo-storyboard.md`.

## Team and ownership

| Developer | Primary ownership | Secondary ownership |
|---|---|---|
| **Ananya** | React frontend, UX states, client-side validation, API integration, frontend tests | Demo flow and user-facing documentation |
| **Jobin** | FastAPI backend, PostgreSQL schema, security, business rules, backend tests | Local infrastructure, seed data, and technical documentation |

The work is balanced at **32 task packages and approximately 31 developer-days each**. Estimates are planning aids, not deadlines. Each phase gives both developers the same estimated workload so neither side becomes a long-running dependency for the other.

## Current baseline

### Already present

- A Vite/React application with visual mockups for many user and admin screens.
- Reusable UI primitives, layout components, mock data, and an initial authentication context.
- A FastAPI package structure and a working `/health` endpoint.
- Docker Compose configuration for PostgreSQL and the API container.
- Written v1 route, API, authorization, requirement, risk, and demo outlines.

### Still required for a working prototype

- The frontend currently uses hard-coded data and custom path handling; most actions do not call the API.
- Several documented routes are missing or are not wired into the application router.
- API routers, schemas, repositories, services, security helpers, and providers are empty placeholders.
- Database migrations, seeds, maintenance queries, and showcase queries are empty placeholders.
- Backend, database, security, concurrency, performance, and end-to-end tests are empty placeholders.
- The web application is not yet included in the local Docker stack.

## Scope rules

### Required for the prototype

- Email/password authentication with `User` and `Super Admin` roles.
- Projects, project members, prompts, immutable versions, diff, and lineage.
- Deterministic mock-provider runs with token, latency, status, and cost records.
- Development, staging, and production deployments; production requires admin approval.
- Project-scoped runtime tokens and an authenticated Serve API.
- Auditable rollback, budgets, personal/admin analytics, users, pricing, and audit views.
- Authorization, secret handling, predictable errors, seed data, tests, and a repeatable local demo.

### Explicitly deferred

- A/B testing, semantic search, LLM-as-judge, SSO, prompt branch UI, and full RLS multi-tenancy.
- Production-grade email delivery and password recovery. The prototype may show the UX, but it must not imply that email delivery works unless it is implemented.
- Pixel-perfect polishing beyond responsive, accessible, demo-ready screens.

## Shared definition of done

A task is complete only when:

- The implementation works with real API/database data; no demo-critical action is hard-coded.
- Loading, empty, success, validation, authorization, conflict, and server-error states are handled where relevant.
- Authorization is enforced by the backend, not only by hidden frontend controls.
- New behavior has automated tests at the appropriate layer.
- API or data-contract changes are reflected in the relevant documentation.
- No plaintext password, provider key, runtime token, or secret is logged or returned after its one-time display.
- The change passes format/lint, type checks, tests, and a manual happy-path check.

---

## Phase 0 — Contract freeze and development foundation

**Outcome:** Both developers can run the same stack and build against stable contracts.

**Workload:** Ananya 2 days · Jobin 2 days

### Ananya — frontend foundation

- [ ] **A0.1 — Break the monolithic UI into a maintainable route structure (0.5 day).** Move page-level views out of `App.tsx`, adopt `react-router-dom`, define public/authenticated/admin route groups, and wire `/403` and `/404` fallbacks.
- [ ] **A0.2 — Establish the web data layer (0.5 day).** Add a typed API client using `VITE_API_BASE_URL`, standard authorization headers, JSON parsing, shared error-envelope handling, and request cancellation.
- [ ] **A0.3 — Establish frontend quality commands (0.5 day).** Add lint, unit/component test, and coverage scripts; configure the test environment; keep `build` and `typecheck` passing.
- [ ] **A0.4 — Convert the documented API contract into frontend types (0.5 day).** Define shared TypeScript request/response, pagination, role, status, money, and error types; record any contract questions before Phase 1.

### Jobin — backend and database foundation

- [ ] **J0.1 — Complete application configuration and lifecycle (0.5 day).** Implement environment-based settings, database pool startup/shutdown, CORS for the web origin, request IDs, structured logging, and health/readiness checks.
- [ ] **J0.2 — Make migrations executable (0.5 day).** Implement the migration runner and migration tracking table, guarantee ordered/idempotent application, and expose documented migrate/seed/reset commands.
- [ ] **J0.3 — Establish backend quality commands (0.5 day).** Configure pytest, async test database fixtures, formatting/linting, type checks, and coverage; ensure the empty baseline suite runs reliably.
- [ ] **J0.4 — Freeze API conventions with Ananya (0.5 day).** Finalize error codes, pagination, date/money serialization, status enums, CORS behavior, and OpenAPI examples in `api-contracts.md`.

### Phase 0 exit criteria

- One documented command starts PostgreSQL and the API; one documented command starts the web app.
- The web app uses a real router and can call `/health` through the shared API client.
- CI-equivalent local commands for both applications are known and passing.
- Both developers agree that contract changes after this phase require updating types, docs, and tests together.

---

## Phase 1 — Authentication, authorization, and application shell

**Outcome:** Real users can register and sign in, and role-protected navigation works end to end.

**Workload:** Ananya 4 days · Jobin 4 days

### Ananya — authentication experience

- [ ] **A1.1 — Connect registration and login (1 day).** Build controlled forms, client validation, submit/loading states, server field errors, password visibility, and redirect to the originally requested route after login.
- [ ] **A1.2 — Implement session lifecycle (1 day).** Connect `AuthProvider` to `/auth/me`, persist the agreed token mechanism, restore the session on refresh, handle expiration/401 globally, and implement sign-out.
- [ ] **A1.3 — Implement route and navigation guards (1 day).** Protect authenticated and Super Admin routes, hide unauthorized navigation, send forbidden users to `/403`, and remove the hard-coded Alex Morgan identity.
- [ ] **A1.4 — Finish responsive shell and auth tests (1 day).** Validate desktop/mobile navigation, keyboard focus, labels, and screen states; add component tests for registration, login, logout, refresh, redirects, and role guards.

### Jobin — identity and authorization

- [ ] **J1.1 — Create identity schema and seed identities (1 day).** Add user/role tables and constraints, active status, timestamps, normalized unique email, and deterministic demo User/Super Admin accounts.
- [ ] **J1.2 — Implement secure credential and token helpers (1 day).** Add Argon2 password hashing, JWT issue/verify/expiry, safe authentication errors, and secret-safe configuration.
- [ ] **J1.3 — Implement authentication endpoints (1 day).** Build register, login, and current-user schemas/services/routes; reject role selection during registration and inactive-user access.
- [ ] **J1.4 — Implement reusable authorization dependencies and tests (1 day).** Add authenticated-user, active-user, project-member, project-owner, and Super Admin dependencies; test 401/403 behavior and role escalation attempts.

### Phase 1 exit criteria

- A new user can register, refresh the browser, remain signed in, and sign out.
- A normal user cannot see or directly open admin pages.
- A Super Admin can open the admin shell.
- Invalid, expired, or missing authentication produces the standard error envelope and a safe frontend recovery path.

---

## Phase 2 — Projects, members, prompts, and immutable versions

**Outcome:** A user can build and inspect a versioned prompt library with real database persistence.

**Workload:** Ananya 6 days · Jobin 6 days

### Ananya — prompt-library workflows

- [ ] **A2.1 — Implement project list/create/detail/settings (1.5 days).** Replace mock project cards with paginated API data; implement search, empty/error/loading states, create/edit forms, stable-key validation, and owner-only controls.
- [ ] **A2.2 — Implement member management (1 day).** Add member list, add/remove dialogs, duplicate/not-found handling, owner restrictions, confirmation UX, and post-mutation refresh.
- [ ] **A2.3 — Implement prompt creation and detail editing flow (1.5 days).** Add project selection, prompt metadata, template editor, `{{variable}}` detection, variables/model configuration, commit message, and first-version creation.
- [ ] **A2.4 — Implement version history, detail, diff, and lineage (2 days).** Wire all version routes, render immutable snapshots, compare selected versions side by side, visualize ancestors, and test that saving creates a new version rather than editing an old one.

### Jobin — project and versioning domain

- [x] **J2.1 — Create project/member schema and endpoints (1.5 days).** Add ownership/membership constraints and indexes; implement scoped project CRUD plus list/add/remove-member operations and duplicate-member conflicts.
- [x] **J2.2 — Create prompt/version schema (1.5 days).** Store stable project-scoped prompt keys, immutable version snapshots, variables/model config, author, commit message, parent version, and per-prompt version number.
- [x] **J2.3 — Implement prompt and atomic version endpoints (1.5 days).** Build scoped prompt create/read/list and version create/list/read operations; allocate version numbers safely under concurrent saves and prohibit update/delete of snapshots.
- [x] **J2.4 — Implement diff/lineage queries and tests (1.5 days).** Return deterministic template/config diffs and ordered recursive ancestry; test membership scoping, immutability, uniqueness, concurrency, and missing parents.

### Phase 2 exit criteria

- An owner can create a project, add a member, and create a prompt with its first version.
- Saving twice creates v2 and v3; v1 and v2 remain unchanged.
- Version history, detail, diff, and lineage are all backed by the database.
- Non-members cannot discover or access the project through list or direct-ID endpoints.

---

## Phase 3 — Playground, run ledger, budgets, and cost analytics

**Outcome:** Prompt versions can be executed deterministically, with auditable usage and enforced budgets.

**Workload:** Ananya 4 days · Jobin 4 days

### Ananya — execution and cost screens

- [ ] **A3.1 — Connect the playground (1 day).** Load permitted prompts/versions, generate inputs from declared variables, validate missing values, submit a run, and render output/status/token/latency/cost data.
- [ ] **A3.2 — Implement run history and detail (1 day).** Replace the mock table with paginated/filterable data, add a run-detail view, and clearly distinguish completed, provider-failed, and budget-blocked runs.
- [ ] **A3.3 — Implement personal cost dashboard (1 day).** Connect spend totals, budget utilization, remaining amount, run count, trend data, and accessible chart/table fallbacks with correct money formatting.
- [ ] **A3.4 — Test run UX and budget boundaries (1 day).** Cover dynamic variables, submission locking, retry-safe errors, empty history, filtering, failed provider calls, exact-limit allowance, and over-limit messaging.

### Jobin — execution ledger and budget rules

- [x] **J3.1 — Implement provider abstraction and deterministic mock (1 day).** Complete the base/factory/mock provider flow with stable test output, token accounting, latency, timeout/error translation, and optional Gemini adapter behind configuration.
- [x] **J3.2 — Implement run ledger and execution transaction (1 day).** Render variables safely, execute the provider, store status/output/tokens/latency/model/pricing/cost/user/project, and never store provider secrets.
- [x] **J3.3 — Implement effective-dated pricing and atomic budgets (1 day).** Add user/project monthly limits, decimal cost calculation, applicable price lookup, and database-boundary enforcement that remains correct under concurrent runs.
- [x] **J3.4 — Implement run and personal-dashboard APIs with tests (1 day).** Add scoped filters/pagination and aggregate queries; test calculation precision, blocked runs, provider failures, authorization, and concurrent budget consumption.

### Phase 3 exit criteria

- A member can run v3 with the mock provider and see a persisted ledger record.
- The displayed tokens, latency, price, and cost match the stored record.
- Lowering a budget blocks an over-limit run atomically and returns `budget_exceeded`.
- Users see only permitted runs and aggregates.

---

## Phase 4 — Deployment, approval, Serve API, and rollback

**Outcome:** The complete promotion lifecycle works, including production governance and runtime consumption.

**Workload:** Ananya 5 days · Jobin 5 days

### Ananya — deployment lifecycle UX

- [ ] **A4.1 — Implement deployment creation and history (1 day).** Select a permitted immutable version and environment, explain production approval, validate notes, submit, cancel owned pending requests, and show environment/status filters.
- [ ] **A4.2 — Implement deployment detail (1 day).** Display requester, version, environment, timestamps, notes, status timeline, active version, cancellation/rejection reason, and links to prompt/version evidence.
- [ ] **A4.3 — Implement admin approval queue and review (1.5 days).** Build pending list/detail, show diff and recent run evidence, collect rejection reason, require confirmation, and handle already-reviewed 409 conflicts without stale UI.
- [ ] **A4.4 — Implement rollback and token-management screens (1.5 days).** Add admin rollback selection/confirmation, active-version feedback, runtime-token issue/list/revoke, one-time plaintext display/copy warning, and tests for both workflows.

### Jobin — deployment control plane

- [x] **J4.1 — Implement deployment schema and user endpoints (1 day).** Model immutable deployment events and active environment state; activate dev/staging immediately, create pending production requests, and allow only valid pending cancellations.
- [x] **J4.2 — Implement atomic admin review (1 day).** Add pending/detail, approve, and reject operations with evidence payloads; enforce Super Admin access, rejection reasons, state transitions, and one-winner concurrent review behavior.
- [x] **J4.3 — Implement runtime token lifecycle and Serve API (1.5 days).** Generate project-scoped tokens, show plaintext once, store only a hash, list safe metadata, revoke tokens, authenticate Serve requests, and return the active prompt for key/environment.
- [x] **J4.4 — Implement rollback and lifecycle tests (1.5 days).** Create rollback as a new auditable deployment to an earlier version; test no-active-deployment, revoked/wrong-project token, approval race, cancel/review conflicts, fetch-before/after rollback, and secret redaction.

### Phase 4 exit criteria

- Staging becomes active immediately; production remains pending until approved.
- Two competing reviews cannot both succeed; the loser receives a 409 conflict.
- A project-scoped runtime token fetches the active production prompt and cannot access another project.
- Rollback creates a new event, changes the served version, and preserves deployment history.

---

## Phase 5 — Administration, governance, and operational views

**Outcome:** The Super Admin can operate and inspect all prototype controls required by the v1 demo.

**Workload:** Ananya 4 days · Jobin 4 days

### Ananya — admin console

- [ ] **A5.1 — Connect organization overview and admin runs (1 day).** Replace hard-coded stats with organization totals, spend-by-model, pending approvals, health, and a filterable organization-wide run explorer.
- [ ] **A5.2 — Implement user and role administration (1 day).** Connect user search/filter, role changes, activate/deactivate controls, confirmations, self-lockout prevention messaging, and mutation error states.
- [ ] **A5.3 — Implement provider-key, budget, and pricing administration (1 day).** Build safe create/list/deactivate provider-key flows, user/project budget forms, pricing history/add form, validation, and never redisplay secret key values.
- [ ] **A5.4 — Implement audit and maintenance views (1 day).** Add filterable read-only audit history, health/readiness details, partition status, materialized-view refresh action/status, admin access tests, and responsive table behavior.

### Jobin — governance services

- [ ] **J5.1 — Implement users and organization analytics APIs (1 day).** Add paginated user management, safe role/status transitions, organization aggregates, spend-by-model, and organization run filters.
- [ ] **J5.2 — Implement provider keys, budgets, and pricing APIs (1 day).** Encrypt provider keys at rest, return metadata only, support deactivation, validate budget targets/periods, and preserve effective-dated price history.
- [ ] **J5.3 — Implement audit trail and admin query APIs (1 day).** Record actor/action/resource/before-after/request metadata for security-sensitive mutations and expose secure, filterable, read-only audit results.
- [ ] **J5.4 — Implement maintenance operations and governance tests (1 day).** Add health/partition/view-refresh endpoints and scripts; test Super Admin enforcement, encryption/redaction, self-demotion/deactivation safeguards, audit coverage, and aggregation accuracy.

### Phase 5 exit criteria

- Every documented admin route is functional or explicitly marked deferred before the demo.
- Provider credentials and runtime tokens are never returned from list/read endpoints.
- Critical changes appear in the audit trail with the correct actor and resource.
- Admin aggregates reconcile with seeded runs and costs.

---

## Phase 6 — End-to-end integration, security, and stabilization

**Outcome:** The prototype survives the full demo and important failure cases from a clean environment.

**Workload:** Ananya 4 days · Jobin 4 days

### Ananya — frontend stabilization

- [ ] **A6.1 — Remove demo-critical hard-coded data (1 day).** Audit every route/action, replace remaining mock responses with APIs, keep mocks only for isolated tests/development, and clearly label any accepted non-critical placeholder.
- [ ] **A6.2 — Complete cross-cutting UX states (1 day).** Standardize toast/error behavior, loading skeletons, empty states, confirmations, pagination, date/timezone and money formatting, stale-query invalidation, and network recovery.
- [ ] **A6.3 — Perform accessibility and responsive pass (1 day).** Verify keyboard navigation, focus restoration for dialogs, accessible names/errors/status, contrast, reduced-motion behavior, and mobile/tablet layouts for all demo routes.
- [ ] **A6.4 — Build frontend integration/E2E coverage (1 day).** Automate the normal-user workflow, production approval, Serve-token management UI, rollback confirmation, budget-blocked state, and forbidden-route recovery.

### Jobin — backend stabilization

- [ ] **J6.1 — Complete database constraints, indexes, and transaction review (1 day).** Enforce referential integrity and valid states, add query-driven indexes, verify isolation/locking for version, approval, budget, and rollback races, and document ownership rules.
- [ ] **J6.2 — Complete security hardening pass (1 day).** Validate inputs, restrict CORS, redact logs/errors, cap pagination/request sizes, prevent identifier-based data leaks, enforce least-privilege DB roles where practical, and document prototype limitations.
- [ ] **J6.3 — Complete automated backend/database suites (1 day).** Fill the existing database, security, concurrency, E2E, and performance test files; make fixtures isolated and repeatable from a clean database.
- [ ] **J6.4 — Validate performance and operational recovery (1 day).** Seed a representative dataset, inspect key query plans, add missing indexes, verify partition/view maintenance scripts, test restart behavior, and document backup/reset expectations for the prototype.

### Phase 6 exit criteria

- All 12 storyboard steps pass twice from clean seed data without manual database edits.
- One forbidden user action and one repeated/concurrent approval conflict are demonstrated correctly.
- No high-severity authorization, secret exposure, data-loss, or broken-demo defect remains.
- Frontend build/typecheck/lint/tests and backend lint/typecheck/tests all pass.

---

## Phase 7 — Packaging, documentation, and demo readiness

**Outcome:** A reviewer can start and evaluate the prototype without developer intervention.

**Workload:** Ananya 2 days · Jobin 2 days

### Ananya — user-facing delivery

- [ ] **A7.1 — Produce the demo runbook and evidence (0.5 day).** Turn the storyboard into exact clicks, accounts, expected results, screenshots, fallback notes, and approximate timing.
- [ ] **A7.2 — Complete frontend/readme documentation (0.5 day).** Document web environment variables, commands, route behavior, test commands, browser support, and known UX limitations.
- [ ] **A7.3 — Run final cross-browser smoke checks (0.5 day).** Verify the critical flow at desktop and mobile widths in two supported browsers and log/fix release-blocking issues.
- [ ] **A7.4 — Prepare presentation-ready seed narratives (0.5 day).** Verify names, copy, timestamps, charts, demo records, empty states, and reset behavior produce a coherent story.

### Jobin — reproducible delivery

- [ ] **J7.1 — Complete the local container stack (0.5 day).** Add the web service, migration/seed startup path, health checks, dependency ordering, persistent volume behavior, and `.env.example` values without real secrets.
- [ ] **J7.2 — Complete technical documentation (0.5 day).** Finish architecture, ERD, normalization, security, testing, performance, deployment, API examples, and known prototype limitations.
- [ ] **J7.3 — Make reset/seed/showcase scripts reliable (0.5 day).** Provide one-command clean reset, deterministic demo data, Serve API example, approval/version race demonstrations, and analytics/lineage/deployment queries.
- [ ] **J7.4 — Run clean-machine release verification (0.5 day).** Clone/start/migrate/seed/test the documented workflow, tag the tested revision, and archive command output needed as delivery evidence.

### Phase 7 exit criteria

- A clean checkout can be configured and started using only the README and example environment file.
- Seeded User and Super Admin credentials and their intended use are documented safely.
- The demo runbook completes within the allotted presentation time.
- The final acceptance checklist below is fully checked.

---

## Final prototype acceptance checklist

### Product workflow

- [ ] Register, login, restore session, and logout work.
- [ ] User and Super Admin authorization boundaries work in UI and API.
- [ ] Project creation, editing, membership, and scoped access work.
- [ ] Prompt creation and immutable v1 → v2 → v3 saves work.
- [ ] Version detail, history, diff, and lineage show real data.
- [ ] Mock-provider execution records output, tokens, latency, status, and cost.
- [ ] Run history, personal costs, and budget utilization reconcile.
- [ ] Development/staging deployment activates immediately.
- [ ] Production deployment requires and survives an atomic admin review.
- [ ] Runtime token creation, one-time display, scoped Serve fetch, and revocation work.
- [ ] Rollback changes the active served version without rewriting history.
- [ ] Budget enforcement blocks an over-limit run at the database boundary.
- [ ] Admin users, keys, budgets, pricing, analytics, audit, and maintenance views work.

### Engineering quality

- [ ] Clean migration, seed, reset, and startup paths work.
- [ ] Standard error envelopes and request IDs are used consistently.
- [ ] Loading, empty, validation, forbidden, conflict, and failure states are usable.
- [ ] Passwords are hashed; provider keys are encrypted; runtime tokens are hashed.
- [ ] Secrets are absent from logs, API list responses, fixtures, screenshots, and source control.
- [ ] Database constraints and transactions protect immutability and race-sensitive workflows.
- [ ] Critical frontend, backend, database, security, concurrency, and E2E tests pass.
- [ ] Documentation, OpenAPI output, examples, and actual behavior agree.

## Coordination rules

- Complete phases in order; within a phase, Ananya and Jobin work in parallel against the frozen contract.
- At the start of each phase, Jobin supplies example success/error payloads and Ananya confirms the UI-required fields before implementation diverges.
- Merge vertical slices frequently: endpoint + client integration + tests, instead of holding a large frontend-only or backend-only branch until phase end.
- Any contract change must update backend schema/OpenAPI, frontend type, fixture/mock, tests, and `api-contracts.md` in the same change set or linked pair of changes.
- Use stable seed identifiers only in tests and demo scripts; production UI routes must use returned IDs, not hard-coded `/1` values.
- Each phase ends with a 30-minute joint walkthrough of its exit criteria and a clean-database test.

## Suggested milestone sequence

| Milestone | Phases | Demonstrable result |
|---|---|---|
| **M1 — Secure skeleton** | 0–1 | Real authentication, protected routes, shared contracts, runnable foundation |
| **M2 — Core prompt vault** | 2 | Projects, collaboration, prompts, immutable versions, diff, lineage |
| **M3 — Evaluation loop** | 3 | Playground runs, ledger, pricing, budgets, personal analytics |
| **M4 — Release control** | 4 | Deployment, approval, runtime serving, tokens, rollback |
| **M5 — Governed prototype** | 5 | Admin operations, audit, organization analytics, maintenance |
| **M6 — Delivery candidate** | 6–7 | Tested, secured, documented, containerized, repeatable demo |
