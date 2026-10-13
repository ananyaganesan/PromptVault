# PromptVault Email Verification Design

## Purpose

PromptVault must prevent a person from using an email address they do not control when creating an account. New accounts therefore remain unable to authenticate until the owner follows a one-use link delivered to that address. Registration must continue to reject an email already stored in the database with a clear account-exists response.

This design replaces the authentication-scope decision recorded on 2026-10-12 that excluded email verification. It remains limited to the local-use and demonstration scope: validation uses the local application, an isolated test database, and loopback SMTP capture. No staging environment, public domain, hosting work, or production release sign-off is required.

## Decisions

- Existing accounts are marked verified by the migration so current users retain access.
- New accounts receive no session until their email is verified.
- Verification links expire after 30 minutes.
- Resends have a 60-second account cooldown and a limit of five attempts per rolling hour for each composite of client identifier and normalized-email hash.
- A resend invalidates all older unused verification links for the account.
- Verification succeeds without creating a session; the user signs in afterward.
- Duplicate registration returns HTTP `409`, code `duplicate_email`, and the message `An account with this email already exists`.
- Resend responses do not reveal whether an account exists or is already verified.
- The existing fixed LLM-provider scope is unaffected.

## Data Model

### Users

Add a nullable `email_verified_at TIMESTAMPTZ` column to `users`.

- The migration sets `email_verified_at` to the migration time for every existing user.
- New users created through registration leave the column null.
- An account is verified only when `email_verified_at IS NOT NULL`.
- `is_active` keeps its existing administrative/account-lifecycle meaning and is not overloaded to represent verification.

Expose `email_verified_at` only where the authenticated application needs to describe the current account. Never expose verification-token data in a user response.

### Verification tokens

Create `email_verification_tokens` with:

- `id UUID PRIMARY KEY`
- `user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE`
- `token_hash CHAR(64) NOT NULL UNIQUE`
- `expires_at TIMESTAMPTZ NOT NULL`
- `used_at TIMESTAMPTZ`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`

Add a partial index supporting lookup and cleanup of unused tokens by user and expiry. Grant the application runtime role only the access required by the existing repository pattern.

The raw token is generated with a cryptographically secure random generator and appears only in the outbound email link and the confirmation request. PostgreSQL stores the SHA-256 hash produced by the existing one-time-token hashing helper.

## Configuration and Email

Add settings for:

- `EMAIL_VERIFICATION_URL`, defaulting to `http://localhost:5173/verify-email`
- `EMAIL_VERIFICATION_TTL_MINUTES`, defaulting to `30`
- `EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS`, defaulting to `60`
- `EMAIL_VERIFICATION_RESEND_LIMIT`, defaulting to `5`
- `EMAIL_VERIFICATION_RESEND_WINDOW_SECONDS`, defaulting to `3600`

Use the existing SMTP configuration and TLS behavior. Add a PromptVault-branded text and HTML verification email. The link is built by safely adding the token query parameter to `EMAIL_VERIFICATION_URL`, following the password-reset URL pattern.

Configuration validation requires a positive TTL, cooldown, limit, and window. Local defaults remain usable without a public URL. No external email is sent in automated tests.

## API Contracts

### Register

`POST /api/v1/auth/register`

The request remains `email`, `password`, and `display_name`. The service:

1. normalizes and validates the request using the existing schema rules;
2. hashes the password;
3. creates an unverified user;
4. creates a 30-minute verification token;
5. sends the verification email; and
6. returns HTTP `202 Accepted` with a small pending-verification response containing the normalized email and a user-facing message.

The response contains no access token and creates no authentication session. A case-insensitive email conflict remains HTTP `409 duplicate_email` with `An account with this email already exists`.

If SMTP is unavailable or delivery fails, return HTTP `503 email_delivery_unavailable`. The registration transaction rolls back the user and token so the same address can retry safely. The accepted tradeoff is the existing transactional-email boundary: a rare database commit failure after SMTP acceptance can produce an unusable email, which a later registration retry corrects because the account was not committed.

### Confirm verification

`POST /api/v1/auth/email-verification/confirm`

The request contains a token between 32 and 512 characters. The database operation locks the matching unused, unexpired token and user, sets `users.email_verified_at`, marks the token used, and invalidates any other unused verification tokens for that user in one transaction.

- Success: HTTP `204 No Content`.
- Malformed, unknown, expired, or previously used token: HTTP `400 invalid_verification_token` with the same public message.

Concurrent confirmations allow exactly one successful state transition. No session is created.

### Resend verification

`POST /api/v1/auth/email-verification/resend`

The request contains an email address. The public success response is always HTTP `202 Accepted` with `If this account is awaiting verification, we sent a new link.` This same response is used for an unknown email, inactive account, or already verified account.

For an active, unverified account eligible for resend, the service invalidates older unused tokens, creates a new 30-minute token, and sends it. A successfully issued token establishes the 60-second account-level cooldown.

The existing authentication rate-limit mechanism adds a resend policy of five requests per rolling hour for each composite of the existing client identifier and a stable hash of the normalized email. Requests inside the 60-second account cooldown or above the hourly limit return the existing HTTP `429 rate_limited` envelope with a retry hint. Rate-limit keys must never store the raw email.

SMTP failure for an eligible account returns HTTP `503 email_delivery_unavailable`. Because the endpoint's normal response is deliberately generic, this delivery error is acceptable for the local application and does not reveal whether the address exists beyond what the caller may infer from a delivery attempt. Token replacement and email delivery participate in the request transaction so a failed delivery preserves the prior usable token.

### Login

`POST /api/v1/auth/login` keeps the existing unknown-email/wrong-password response. After the submitted password is proven correct:

- an inactive account remains HTTP `403 inactive_user`;
- an unverified account returns HTTP `403 email_unverified` with `Verify your email before signing in`; and
- only an active, verified account receives a session.

Checking verification only after password validation avoids turning login into an email-enumeration endpoint.

## Frontend Experience

### Registration

Successful registration replaces the form with a check-email state that:

- identifies the normalized submitted address;
- explains that sign-in remains unavailable until verification;
- provides a resend action with a visible 60-second countdown; and
- links back to sign in.

The page displays the API's duplicate-email message for HTTP `409 duplicate_email`. It displays the existing delivery-unavailable error for SMTP failures and leaves the form available for retry.

### Verification page

Add `/verify-email?token=...` with three states:

- verifying while confirmation is pending;
- verified, with a button to sign in; and
- invalid or expired, with a way to return to sign in and request another email.

The page does not store the raw token beyond the current URL/request and does not create a session.

### Login and resend

When login returns `email_unverified`, show `Verify your email before signing in` and a resend control for the address currently entered in the form. A resend success always displays the generic response. Cooldown and rate-limit responses state when the user may try again without exposing internal limiter keys.

## Application and Migration Compatibility

- Update user repository projections, records, response schemas, and frontend types for verification state where needed.
- Existing seed accounts are verified explicitly or inherit the migration backfill, preserving current login tests and demonstrations.
- Account closure removes verification tokens through the user foreign key cascade and updates any explicit lifecycle cleanup assertions.
- Password reset remains separate and unchanged. Verification tokens must never be accepted by password-reset endpoints or vice versa.
- Session restoration and authorization still require the current database user. Existing sessions belong only to migrated verified users; no pending user can obtain a session.
- Update `AGENTS.md` to replace the obsolete exclusion with the approved verification rules, while preserving the local-only validation scope and stable database requirements.
- Update the API contract, security documentation, README, environment examples, and generated OpenAPI artifact as required by established project workflows.

## Testing Strategy

Implementation follows test-driven development with each behavior observed failing before production code is added.

### Database and API integration

Use an explicitly separate test database to verify:

- migration backfills every existing user as verified;
- new registrations are pending, return no session, and store only a token hash;
- registration email contains the raw one-use link and the configured expiry;
- duplicate emails are rejected case-insensitively with the required message;
- SMTP failure rolls back a new account and token;
- correct credentials cannot log into an unverified account;
- wrong credentials keep the existing generic response even for an unverified account;
- confirmation verifies the account exactly once;
- expired, malformed, unknown, and used tokens share the public invalid-token response;
- concurrent confirmation cannot perform two successful transitions;
- resend invalidates older links, respects the cooldown, and enforces five attempts per hour;
- unknown, inactive, and verified-address resends share the generic accepted response;
- eligible-account SMTP failure preserves the previous usable token; and
- login, logout, session revocation, password reset, profile, and account lifecycle regressions remain green.

### Frontend tests

Exercise real page behavior at the API boundary for:

- the registration check-email state and absence of a stored access token;
- exact duplicate-account feedback;
- resend countdown and generic success;
- unverified-login feedback and resend action;
- verification loading, success, and invalid/expired states; and
- connectivity, SMTP, and rate-limit errors.

### Local acceptance

Run the local authentication acceptance flow with loopback SMTP capture and an isolated database. The flow registers a new account, proves login is blocked, extracts the delivered verification link, verifies the account, signs in, exercises resend/expiry cases, and confirms existing migrated accounts can still sign in. Normal application startup continues to use the persistent `promptvault` database on `localhost:5432`; tests never reset or overwrite it.

## Completion Criteria

The work is complete when:

- every new account must prove control of its email before receiving a session;
- existing accounts retain access through migration backfill;
- duplicate registration reliably reports that the account already exists;
- verification and resend tokens are hashed, expiring, one-use, and correctly rate limited;
- verification, password reset, sessions, and account lifecycle remain isolated and regression-tested;
- the frontend provides complete registration, verification, resend, and error states;
- local API, frontend, database, and loopback-SMTP acceptance checks pass; and
- project instructions and documentation describe the new approved scope without adding deployment work.
