# PromptVault local project completion plan

Updated: 2026-10-12. Owners: Ananya Ganesan and Jobin.

Scope clarified by the user on 2026-10-12: this is a local project and demonstration,
not a production deployment. No staging URL, public domain, hosting or production
release sign-off is required. This plan supplements the completed prototype plan and
[academic database requirements](database-design-requirements.md).

## Current implementation order — local acceptance

1. **A1 execution adapters (implemented; local simulated acceptance passed):** extend the existing Gemini execution path with
   OpenRouter and Groq, using encrypted server-side credentials, verified free-access
   routes, normalized errors/timeouts, usage recording and duplicate-run protection.
   The external provider allowlist remains exactly Gemini, OpenRouter and Groq.
2. **A1 discovery and Playground (implemented):** expose only supported free-access models,
   credential availability and applicable limits; add provider/model selection and
   usable missing-key, unavailable-model, quota and timeout states. The existing admin-managed shared project credentials are used.
3. **Local end-to-end acceptance (simulated HTTP passed; real keys pending):** demonstrate actual responses from each of the
   three providers through the local UI, persisted run details, refresh and safe
   failures. Existing A2 local SQL/API/browser acceptance satisfies the local A2
   gate; rerun relevant checks after new changes. No hosted A2 gate is required.
4. **A4 account profile (implemented and locally verified):** implement self-only display-name editing using the
   existing database column, validation, auth-context refresh and authorization tests.
5. **Authentication integration and local acceptance (complete):** checked the existing login,
   session/logout and password-reset flows together for the local demonstration;
   fix any gaps found. Email verification (A3) is excluded by the user and must
   not be added or used to gate access. Test reset delivery using the local/test
   setup; public-domain URLs and HTTPS deployment are not prerequisites. See
   [A5 local acceptance](a5-local-acceptance.md): 50 backend tests, 22 frontend
   authentication tests and eight desktop/mobile live browser cases passed.
6. **Academic evidence and demonstration (implemented and locally verified):** keep ER/schema documentation current,
   finalize the column dictionary and reproducible CRUD/join/aggregate/view/procedure
   evidence, then run the complete local user/admin demonstration. See
   [academic local acceptance](academic-local-acceptance.md) for the 147-column
   dictionary, rollback-only SQL collector and twelve desktop/mobile checks.
   Original design chronology and final submission review remain open.

The production-oriented sections below are historical context from the earlier
launch scope. Hosted/staging acceptance, infrastructure, backups/alerts for a hosted
service, production release automation and pilot-user gates are outside current
scope and must not block local project completion. Their unchecked boxes are not
requirements to implement. Existing security, data-integrity and concurrency checks
remain applicable to the local application.

Scope update (2026-10-12): email verification is not required. All historical A3,
verification/resend, verified-email access gates and verification acceptance items
below are excluded. Local authentication/reset acceptance (A5) is complete. The
academic evidence and full local demonstration are also technically complete.
Remaining boundaries are original design chronology, final submission review and
real free-tier provider-account calls.

The repository audit and first implementation batch are recorded in
[A2 live acceptance](a2-live-acceptance.md). Start with **A2 acceptance**, then
**A1 contract/discovery**. Do not rebuild the existing live workflow integrations.

Local implementation and verification are recorded in
[A1 acceptance](a1-local-acceptance.md) and [A4 acceptance](a4-local-acceptance.md).

## Current baseline

- The frontend already uses live APIs for authentication, projects, membership,
  prompts, versions, runs, deployments, tokens, and administration. Extend and
  verify these integrations rather than rebuilding them.
- SMTP, a branded reset email, the website reset page, password-history hashes,
  and password-reuse rejection are implemented. Gmail authentication was verified;
  repeat the full delivery/reset journey on the hosted domain.
- Jobin's changes through `89b86b5` are integrated locally. The Gemini adapter,
  encrypted credential lookup, pre-call budget reservations, user-scoped idempotency,
  concurrency limits and interrupted-execution maintenance are implemented. Safe
  discovery and hosted real-provider acceptance remain part of A1/J1/J2.
- Admission now takes the reservation's exclusive user lock before checking access,
  avoiding concurrent shared-to-exclusive lock upgrades. Existing A2 coherent
  pagination, dashboard snapshots and membership read locks are preserved.
- CI already runs frontend and backend checks. Staging/release automation and live
  browser acceptance still need production coverage.
- Normal local startup now reuses the original `promptvault` database on
  localhost:5432, matching pgAdmin. Its recorded migrations 001–015 passed checksum
  verification and pending 016–023 were applied without resetting existing data.
  `.venv/bin/python scripts/start-local.py` fixes web/API ports at 5173/8000;
  separate test databases remain isolated from the normal app.
- Current session tokens are stored in sessionStorage. Database-backed sessions,
  logout/reset/role-change revocation and distributed rate-limit support are now
  implemented; hosted session and verification acceptance remain open.
- Jobin's branch includes a cost analytics page. Its presence does not add a
  monetary-page launch prerequisite; retain backend accounting and budget protection.

Local integration validation and the disposable database setup are recorded in
[Jobin integration acceptance](jobin-integration-acceptance.md). Existing A2 evidence
remains historical evidence for its original working tree; hosted sign-off is still open.

## Confirmed provider and payment scope

The project's external provider scope is Gemini, OpenRouter and Groq.
Use free-access configurations only; no payment, credit purchase, subscription or
checkout flow is in scope. Keep mock execution for development and tests.
This allowlist is fixed for the entire project and demonstration. DeepSeek and all
other external providers are excluded, including fallback routes. Free access must
be verified for the selected API/model/account. OpenRouter discovery must
select verified free models and must not fall back to paid models. Preserve usage,
quota, concurrency, timeout and idempotency controls when monetary cost is zero.
Credential ownership (shared application keys or user-owned keys) remains undecided.

## Decisions to make together first

- Shared application LLM credentials or user-owned credentials for the three selected providers.
- Public signup or invited/approved users for the initial pilot.
- One centrally administered workspace or independent customer organizations.
  If independent organizations are promised, tenant isolation becomes a launch blocker.
- Initial usage quotas, maximum concurrent runs, input/output limits, data retention,
  and account deletion/export policy.
- Hosting/domain, staging domain, and backup/recovery targets. Payments and
  subscriptions are outside the confirmed project scope.

## Ananya — own complete application and live-data features

| Task | Scope | Done when |
|---|---|---|
| [ ] A1 — Execution contract, discovery, then live Playground | A1a: agree credential ownership, free-access eligibility, discovery fields, supported-model limits, credential availability, idempotency, persisted statuses and error shapes with Jobin; implement safe discovery/types/forms. A1b: integrate J1/J2 execution, preserving the existing Playground and run details. Keep unsupported providers unavailable and return no secret/ciphertext. | A1a has an agreed contract and API tests. A1b has hosted responses for the enabled free-access providers, credential/quota/timeout/error states, tokens/latency, persisted result details, and proof that unavailable or non-free routes cannot execute. |
| [ ] A2 — Data freshness: implementation complete, hosted sign-off pending | A2a/A2b implementation and isolated acceptance are complete: coherent count/page queries, dashboard snapshot, membership-safe detail reads, bounded multi-page reconciliation, all six workflow SQL checks, cross-user refresh, stale responses, draft preservation and access isolation. No new endpoint/schema needed. Repeat on staging and include J4 authorization review before release sign-off. | 325 backend tests, 132 frontend unit tests and 10 desktop/mobile live checks passed; lint/types/build/OpenAPI checks passed. Final API/SQL values agree, with source fingerprints in the evidence. The release checkbox remains open until the same checks pass on staging at the release revision. |
| [ ] A3 — Email verification end to end | Design schema/contract first; implement hashed expiring one-use verification tokens, verification/resend endpoints, email template, and verification pages. Jobin reviews abuse limits and authorization rules. | An invited or registered user receives verification mail, verifies once, and expired/reused links and resend behavior work under the agreed signup policy. |
| [ ] A4 — Account profile backed by the database | After agreeing display name as the editable field, add a self-only update through repository/service/API/UI, validation, auth-context refresh, and authorization tests. Reuse the existing users.display_name column. Keep email/role/security changes on separately reviewed flows. | Display-name edits persist after reload and appear across the UI; attempts to update another user or submit role/email/security fields fail. A4 can proceed before A3 when its authorization contract is reviewed. |
| [ ] A5 — Authentication and reset integration | Integrate Jobin's production sessions and revocation, correct hosted email URLs, expiry/logout recovery, password-history errors, and verification status. | Login, refresh, logout, reset, role/membership changes, and verification work on the HTTPS site; old passwords are rejected. |
| [ ] A6 — Hosted UX and browser acceptance | Own onboarding, loading/empty/error states, mobile and keyboard checks, and live browser workflows against staging; resolve data/UI failures with evidence. | A new real user can complete the entire product journey without developer assistance. |
| [ ] A7 — Continuous schema documentation and final database evidence | Maintain ER/schema/dictionary changes before new tables or columns; gather API/SQL evidence alongside each task. Finalize CRUD/join/aggregate/view and UI reconciliation demonstrations against J8's reviewed final schema, including the explicit PROCEDURE/CALL requirement. | Every table maps to the ER/schema; column dictionary and executable evidence meet academic requirements and match the final release. Final evidence is last, but design documentation starts before A3/session migrations. |
| [ ] A8 — Frontend release and user support | Configure public API URL, production routing/assets, frontend error reporting, CI browser smoke checks, user documentation, and a support contact flow. | A staging-tested frontend deploys reproducibly, direct links work, errors are diagnosable without credential leakage, and users know how to get support. |

Ananya's A1, A2, A3, and A4 include API/backend/database ownership; she is not limited
to frontend work. Both developers review authorization on endpoints they add.

A2 status (2026-10-11):

- [x] A2a: isolated live acceptance and SQL/UI/API reconciliation.
- [x] A2b implementation: count/page snapshots, dashboard consistency, membership
  read locks, bounded pagination reconciliation, and regression coverage.
- [ ] Hosted A2 release sign-off and J4 review: staging URL/accounts/SQL access are
  not available in this session. Keep the joint release gate open; A1 contract work
  can now proceed. See [A2 evidence](a2-live-acceptance.md).

## Jobin — execution, security, database integrity, and operations

| Task | Scope | Done when |
|---|---|---|
| [ ] J1 — Three-provider execution using free access | Extend the Gemini adapter/factory with OpenRouter and Groq under verified free-access routes; implement credential retrieval/decryption, supported models, timeout/error translation and usage recording. Keep providers unavailable until their zero-payment route is established. | A real request completes through the API with persisted output and accurate usage; secrets never enter frontend responses or logs. |
| [ ] J2 — Budget admission, quotas, and idempotency | Enforce free-access eligibility and quota/concurrency admission before execution; retain the existing reservation ledger for usage, failed/uncertain outcomes and concurrent attempts. Implement user-scoped idempotency and request/concurrency limits. | Over-budget requests never reach the provider; duplicate submissions cannot trigger duplicate execution; usage and reservation accounting remain consistent without replaying uncertain calls. |
| [ ] J3 — Production sessions and authentication abuse protection | Finalize secure session transport/storage, revocation on logout/reset, appropriate CSRF protection if cookies are used, expiry behavior, and distributed login/reset/resend rate limits. Review Ananya's verification flow. | Old sessions fail after reset/revocation, session behavior works across deployment instances, and authentication abuse tests pass. |
| [ ] J4 — Authorization and tenancy audit | Test every resource/read/write/admin/Serve route with multiple unrelated accounts, removed members, inactive users, revoked tokens, and role changes. Add tenant boundaries if required by the product decision. | Identifier guessing and stale credentials cannot cross access boundaries; global administrator permissions are deliberate and tested. |
| [ ] J5 — Production infrastructure and configuration | Set up HTTPS, frontend/API routing, private PostgreSQL access, least-privilege app login, managed secrets, restricted CORS, and separate staging/production databases. Use an explicit production-admin bootstrap; no demo seeds in production. | Production boots with safe configuration, correct public reset/verification URLs, isolated data, and no development credentials/accounts. |
| [ ] J6 — Execution recovery and maintenance | Define persisted run states and interrupted-call recovery; use workers/queue if needed for expected execution duration/concurrency. Schedule partition creation, view refresh, and expired-token cleanup. | Restart/crash tests leave explainable run states and correct reservations; month rollover and maintenance work automatically. |
| [ ] J7 — Backups, monitoring, and release automation | Automate encrypted backups/retention, restore drills, health/error/provider/spend alerts, migrations, deploy smoke checks, and rollback. Extend existing CI rather than replacing it. | A restore is demonstrated; alerts reach operators; a failed release can be recovered without losing committed data. |
| [ ] J8 — Database design and academic compliance | Complete ER-to-table mapping including auth/history/tracking tables, relational schema, functional-dependency/3NF review, PK/FK/constraints/index evidence, and a real PostgreSQL stored procedure with CALL demonstration. Diagnose the original database's checksum mismatch safely. | Every database requirement is reviewed and supported by executable evidence; applied migrations remain immutable. |
| [ ] J9 — Security, capacity, and lifecycle validation | Test expected load, dependency/configuration security, concurrent provider execution, data retention, and the agreed account deletion/export behavior; document operational limits. | Pilot capacity is measured, no launch-blocking authorization/data-loss defect remains, and lifecycle policy is implemented. |

## Work order and dependencies

1. **A2a first:** execute isolated live acceptance, fix failures, and publish SQL/API/UI
   evidence. Joint decisions can proceed alongside this work; deterministic mock
   execution lets A2a proceed without real-provider credentials or onboarding-policy changes.
2. **A1a next:** agree the execution/discovery contract with Jobin. Jobin implements
   J1/J2 and J5 staging; jointly settle credential ownership, free-access eligibility, quotas and limits
   before enabling the three selected providers. Ananya implements discovery and configuration against that
   contract. Resolve A2b snapshot/authorization concurrency issues with J4.
3. **A4 while execution dependencies are pending:** agree permitted self-profile
   fields and authorization, then persist display-name edits. Finish A1b once J1/J2
   are available; verify real execution and A2 on staging before claiming completion.
4. **A3 then A5:** agree onboarding and verification/access rules; update ER/schema
   before verification/session migrations. Implement verification with email setup
   and J3/J4 review, then integrate production sessions and the existing reset flow.
5. **A8 setup before final A6 acceptance:** establish public routing/URLs and browser
   CI alongside J5/J6/J7/J9, then run the full hosted journey, mobile/keyboard and
   failure/recovery checks. Complete user documentation and support before pilot.
6. **Final A7/J8 evidence and release gate:** refresh the continuously maintained
   schema/dictionary, test the exact candidate revision, verify backup recovery,
   and conduct the agreed public or invitation-only pilot. Payments and subscriptions remain
   outside project scope.

## Joint release gate

- [ ] Newly registered/invited users complete verification, login, and reset on HTTPS.
- [ ] Project/member/prompt/version changes persist and remain properly scoped.
- [ ] Real execution records usage and obeys pre-call budget/quota/idempotency rules.
- [ ] Approval, Serve, rollback, and token revocation work with hosted data.
- [ ] Data stays current after relevant mutations and controlled cross-user refresh.
- [ ] Old credentials/sessions lose access when required; no secrets are exposed.
- [ ] A restart, interrupted execution, failed deployment, and backup restore are tested.
- [ ] Production contains intended accounts only and is isolated from demo/test fixtures.
- [ ] Tests, browser checks, schema documentation, and academic evidence agree with
  the exact release revision.
- [ ] Pilot users finish the workflow and have an available support channel.
