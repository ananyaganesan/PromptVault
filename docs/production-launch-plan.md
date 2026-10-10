# PromptVault production launch plan

Updated: 2026-10-10. Owners: Ananya Ganesan and Jobin.

This plan covers the remaining work to host real users. It supplements the completed
prototype plan and the [academic database requirements](database-design-requirements.md).
Items are unchecked until their acceptance evidence exists on the release revision.

## Current baseline

- The frontend already uses live APIs for authentication, projects, membership,
  prompts, versions, runs, deployments, tokens, and administration. Extend and
  verify these integrations rather than rebuilding them.
- SMTP, a branded reset email, the website reset page, password-history hashes,
  and password-reuse rejection are implemented. Gmail authentication was verified;
  repeat the full delivery/reset journey on the hosted domain.
- Only the mock provider executes requests; `gemini.py` is empty. Saved provider
  credentials are not yet connected to paid execution.
- Budget enforcement currently records its decision after provider execution.
  Admission/reservation must precede paid calls.
- CI already runs frontend and backend checks. Staging/release automation and live
  browser acceptance still need production coverage.
- The running preview database is separate from the original local database, which
  has a migration-016 checksum mismatch. Preserve data and diagnose migration history;
  do not bypass checksum protection or use a reset to repair valuable data.
- Current session tokens are stored in sessionStorage. Session revocation and the
  production session strategy need explicit implementation and verification.
- Costs were removed from the current UI. Do not reintroduce monetary pages as a
  launch prerequisite; retain backend cost accounting and budget protection.

## Decisions to make together first

- Shared application LLM credentials or user-owned credentials; define who pays.
- Public signup or invited/approved users for the initial pilot.
- One centrally administered workspace or independent customer organizations.
  If independent organizations are promised, tenant isolation becomes a launch blocker.
- Initial usage quotas, maximum concurrent runs, input/output limits, data retention,
  and account deletion/export policy.
- Hosting/domain, staging domain, and backup/recovery targets. Paid subscriptions
  and payment integration are conditional on deciding to charge users.

## Ananya — own complete application and live-data features

| Task | Scope | Done when |
|---|---|---|
| [ ] A1 — Provider/model configuration and live Playground | Own the safe provider/model discovery API, response types, configuration forms, and run UI. Expose supported models and credential availability only; integrate Jobin's execution API. | Real Gemini response, missing-key/pricing/quota/timeout states, tokens/latency, and persisted run detail work through the hosted UI. |
| [ ] A2 — Data freshness across workflows | Own cache invalidation/refetch logic, pagination/filter correctness, and SQL/API reconciliation for runs, recent activity, projects, versions, approvals, and active deployments. Add narrowly scoped read endpoints only where a gap is demonstrated. | A mutation is reflected in the relevant screens; another user's change appears after controlled refresh/polling; lists and counts match PostgreSQL without leaking other users' data. |
| [ ] A3 — Email verification end to end | Design schema/contract first; implement hashed expiring one-use verification tokens, verification/resend endpoints, email template, and verification pages. Jobin reviews abuse limits and authorization rules. | An invited or registered user receives verification mail, verifies once, and expired/reused links and resend behavior work under the agreed signup policy. |
| [ ] A4 — Account profile backed by the database | Implement permitted profile updates through schema/service/repository/API and UI, with validation and tests. Keep email/role/security changes on explicitly reviewed flows. | Editing display name persists after reload; users cannot update another account or assign themselves a role. |
| [ ] A5 — Authentication and reset integration | Integrate Jobin's production sessions and revocation, correct hosted email URLs, expiry/logout recovery, password-history errors, and verification status. | Login, refresh, logout, reset, role/membership changes, and verification work on the HTTPS site; old passwords are rejected. |
| [ ] A6 — Hosted UX and browser acceptance | Own onboarding, loading/empty/error states, mobile and keyboard checks, and live browser workflows against staging; resolve data/UI failures with evidence. | A new real user can complete the entire product journey without developer assistance. |
| [ ] A7 — Database evidence and dictionary | Prepare the column-by-column dictionary and reproducible CRUD/join/aggregate/view demonstrations using real API/SQL results. Compare UI values with query results. | Evidence satisfies the supplied academic requirements and agrees with Jobin's final schema and 3NF analysis. |
| [ ] A8 — Frontend release and user support | Configure public API URL, production routing/assets, frontend error reporting, CI browser smoke checks, user documentation, and a support contact flow. | A staging-tested frontend deploys reproducibly, direct links work, errors are diagnosable without credential leakage, and users know how to get support. |

Ananya's A1, A2, A3, and A4 include API/backend/database ownership; she is not limited
to frontend work. Both developers review authorization on endpoints they add.

## Jobin — execution, security, database integrity, and operations

| Task | Scope | Done when |
|---|---|---|
| [ ] J1 — Real Gemini execution | Implement adapter/factory, credential retrieval/decryption under the agreed ownership model, supported model settings, timeout/error translation, and actual usage/cost recording. | A real request completes through the API with persisted output and accurate usage; secrets never enter frontend responses or logs. |
| [ ] J2 — Budget admission, quotas, and idempotency | Reserve estimated maximum cost before paid execution; atomically reconcile usage, failed/uncertain outcomes, and concurrent attempts. Implement user-scoped idempotency and request/concurrency limits. | Over-budget requests never reach the provider; duplicate submissions cannot trigger duplicate execution; accounting matches actual charges without silently treating uncertain calls as free. |
| [ ] J3 — Production sessions and authentication abuse protection | Finalize secure session transport/storage, revocation on logout/reset, appropriate CSRF protection if cookies are used, expiry behavior, and distributed login/reset/resend rate limits. Review Ananya's verification flow. | Old sessions fail after reset/revocation, session behavior works across deployment instances, and authentication abuse tests pass. |
| [ ] J4 — Authorization and tenancy audit | Test every resource/read/write/admin/Serve route with multiple unrelated accounts, removed members, inactive users, revoked tokens, and role changes. Add tenant boundaries if required by the product decision. | Identifier guessing and stale credentials cannot cross access boundaries; global administrator permissions are deliberate and tested. |
| [ ] J5 — Production infrastructure and configuration | Set up HTTPS, frontend/API routing, private PostgreSQL access, least-privilege app login, managed secrets, restricted CORS, and separate staging/production databases. Use an explicit production-admin bootstrap; no demo seeds in production. | Production boots with safe configuration, correct public reset/verification URLs, isolated data, and no development credentials/accounts. |
| [ ] J6 — Execution recovery and maintenance | Define persisted run states and interrupted-call recovery; use workers/queue if needed for expected execution duration/concurrency. Schedule partition creation, view refresh, and expired-token cleanup. | Restart/crash tests leave explainable run states and correct reservations; month rollover and maintenance work automatically. |
| [ ] J7 — Backups, monitoring, and release automation | Automate encrypted backups/retention, restore drills, health/error/provider/spend alerts, migrations, deploy smoke checks, and rollback. Extend existing CI rather than replacing it. | A restore is demonstrated; alerts reach operators; a failed release can be recovered without losing committed data. |
| [ ] J8 — Database design and academic compliance | Complete ER-to-table mapping including auth/history/tracking tables, relational schema, functional-dependency/3NF review, PK/FK/constraints/index evidence, and a real PostgreSQL stored procedure with CALL demonstration. Diagnose the original database's checksum mismatch safely. | Every database requirement is reviewed and supported by executable evidence; applied migrations remain immutable. |
| [ ] J9 — Security, capacity, and lifecycle validation | Test expected load, dependency/configuration security, concurrent paid execution, data retention, and the agreed account deletion/export behavior; document operational limits. | Pilot capacity is measured, no launch-blocking authorization/data-loss defect remains, and lifecycle policy is implemented. |

## Work order and dependencies

1. **Start now:** jointly settle credential/signup/tenancy rules. Ananya begins A1's
   contract and A2's data audit; Jobin begins J1/J2 and creates staging infrastructure.
2. **Connect real execution:** finish A1/A2 + J1/J2. Agree discovery fields, idempotency,
   statuses, and errors before frontend/backend work diverges.
3. **Complete user access:** finish A3/A4/A5 + J3/J4. Update ER/schema before any new
   verification or session tables; review security together.
4. **Prepare hosted operations:** finish A6/A8 + J5/J6/J7/J9. Validate public-domain
   email delivery, backups, quotas, failures, and recovery on staging.
5. **Finalize evidence:** finish A7 + J8, run the full release checks on the exact
   candidate revision, then conduct an invited-user pilot before wider signup.

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
