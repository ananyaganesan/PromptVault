# Email Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require every newly registered PromptVault account to verify its email before receiving a session, while preserving existing accounts and clear duplicate-email errors.

**Architecture:** Migration 024 backfills `users.email_verified_at`, creates a dedicated hashed one-use token table, and exposes an atomic confirmation function. FastAPI registration, confirmation, resend, and login flows use the existing transactional repository/service pattern and SMTP transport; React adds pending-registration, verification, and resend states without storing a session before verification.

**Tech Stack:** PostgreSQL 18 SQL migrations, Python 3.11+/FastAPI/Pydantic/psycopg, SMTP `EmailMessage`, React 19/TypeScript/Vitest/Playwright.

**Spec:** `docs/superpowers/specs/2026-10-13-email-verification-design.md`

## Global Constraints

- Existing accounts are marked verified during migration; new accounts start unverified.
- Verification links expire after 30 minutes and store only SHA-256 token hashes.
- Resend uses a 60-second account cooldown and five attempts per rolling hour for each client-identifier/normalized-email-hash composite.
- New verification links invalidate older unused links; confirmation is atomic and one-use.
- Registration returns no access token; verification does not create a session.
- Duplicate registration stays HTTP `409 duplicate_email` with `An account with this email already exists`.
- Unknown, inactive, and verified-account resend requests return the same generic HTTP `202` response.
- Existing password reset, session revocation, account lifecycle, local database, and fixed LLM-provider behavior must remain unchanged.
- Tests use an explicitly separate database ending in `_test`; normal startup continues using root `.env` and `localhost:5432/promptvault`.
- No staging, public-domain, hosting, or production-release work is added.

## Review Focus

- A mixed-case email on register, resend, and login must identify the same CITEXT account without leaking a second identity; Task 3 adds integration coverage.
- A correct password for an unverified account must return `email_unverified`, while a wrong password for that same account must remain `invalid_credentials`; Task 3 pins the ordering.
- Two confirmation requests racing on one token must produce one state transition and leave the account verified; Task 3 adds a concurrent database/API test.
- Two resend requests racing after cooldown must not create two live links or evade the account cooldown; Task 4 adds the race test around the locked replacement operation.
- SMTP acceptance followed by a request rollback must not leave a committed pending user or replace the prior usable token on reported delivery failure; Tasks 2–4 assert transactional outcomes with simulated SMTP.

---

### Task 1: Persist Verification State and Atomic Token Consumption

**Files:**
- Modify: `AGENTS.md`
- Create: `db/migrations/024_email_verification.sql`
- Modify: `tests/database/test_schema_migrations.py`
- Modify: `tests/database/test_migration_upgrade.py`
- Modify: `tests/delivery/test_academic_evidence.py`

**Interfaces:**
- Produces: `users.email_verified_at TIMESTAMPTZ`; table `email_verification_tokens`; restricted SQL function `confirm_email_verification(p_token_hash CHAR(64)) RETURNS BOOLEAN`.
- Produces: existing users with non-null `email_verified_at`; future inserts defaulting to null.

- [ ] **Step 1: Record the approved authentication scope**

Replace the obsolete `AGENTS.md` email-verification exclusion with the approved requirements: existing-account backfill, new-account login gating, 30-minute one-use links, 60-second resend cooldown, five attempts per rolling hour, generic resend responses, duplicate-email feedback, and local-only validation. Preserve every provider, database, and local-project constraint verbatim.

- [ ] **Step 2: Write failing migration-shape tests**

Update the expected migration chain to `range(1, 25)` and assert migration 024 contains the user column/backfill, token table/index/grants, row locking, token expiry/use checks, and `SECURITY DEFINER` confirmation function. Update the academic migration count from 23 to 24.

- [ ] **Step 3: Write the failing upgrade-preservation test**

Extend `assert_preserved_rows_and_fk(...)` to assert the pre-existing user has non-null `email_verified_at`, the old password-reset token remains unchanged, and the new token table has a foreign key to `users`. Expect 24 applied migrations.

- [ ] **Step 4: Run the database tests and verify RED**

Run: `TEST_DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_test python3 -m pytest tests/database/test_schema_migrations.py tests/database/test_migration_upgrade.py tests/delivery/test_academic_evidence.py -q`

Expected: FAIL because migration 024 and its schema objects do not exist.

- [ ] **Step 5: Implement migration 024**

Add and backfill `email_verified_at`, then make no default that would verify future registrations. Create `email_verification_tokens` and its active-token index. Implement `confirm_email_verification(CHAR(64)) -> BOOLEAN` to lock the eligible token and user, set verification time once, consume the selected token, invalidate other unused tokens, and expose only `EXECUTE` on the function to `promptvault_app` while granting repository-required table operations.

- [ ] **Step 6: Run the database tests and verify GREEN**

Run the Step 4 command.

Expected: PASS, including fresh and legacy upgrade preservation.

- [ ] **Step 7: Commit**

```bash
git add AGENTS.md db/migrations/024_email_verification.sql tests/database/test_schema_migrations.py tests/database/test_migration_upgrade.py tests/delivery/test_academic_evidence.py
git commit -m "feat: add email verification schema"
```

### Task 2: Configure and Deliver Verification Email

**Files:**
- Create: `api/app/templates/email-verification.html`
- Modify: `api/app/config.py`
- Modify: `api/app/email.py`
- Modify: `api/tests/unit/test_config.py`
- Modify: `api/tests/unit/test_email.py`
- Modify: `.env.example`
- Modify: `.env.production.example`

**Interfaces:**
- Produces: `Settings.email_verification_url: str`, `email_verification_ttl_minutes: int`, `email_verification_resend_cooldown_seconds: int`, `email_verification_resend_limit: int`, and `email_verification_resend_window_seconds: int` with spec defaults.
- Produces: `send_email_verification_email(settings: Settings, recipient: str, token: str) -> None`.
- Consumes: existing SMTP/TLS transport and `EmailDeliveryError`.

- [ ] **Step 1: Write failing configuration tests**

Add tests for the exact defaults (`30`, `60`, `5`, `3600`, and `http://localhost:5173/verify-email`), rejection of zero/negative limits, rejection of credentialed/fragmented/non-HTTP verification URLs, and HTTPS enforcement only under the same production-with-SMTP condition used by password reset.

- [ ] **Step 2: Run configuration tests and verify RED**

Run: `python3 -m pytest api/tests/unit/test_config.py -q`

Expected: FAIL because the verification settings do not exist.

- [ ] **Step 3: Implement the settings and environment examples**

Add the five typed settings and fold them into the existing URL/runtime-limit validator without changing password-reset validation. Document local values in `.env.example` and an HTTPS verification URL in `.env.production.example`; this maintains existing configuration examples without adding deployment work.

- [ ] **Step 4: Run configuration tests and verify GREEN**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 5: Write failing verification-email tests**

Assert `send_email_verification_email(...)` builds a branded multipart message with subject `Verify your PromptVault email`, recipient, safely merged `token` query parameter, 30-minute copy, inline logo, and the shared SMTP authentication/TLS behavior. Assert missing SMTP and transport failures raise only `EmailDeliveryError` without sensitive server text.

- [ ] **Step 6: Run email tests and verify RED**

Run: `python3 -m pytest api/tests/unit/test_email.py -q`

Expected: FAIL because the function and template do not exist.

- [ ] **Step 7: Implement the verification email**

Add the template and `send_email_verification_email(...)`. Extract private URL/message/SMTP helpers only where they remove duplication while keeping password-reset output unchanged.

- [ ] **Step 8: Run email tests and verify GREEN**

Run: `python3 -m pytest api/tests/unit/test_email.py api/tests/unit/test_config.py -q`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add .env.example .env.production.example api/app/config.py api/app/email.py api/app/templates/email-verification.html api/tests/unit/test_config.py api/tests/unit/test_email.py
git commit -m "feat: send email verification links"
```

### Task 3: Register Pending Accounts, Confirm Them, and Gate Login

**Files:**
- Modify: `api/app/repositories/users.py`
- Modify: `api/app/schemas/auth.py`
- Modify: `api/app/services/auth.py`
- Modify: `api/app/routers/auth.py`
- Modify: `api/tests/integration/test_auth.py`
- Modify: `api/tests/integration/test_authorization_dependencies.py`
- Modify: `api/tests/integration/test_admin_governance.py`
- Modify: `api/tests/integration/test_deployments_tokens_serve.py`
- Modify: `api/tests/integration/test_projects_prompts_versions.py`
- Modify: `api/tests/integration/test_runs_dashboard.py`
- Create: `tests/auth_support.py`
- Modify: `tests/support.py`
- Modify: `tests/security/test_authorization_matrix.py`
- Modify: `tests/security/test_secret_redaction.py`

**Interfaces:**
- Produces: `PendingVerificationResponse(email: EmailStr, message: str)`.
- Produces: `EmailVerificationConfirm(token: str)` and `AuthService.confirm_email_verification(request: EmailVerificationConfirm) -> None`.
- Produces: internal `UserRecord.email_verified_at: datetime | None`; public user responses remain unchanged because clients need only the login error and verification endpoints.
- Produces repository methods `create_email_verification_token(*, user_id: UUID, token_hash: str, expires_at: datetime) -> None` and `confirm_email_verification(token_hash: str) -> bool`.
- Changes: `AuthService.register(request: RegisterRequest) -> PendingVerificationResponse` and `POST /auth/register` to HTTP `202`.
- Produces test-only `create_verified_test_user(client: TestClient, label: str) -> tuple[dict[str, object], dict[str, str]]`, which inserts a verified user into the client's isolated database and logs in through the public API for non-authentication integration tests.

- [ ] **Step 1: Write failing registration tests**

Change the auth integration expectation so registration returns `202`, normalized email, and check-inbox copy with no `access_token`. Query PostgreSQL to assert the user has null `email_verified_at`, exactly one unused token exists, and its stored value equals SHA-256 of the raw token captured from simulated email rather than the raw token itself. Retain the mixed-case duplicate test and assert its exact message.

- [ ] **Step 2: Write failing login-order tests**

Add one test proving correct credentials on the pending account return `403 email_unverified`, and another proving a wrong password on that same account returns the unchanged `401 invalid_credentials`. Update seeded/existing account fixtures to remain verified.

- [ ] **Step 3: Write failing confirmation tests**

Cover success (`204` and non-null `email_verified_at`), login after success, malformed/unknown/expired/used tokens sharing `400 invalid_verification_token`, cross-use rejection by password-reset confirmation, and two concurrent confirmations producing one successful transition.

- [ ] **Step 4: Run focused auth tests and verify RED**

Run: `TEST_DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_test python3 -m pytest api/tests/integration/test_auth.py -q`

Expected: FAIL on pending response, verification persistence, confirmation route, and login gate.

- [ ] **Step 5: Implement repository records and token methods**

Add `email_verified_at` to every user projection and `_user_from_row`. Insert the initial hashed token and call the migration function for confirmation. Keep raw tokens out of repository/database interfaces.

- [ ] **Step 6: Implement schemas, service flow, and routes**

Registration creates the user/token, calls `send_email_verification_email`, returns the pending response, and maps SMTP failure to `503 email_delivery_unavailable` so the request transaction rolls back. Confirmation hashes its request token and maps false to `400 invalid_verification_token`. Login checks `is_active`, then `email_verified_at`, only after password verification.

- [ ] **Step 7: Update API test registration helpers**

Create the isolated-database helper for tests whose subject is not registration, then replace each local `register`/`register_user` implementation and `tests.support.register` with it. Keep `test_auth.py` on the real register-email-confirm-login flow so session issuance and token handling remain integration-tested. The helper must refuse database names not ending in `_test`.

- [ ] **Step 8: Run auth and authorization tests and verify GREEN**

Run: `TEST_DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_test python3 -m pytest api/tests/integration/test_auth.py api/tests/integration/test_authorization_dependencies.py api/tests/integration/test_admin_governance.py -q`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add api/app/repositories/users.py api/app/schemas/auth.py api/app/services/auth.py api/app/routers/auth.py api/tests/integration tests/auth_support.py tests/support.py tests/security/test_authorization_matrix.py tests/security/test_secret_redaction.py
git commit -m "feat: require verified email for sessions"
```

### Task 4: Resend Safely with Cooldown and Composite Rate Limits

**Files:**
- Modify: `api/app/auth_rate_limits.py`
- Modify: `api/app/main.py`
- Modify: `api/app/repositories/users.py`
- Modify: `api/app/schemas/auth.py`
- Modify: `api/app/services/auth.py`
- Modify: `api/app/routers/auth.py`
- Modify: `api/tests/unit/test_auth_rate_limits.py`
- Modify: `api/tests/integration/test_auth.py`

**Interfaces:**
- Produces: `EmailVerificationResendRequest(email: EmailStr)` using the existing email normalization rule.
- Produces: `enforce_email_verification_resend_limit(store: RateLimitStore, *, client_host: str, normalized_email: str, requests: int, window_seconds: int) -> None`; its store key contains SHA-256 email material, never raw email.
- Produces: `UserRepository.replace_email_verification_token(*, user_id: UUID, token_hash: str, expires_at: datetime, cooldown_seconds: int) -> int | None`, where an integer is retry-after seconds and `None` means replacement succeeded.
- Produces: `AuthService.resend_email_verification(request: EmailVerificationResendRequest) -> None`.

- [ ] **Step 1: Write failing composite rate-limit tests**

Using the real local store, assert five requests for the same client/email composite are allowed and the sixth raises/returns `429` with `Retry-After`; different normalized emails and different client hosts receive independent budgets; captured keys contain neither original nor normalized raw email; two API instances share the injected store.

- [ ] **Step 2: Run limiter tests and verify RED**

Run: `python3 -m pytest api/tests/unit/test_auth_rate_limits.py -q`

Expected: FAIL because the resend limiter does not exist.

- [ ] **Step 3: Implement the limiter and app-state wiring**

Hash normalized email with SHA-256, combine it with the direct ASGI client host and a dedicated group name, call `RateLimitStore.retry_after`, and raise `AppError(429, "rate_limited", ...)` with `Retry-After`. Store the resolved limiter on `application.state` for the route to use without creating a second local/Redis store.

- [ ] **Step 4: Run limiter tests and verify GREEN**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 5: Write failing resend integration tests**

Assert unknown, inactive, and verified accounts share exact generic `202` output and send no mail. For a pending account, assert resend sends a new token, invalidates the old link, and leaves only the new link usable. Assert an immediate resend returns `429` with a 60-second retry hint, six requests across eligible time advances trigger the hourly limit, SMTP failure preserves the prior token, and two racing resends cannot create two active tokens or bypass cooldown.

- [ ] **Step 6: Run resend tests and verify RED**

Run: `TEST_DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_test python3 -m pytest api/tests/integration/test_auth.py -q`

Expected: FAIL because the resend route and locked replacement operation do not exist.

- [ ] **Step 7: Implement token replacement, service, and route**

Lock the user before checking the most recent token timestamp. On eligibility, mark old unused tokens used and insert the new hash in the same transaction. Apply the composite limiter before account lookup, return generic success for ineligible identities, and let `EmailDeliveryError` roll the request back to preserve the previous token.

- [ ] **Step 8: Run resend and auth tests and verify GREEN**

Run: `TEST_DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_test python3 -m pytest api/tests/unit/test_auth_rate_limits.py api/tests/integration/test_auth.py -q`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add api/app/auth_rate_limits.py api/app/main.py api/app/repositories/users.py api/app/schemas/auth.py api/app/services/auth.py api/app/routers/auth.py api/tests/unit/test_auth_rate_limits.py api/tests/integration/test_auth.py
git commit -m "feat: resend verification emails safely"
```

### Task 5: Build Pending, Verification, and Login-Resend UI States

**Files:**
- Modify: `web/src/types/api.ts`
- Modify: `web/src/types/auth.ts`
- Modify: `web/src/features/auth/api.ts`
- Modify: `web/src/features/auth/auth-context.tsx`
- Modify: `web/src/features/auth/pages.tsx`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/features/auth/api-mode.test.tsx`
- Create: `web/src/features/auth/email-verification.test.tsx`

**Interfaces:**
- Produces: frontend `PendingVerificationResponse { email: string; message: string }`; the verification timestamp stays server-internal.
- Changes: `AuthValue.register(request: RegisterRequest) -> Promise<PendingVerificationResponse>` without saving an access token.
- Produces API calls `confirmEmailVerification(token: string) -> Promise<void>` and `resendEmailVerification(email: string) -> Promise<void>`.
- Produces route component `VerifyEmailPage` at `/verify-email`.

- [ ] **Step 1: Write failing pending-registration tests**

Assert `202` registration shows `Check your email`, the normalized submitted address, no dashboard navigation, no session-storage token, a disabled resend control counting down from 60 seconds, and exact duplicate-account feedback on `409 duplicate_email`.

- [ ] **Step 2: Write failing verification-page tests**

Assert a missing token renders an invalid-link state without calling the API; a valid query token calls confirmation once and shows a sign-in action; `invalid_verification_token` shows invalid/expired copy; no path creates a session.

- [ ] **Step 3: Write failing login-resend tests**

Assert `403 email_unverified` shows the required message and resend action for the typed email; resend success uses the generic copy; cooldown disables the action; `429` and `503` errors remain visible and recoverable.

- [ ] **Step 4: Run frontend auth tests and verify RED**

Run: `npm test -- --run src/features/auth/api-mode.test.tsx src/features/auth/email-verification.test.tsx`

Working directory: `web`

Expected: FAIL because pending responses, verification route, and resend controls do not exist.

- [ ] **Step 5: Implement frontend types, API methods, and auth context**

Change registration to return pending data without mutating `user`, access-token memory, or session storage. Add confirmation/resend API methods and the new error-code types.

- [ ] **Step 6: Implement page states and route**

Add the check-email state, countdown with cleanup on unmount, generic resend feedback, `email_unverified` login branch, and `VerifyEmailPage`. Preserve current validation, requested-route navigation, password-reset pages, and accessibility roles.

- [ ] **Step 7: Run frontend tests and verify GREEN**

Run: `npm test -- --run src/features/auth/api-mode.test.tsx src/features/auth/email-verification.test.tsx src/features/auth/password-reset.test.tsx src/features/auth/auth-context.test.tsx`

Working directory: `web`

Expected: PASS.

- [ ] **Step 8: Run frontend static checks**

Run: `npm run typecheck`

Run: `npm run lint`

Run: `npm run build`

Working directory: `web`

Expected: all commands exit 0 with no lint warnings.

- [ ] **Step 9: Commit**

```bash
git add web/src/types web/src/features/auth web/src/app/App.tsx
git commit -m "feat: add email verification experience"
```

### Task 6: Update Local Acceptance, Contracts, and Governing Scope

**Files:**
- Modify: `scripts/run-local-auth-acceptance.py`
- Modify: `web/e2e/live-auth-reset.spec.ts`
- Create: `web/e2e/support/auth.ts`
- Modify: `web/e2e/live-profile.spec.ts`
- Modify: `web/e2e/live-data-freshness.spec.ts`
- Modify: `README.md`
- Modify: `docs/api-contracts.md`
- Modify: `docs/security.md`
- Modify: `docs/academic-local-acceptance.md`
- Regenerate: `docs/openapi.json`
- Modify: `api/tests/unit/test_openapi_export.py` if contract assertions require it

**Interfaces:**
- Consumes: all API and UI interfaces from Tasks 1–5.
- Produces: loopback-SMTP acceptance that extracts both verification and password-reset links without external delivery.
- Produces: governing instructions that require verification while preserving local-only validation, stable PostgreSQL startup, and provider restrictions.

- [ ] **Step 1: Extend the failing local acceptance scenarios**

In `live-auth-reset.spec.ts`, register and assert the check-email state/no session, prove login returns `email_unverified`, capture the first verification link, age its database `created_at` beyond the test cooldown, resend from the UI, prove the first link is invalid, verify with the replacement link, sign in, and continue the existing password-reset/session-revocation flow. Add a second pending account, force its token `expires_at` into the past in the isolated database, and assert the verification page shows invalid/expired. Configure `EMAIL_VERIFICATION_URL` for port 5178 and a one-second acceptance-only cooldown while retaining the production default assertion in unit tests.

Create `web/e2e/support/auth.ts` with `createVerifiedTestAccount(api, label)`, implemented through a guarded Python helper that refuses any database not ending in `_test`, inserts a password-hashed verified user, and logs in through the API. Use it in `live-profile.spec.ts` and `live-data-freshness.spec.ts`, whose subjects are profile/data behavior rather than registration.

- [ ] **Step 2: Run focused live acceptance and verify RED**

Run the three commands documented in `docs/a5-local-acceptance.md`: start `scripts/run-local-auth-acceptance.py` with `E2E_DATABASE_URL` ending in `_test` and `E2E_MAILBOX_DIR`; start Vite on `127.0.0.1:5178`; then run `live-auth-reset.spec.ts` and `live-auth.spec.ts` on desktop/mobile Chrome with `E2E_LIVE=1` and API port 8005.

Expected: FAIL until the acceptance server and browser scenario use the new verification contract.

- [ ] **Step 3: Update the acceptance harness and verify GREEN**

Teach the SMTP capture/test parser to distinguish verification and reset subjects/links. Run the Step 2 flow again and require the complete browser scenario to pass.

- [ ] **Step 4: Update instructions and narrative contracts**

Update README configuration/flow text, API contracts, security model, and local acceptance documentation to match the governing scope recorded in Task 1, without adding deployment requirements or changing the provider allowlist.

- [ ] **Step 5: Regenerate and check OpenAPI**

Run: `python3 scripts/export-openapi.py --output docs/openapi.json`

Then run: `python3 -m pytest api/tests/unit/test_openapi_export.py -q`

Expected: PASS with registration `202` and the confirmation/resend routes represented.

- [ ] **Step 6: Run complete backend verification**

Run: `TEST_DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_test python3 -m pytest -q api/tests tests`

Run: `ruff check api scripts tests`

Run: `mypy --config-file api/pyproject.toml api/app`

Expected: all tests and static checks pass. Report any unrelated pre-existing failure by exact test/check name instead of hiding it.

- [ ] **Step 7: Run complete frontend verification**

Run: `npm test`

Run: `npm run typecheck`

Run: `npm run lint`

Run: `npm run build`

Working directory: `web`

Expected: all tests and static checks pass.

- [ ] **Step 8: Review provider and database boundaries**

Inspect the final diff and run the existing provider-scope regression tests. Confirm no external provider outside Gemini, OpenRouter, and Groq was added; `mock` remains test-only; normal startup still targets the root `.env` database; and test commands target only `_test` databases.

- [ ] **Step 9: Commit**

```bash
git add README.md docs api/tests/unit/test_openapi_export.py scripts/run-local-auth-acceptance.py web/e2e/support/auth.ts web/e2e/live-auth-reset.spec.ts web/e2e/live-profile.spec.ts web/e2e/live-data-freshness.spec.ts
git commit -m "docs: complete verified registration workflow"
```

### Task 7: Final Requirement and Regression Audit

**Files:**
- Review only: all files changed by Tasks 1–6

**Interfaces:**
- Consumes: the approved spec and every prior task deliverable.
- Produces: verification evidence and a concise handoff; no new feature behavior.

- [ ] **Step 1: Re-read the spec against the final diff**

Check every completion criterion, exact error code/message, time limit, local-only constraint, provider restriction, and migration-preservation rule. Add a missing regression test before fixing any uncovered behavior.

- [ ] **Step 2: Run mutation-oriented spot checks**

Confirm the suite would fail if login ignored `email_verified_at`, if raw tokens were stored, if resend left the old token valid, if migration failed to backfill existing users, or if frontend registration stored a session.

- [ ] **Step 3: Re-run the full verification commands from Task 6**

Expected: fresh clean output for backend tests/static checks, frontend tests/static checks/build, migration upgrade, OpenAPI drift, and isolated local auth acceptance.

- [ ] **Step 4: Inspect repository state**

Run: `git status --short` and `git diff --check 524efc5..HEAD`.

Expected: no uncommitted implementation changes, no whitespace errors, and only intended files in the commit range.

- [ ] **Step 5: Prepare completion report**

Report the implemented user flow, migration behavior, exact verification commands/results, and any real-account SMTP limitation. Do not claim external email delivery passed unless tested with user-provided SMTP credentials; loopback SMTP acceptance is the required local proof.
