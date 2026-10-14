# Security model

## Application authentication

Passwords are accepted only over the register/login request models, limited to 12–128 characters, and hashed with Argon2id (`m=65536`, `t=3`, `p=4`). Public schemas and logs never contain a password hash. Login returns the same `401 unauthorized` response for an unknown email and an incorrect password.

Registration creates an active but unverified account and no session. PostgreSQL stores only the SHA-256 hash of each random verification token; confirmation is atomic, one-use, and expires after 30 minutes. Existing accounts are backfilled as verified. A correct password for a pending account returns `403 email_unverified`, while a wrong password remains indistinguishable from an unknown account. Resend replaces older links under a user-row lock, rolls back replacement if SMTP delivery fails, enforces a 60-second account cooldown, and uses a five-per-hour client plus normalized-email-hash limit whose key never contains the raw email.

Application access tokens are HS256 JWTs containing `jti`, `sub`, `role`, `iat`, `exp`, `iss`, and `aud`. Verification pins the algorithm, signing secret, issuer, and audience and distinguishes expired tokens from malformed or tampered tokens. Each `jti` maps to a server-side `auth_sessions` row, so logout takes effect immediately and a password reset atomically revokes every session for that account. Production requires a non-placeholder signing secret of at least 32 characters. Tokens are short-lived; refresh tokens are outside v1.

Browser origins are an explicit allowlist of absolute HTTP origins. Wildcards, credentials, paths, queries, and fragments are rejected; production origins must use HTTPS. Requests are capped globally by `MAX_REQUEST_BODY_BYTES` before JSON/form parsing, list pages are capped at 100 records, and unsupported query parameters fail closed. Login/registration and password-reset attempts have separate configurable per-client limits and return `429 rate_limited` plus `Retry-After`. Development/test may use the process-local store; production refuses startup without `RATE_LIMIT_REDIS_URL`, and an atomic Redis operation shares counters across API replicas.

Expired or revoked application sessions and consumed/expired password-reset tokens are retained for a bounded investigation window, then removed by scheduled maintenance. A stale paid-run reservation is never silently released: it moves to `uncertain`, remains in budget accounting, and requires reconciliation because the provider may have accepted the request before the worker disappeared.

The token role is informational, not authoritative. Every protected request validates the server-side session, loads the user by `sub`, and enforces the current database `role` and `is_active` values. Deactivation therefore invalidates access immediately, and a role change makes the old token stale so the user must authenticate again. Forging an `admin` role claim or an unregistered `jti` cannot elevate a normal database user.

## Authorization

- Missing or invalid authentication returns 401 plus `WWW-Authenticate: Bearer`.
- Inactive users return `403 inactive_user`.
- Normal users attempting an admin operation return `403 forbidden`.
- Project creation requires a current Super Admin. Ordinary users enter project
  scope only by accepting a one-use invitation delivered to their account email;
  pending invitations grant no access.
- Project deletion requires a current Super Admin in both the API and the
  security-definer database routine. The deletion is atomic and retains audit
  events while removing the project's dependent operational data.
- Project-member and project-owner dependencies query scoped relationships using parameterized SQL. Super Admin bypass is explicit in those dependencies.
- Direct prompt/version lookups apply membership scope in the SQL statement and return the same not-found response for inaccessible and unknown IDs.
- Run targets require current project membership; run detail/list access is limited to the actor's own runs, current project membership, or explicit Super Admin bypass.
- Scoped mutations lock the relevant membership row so removal cannot race between authorization and the write.
- Prompt/version direct lookups deliberately collapse unknown and inaccessible identifiers to the same `404 not_found` result, preventing object-existence probing.
- Registration rejects unknown fields, so clients cannot supply a role or active status.
- Every governance route requires the current database user to be an active Super Admin. Direct application-role updates to users are revoked; role/status changes run through a serialized database function that prevents concurrent requests from removing the final active Super Admin. An admin may change their own access when another active admin remains; the web client signs them out immediately.

## Stored and logged secrets

Development seed SQL stores fixed Argon2id hashes, never plaintext passwords. Provider secrets are encrypted with authenticated Fernet encryption under the server-only `PROVIDER_ENCRYPTION_KEY`; production requires that key to be distinct from configuration defaults. Provider-key create responses and all list responses expose metadata only. Provider-key ciphertext and runtime-token hashes have column-level protections from the read-only database role. Audit triggers remove `password_hash`, `encrypted_secret`, and `token_hash` from before/after documents. Structured request logs omit bodies and query strings.

Run ledger rows contain rendered inputs, output text, usage, latency, model identity, and historical cost but never provider credentials. Provider failures expose stable codes and generic messages; raw provider exceptions are not returned or logged.

Serve tokens are a separate credential type and are not accepted by application JWT dependencies. They contain 256 bits of random material with a recognizable `pv_live_` prefix. Plaintext is returned only by the create response; PostgreSQL stores only its SHA-256 hash and a short display prefix. Authentication rejects expired or revoked credentials, and active-prompt resolution is constrained to the token's project and requested environment. Token list/revoke operations require the project owner or a Super Admin.

Audit search is Super Admin-only and applies defensive recursive redaction before serializing historical JSON. Provider-key, budget, pricing, deployment, token, project, prompt, version, user-governance, view-refresh, and partition operations carry the request actor and request ID into database audit events. Maintenance database privileges are exposed only through active-admin-checking security-definer functions.

The `promptvault_app` role is a trusted server role, never an end-user login. Production configuration requires `DATABASE_ROLE=promptvault_app`, and every pooled API connection executes `SET ROLE promptvault_app`; the login named in `DATABASE_URL` must be granted membership but should not be a superuser or object owner. It cannot directly insert immutable versions/runs, update user credentials, or insert/update deployments; those sensitive writes use fixed-`search_path` security-definer functions. Ordinary project CRUD and the current budget/provider-key/runtime-token repositories retain direct table grants, with authorization enforced by the API transaction before DML.

## Current limitations

Password reset uses a separate random one-use token. PostgreSQL stores only its hash and expiry; confirmation consumes it through a restricted database function while updating the Argon2id password hash and revoking existing sessions. SMTP credentials are secret backend settings. The prototype has no refresh token, MFA, or SSO. Browser access tokens are stored in tab-scoped session storage and are backed by revocable database sessions. Local acceptance uses a loopback-only SMTP capture and an isolated `_test` database; external inbox delivery is not claimed.

Compose values in `.env.example` are explicit local-development placeholders. They are not production credentials, and the application rejects placeholder secrets when `ENVIRONMENT=production`. The verification evidence redacts login tokens and never prints runtime tokens or provider secrets.
