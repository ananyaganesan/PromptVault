# A4 local self-profile acceptance

Date: 2026-10-12. Changes remain uncommitted on top of `89b86b5`.

- `PATCH /api/v1/auth/me` changes only the authenticated user's display name.
  Requests cannot supply another user ID, role, email, password or account status.
  Validation trims names, rejects blanks and caps them at 120 characters.
- Migration `023_self_profile.sql` adds a narrow SECURITY DEFINER function,
  with PUBLIC execution revoked and execution granted to `promptvault_app`.
  It checks the active user and matching unrevoked/unexpired session under locks;
  broad direct users-table UPDATE remains revoked. No columns or tables change.
  Audit attribution/redaction uses the existing users audit trigger.
- The Profile form handles pending/saved/error states, preserves a failed draft,
  refreshes shared auth context and navigation identity, and persists after reload.
  A response from an old session cannot overwrite auth context after logout/login.
- API/security checks cover persistence, unrelated-account isolation, rejected
  protected fields, name validation, anonymous/logged-out denial, and successful
  restricted-role updates while direct role escalation stays denied.
- Two frontend tests verify shared identity refresh and failed-draft preservation.
- Two desktop/mobile live browser checks passed against the normal local API and
  isolated SQL database, verifying save, matching SQL identity/security fields and
  reload persistence. They create separate accounts rather than altering demo users.

Only the disposable local test databases were migrated. Existing migration files
and the original application database were not modified or reset. The migration
upgrade tests retain their data-preservation checks and now expect 23 migrations.
Final verification: **439 backend tests passed**, zero skipped, **90.38% coverage**;
**152 frontend tests passed**; backend/frontend lint, types, build and OpenAPI checks
passed. Provider browser acceptance covers six desktop/mobile cases; profile covers
two. The older freshness suite's nine passing cases and one successful artifact-safe
rerun preserve all ten existing local checks.
