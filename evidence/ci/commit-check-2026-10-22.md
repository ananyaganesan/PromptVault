# CI checks for the three reported commits

Checked on 2026-10-22 using isolated `git archive` snapshots. The working tree and persistent application database were not used for test writes. Database tests used uniquely named disposable databases ending in `_test`, removed after their run.

Hosted GitHub Actions status could not be retrieved: `gh` is signed out, the unauthenticated GitHub API is rate-limited, and the public Actions pages are unavailable. The results below are local reproductions of the repository workflow commands, not a claim about the current hosted badges.

Local environment: Python 3.12.4, Node 24.14.1, PostgreSQL 18.4. The workflow uses Python 3.11, Node 22 and PostgreSQL 16. Installed dependency lock files match all three snapshots. Backend tests for the older commits were repeated with `PGOPTIONS=-c timezone=UTC`, matching the CI database's default timezone. A timestamp string assertion otherwise fails on this local server's +04:00 timezone despite representing the same instant.

| Check | `3abf0b2` | `45d4606` | `4be8ebd` |
|---|---|---|---|
| Backend Ruff | Pass | Pass | Pass |
| Backend mypy | Pass | Pass | Pass |
| Frontend ESLint | Pass | Pass | Pass |
| Frontend TypeScript | Pass | Pass | Pass |
| Frontend Vitest | 169 passed | 1 failed, 156 passed | 1 failed, 154 passed |
| Frontend build | Pass | Pass | Pass |
| Generated OpenAPI matches committed file | Fail | Pass | Pass |

## Merge commit `3abf0b2aee2ef65fc912a3741e5ec2e02531890e`

Backend test run: **76 failed, 432 passed** on the local database environment.

Most failures start with ordinary-user project creation returning HTTP 403. The commit changes project creation to require an administrator, but integration, concurrency, end-to-end and security fixture setup still expects ordinary users to create projects. Fix fixture preparation to use the administrator flow and explicitly establish intended membership/ownership for the scenario; preserve the actual admin-only policy and forbidden-response tests.

Additional confirmed stale assertions:

- `tests/database/test_schema_migrations.py::test_complete_migration_chain_is_discoverable` expects versions 1–24; the commit contains versions 1–28.
- `test_email_verification_is_hashed_expiring_and_atomic` reads migration 024, which contains project invitations. Email verification moved to 025.
- `tests/database/test_migration_upgrade.py` still expects 24 fresh migrations and a legacy-upgrade result ending at 024.
- `tests/delivery/test_academic_evidence.py` expects 18 logical tables; email verification makes the count 19.
- `docs/openapi.json` omits `DELETE /api/v1/projects/{project_id}`. Exporting the contract adds this operation and makes the workflow diff fail.

## Commit `45d460613efe1e2d3fa4a5ebe30b9939ff3c8ee4`

Frontend failure: `src/features/playground/playground-page.test.tsx`, test “records a successful run and updates spend”, line 31. It waits for `View run details →`, which the rendered Playground no longer contains. The output does show a completed run. Update the assertion to the intended successful-run behavior, or restore the link if that navigation is a product requirement. The later merge snapshot already uses the completed-status assertion and passes this test.

Backend with UTC: **464 passed**, coverage **90.19%**.

## Commit `4be8ebd4bc99a51f2671728296438ed1411aaa84`

The frontend has the same obsolete `View run details →` assertion at the same test/line as `45d4606`.

Backend with UTC: **462 passed**, coverage **90.17%**.

## Scope

This check does not rerun or alter GitHub workflows, rewrite commits, send email, execute external LLM calls or change the live demonstration records. The frontend builds and backend/frontend static checks pass across all three commits, but each snapshot has a reproducible failing test or contract check, so none is a clean local reproduction of the complete CI workflow.
