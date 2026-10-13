# Project invitation local acceptance

Verified 2026-10-13. The member-add API and UI now send a seven-day invitation to
an existing active user. No membership or project visibility is granted until the
recipient signs in to the invited account and explicitly accepts the email link.
Existing project members and automatic owner membership are preserved.

Owners/admins can inspect and cancel pending invitations. Duplicate pending
invitations return a conflict; expired ones can be replaced. Tokens are random,
stored only as SHA-256 hashes and omitted from API/audit responses. The email URL
uses a fragment so its token does not enter HTTP access logs. A failed SMTP send
rolls back the invitation. Acceptance consumes the invitation and creates membership
atomically; cancellation competes on the same invitation row.

Validation:

- 501 backend tests passed on the combined isolated test database, including eight
  invitation checks for no pre-acceptance access, wrong account, expiry/cancellation,
  inactive accounts, SMTP failure and concurrent acceptance/cancellation.
- 164 frontend tests passed; frontend lint, typecheck and build passed.
- Backend Ruff and strict mypy passed; OpenAPI regenerated; whitespace checks passed.
- Six desktop/mobile browser cases passed on `promptvault_invitation_browser_test`:
  SMTP delivery to local capture, invitation redirect through login, explicit
  acceptance, replay rejection, project/prompt workflows, refresh and member removal.
- The dictionary/catalog evidence now includes migration 025, 19 logical tables
  and 163 columns. Applied migrations were not edited.

The local SMTP test harness captured email without sending to external inboxes.
External inbox delivery for this new message has not been separately verified.
Normal startup uses `.venv/bin/python scripts/start-local.py` and the persistent
`localhost:5432/promptvault` database with web/API on 5173/8000. Migration 025 was
applied there through that launcher; no accounts or memberships were reset.

Configuration: `PROJECT_INVITATION_URL` defaults to
`http://localhost:5173/project-invitations`; existing password-reset SMTP settings
also deliver project invitations. Email verification remains required for newly
registered accounts; accepting an invitation does not replace that gate. Provider scope remains
Gemini, OpenRouter and Groq.
