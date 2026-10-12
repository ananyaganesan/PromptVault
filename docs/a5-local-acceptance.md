# A5 local authentication and password-reset acceptance

Accepted locally on 2026-10-12. Email verification is excluded. Registration
immediately creates a usable session; no verified-email gate was added.

## Result

Existing application behavior passed without authentication code changes:

- Registration and login restore the session after browser reload.
- A real SMTP conversation delivers a reset email into a loopback-only capture
  mailbox. Its link opens the local reset page. No external email is sent.
- SQL confirms that only the SHA-256 reset-token hash is persisted and the token
  becomes consumed after a successful reset.
- Reusing the current password fails without consuming the link; a new password
  succeeds. Reusing the consumed link fails.
- Password reset revokes both the registration session and a second login session.
  The browser recovers to login when its old session is rejected.
- The old password fails login; the replacement works and survives reload.
- Logout returns 204 and the server subsequently rejects that session.
- Missing reset links show the invalid-link page; non-admin routes remain restricted.

Validation: 50 backend authentication, authorization, schema, rate-limit and email
tests passed. These include expired reset links, unknown-account non-disclosure,
password history, concurrent reset behavior, expired/tampered sessions and account
deactivation. All 22 frontend authentication tests passed, including expired-session
recovery. Eight live browser cases passed across desktop and mobile Chrome. After
refining the hash-only SQL assertion, both reset journeys passed again. Frontend
lint/types, the new script's Ruff check and `git diff --check` passed.

## Repeat locally

Use an already migrated and seeded disposable database whose name ends in `_test`.
The following example uses the isolated browser database, not the backend test
database that pytest resets. Run each long-lived command in its own terminal.

```bash
export E2E_DATABASE_URL=postgresql://promptvault@127.0.0.1:55435/promptvault_integration_browser_test
export E2E_MAILBOX_DIR=/private/tmp/promptvault-auth-mailbox
.venv/bin/python scripts/run-local-auth-acceptance.py
```

```bash
cd web
VITE_API_BASE_URL=http://127.0.0.1:8005 VITE_API_URL=http://127.0.0.1:8005 VITE_USE_DEMO_DATA=false npm run dev -- --host 127.0.0.1 --port 5178
```

```bash
cd web
E2E_LIVE=1 E2E_BASE_URL=http://127.0.0.1:5178 E2E_API_BASE_URL=http://127.0.0.1:8005/api/v1 E2E_DATABASE_URL=postgresql://promptvault@127.0.0.1:55435/promptvault_integration_browser_test E2E_MAILBOX_DIR=/private/tmp/promptvault-auth-mailbox npx playwright test e2e/live-auth-reset.spec.ts e2e/live-auth.spec.ts --project=desktop-chrome --project=mobile-chrome --output=/private/tmp/promptvault-a5-browser-results
```

The harness binds API port 8005 and SMTP port 1026 to 127.0.0.1. It uses test-only
settings and a separate session-signing key; it does not alter `.env` or the other
local API's SMTP settings. The mailbox contains test reset links in owner-only JSON
files under an owner-only directory. To try reset manually, use the URL in the
captured message's `text` field. Keep mailbox files out of Git/evidence artifacts.
Stop the harness with Ctrl-C and remove its disposable mailbox when finished.

This proves local capture delivery, not delivery to a real external inbox. No
staging, public-domain URL, email verification or external SMTP account is required.
Academic database evidence and the full local product demonstration are next.

## Installed PostgreSQL and real Gmail SMTP follow-up

Normal startup now uses localhost:5432/promptvault and the web app on 5173.
The installed Python had no default CA certificates, so Gmail STARTTLS failed
with `SSLCertVerificationError`. SMTP now augments the system/custom trust store
with the maintained certifi bundle, preserving certificate and hostname checks.
Gmail TLS verification and authentication succeeded (235) with the configured
sender; no external message was sent during that diagnostic.

Both STARTTLS and implicit TLS are covered by empty-trust-store regression tests.
The email/auth suite passed 27 tests. Registration sends no verification email;
password-reset mail is sent only for a registered active account. At diagnosis,
the user's email had no account in the persistent database, so its reset
request could not produce mail. The public reset response deliberately does not
reveal account existence.

Follow-up: the user's existing account was located in the Docker preview database
published on host port 55432. It was absent from the installed PostgreSQL server
on 5432. The account and password history were copied transactionally to the
persistent database, preserving identity, original password hash, role and active
status. No account fields were overwritten and the source database was unchanged.
The account had no owned projects, memberships, authored versions, runs or keys to
transfer. New reset requests now target this registered account on the fixed server.
The retry returned 202 and its valid, unused reset token was confirmed in the
persistent database. Gmail accepted the submission; inbox receipt awaits the user.
