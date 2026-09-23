# Security model

## Application authentication

Passwords are accepted only over the register/login request models. Registration requires 12–128 non-whitespace characters; login accepts 1–128 characters so a short wrong password gets the correct error. Stored passwords are hashed with Argon2id (`m=65536`, `t=3`, `p=4`). Public schemas and logs never contain a password hash. In the current development prototype, login distinguishes `401 email_not_found` from `401 invalid_password`. This reveals whether an email is registered, so review that behavior before public deployment.

Application access tokens are HS256 JWTs containing `sub`, `role`, `iat`, `exp`, `iss`, and `aud`. Verification pins the algorithm, signing secret, issuer, and audience and distinguishes expired tokens from malformed or tampered tokens. Production requires a non-placeholder signing secret of at least 32 characters. Tokens are short-lived; refresh tokens are outside v1.

The token role is informational, not authoritative. Every protected request loads the user by `sub` and enforces the current database `role` and `is_active` values. Deactivation therefore invalidates existing sessions immediately, and forging an `admin` role claim with an otherwise valid token cannot elevate a normal database user.

## Authorization

- Missing or invalid authentication returns 401 plus `WWW-Authenticate: Bearer`.
- Inactive users return `403 inactive_user`.
- Normal users attempting an admin operation return `403 forbidden`.
- Project-member and project-owner dependencies query scoped relationships using parameterized SQL. Super Admin bypass is explicit in those dependencies.
- Direct prompt/version lookups apply membership scope in the SQL statement and return the same not-found response for inaccessible and unknown IDs.
- Scoped mutations lock the relevant membership row so removal cannot race between authorization and the write.
- Registration rejects unknown fields, so clients cannot supply a role or active status.

## Stored and logged secrets

Development seed SQL stores fixed Argon2id hashes, never plaintext passwords. Provider-key ciphertext and runtime-token hashes have column-level protections from the read-only database role. Audit triggers remove `password_hash`, `encrypted_secret`, and `token_hash` from before/after documents. Structured request logs omit bodies and query strings.

Serve tokens are a separate credential type and are not accepted by application JWT dependencies. Their generation, hashing, scope, and revocation are implemented in the deployment/Serve batch.

## Password reset and email delivery

Password reset requests create a random one-time token, store only its SHA-256 hash in PostgreSQL, and send the raw token only in an SMTP email. Tokens expire after `PASSWORD_RESET_TTL_MINUTES` (30 minutes by default) and are consumed atomically when the password changes. The reset request returns the same successful response for unknown or inactive emails. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, and `SMTP_STARTTLS` in `.env` to deliver real email.

## Current limitations

The prototype has no refresh token, email verification, MFA, SSO, or distributed token-revocation list. Browser access tokens are stored in tab session storage and validated after refresh. TLS termination, rate limiting, secret rotation, and production key management belong to the deployment environment.
