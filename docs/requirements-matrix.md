# v1 requirements matrix (Phase 0)

| ID | Requirement | Acceptance evidence | Status |
|---|---|---|---|
| F1 | Authentication and two roles | API tests: register/login/me succeed; duplicate email, wrong password, inactive user, expired/tampered JWT, and client-supplied role fail | Verified (`api/tests/integration/test_auth.py`, `test_authorization_dependencies.py`) |
| F2 | Projects and membership | API tests: owner/member/admin permissions, atomic owner membership, duplicate/missing member, owner-removal guard, and ID-guessing denial | Verified (`api/tests/integration/test_projects_prompts_versions.py`) |
| F3 | Immutable prompt versioning | DB/API tests: every save inserts a numbered snapshot; update/delete, wrong parent, and 20 concurrent saves prove rejection/safe numbering | Verified (`test_projects_prompts_versions.py`, `tests/database/test_immutability.py`, `tests/concurrency/test_version_numbering_race.py`) |
| F4 | Diff and lineage | API tests: same-prompt diff plus recursive ordered ancestry; cross-prompt comparison and cycles fail safely | Verified (`api/tests/integration/test_projects_prompts_versions.py`) |
| F5 | Playground and run ledger | Mock/live execution records output, tokens, latency, status, request ID, and historical cost; provider failures are normalized | Verified (`api/tests/unit/test_providers_costs.py`, `api/tests/integration/test_runs_dashboard.py`) |
| F6 | Dev/staging/prod deployments | Dev/staging activate atomically; prod remains pending; user review is denied; competing reviews yield one transition | Verified (`test_deployments_tokens_serve.py`, `tests/concurrency/test_approval_race.py`) |
| F7 | Serve API | Plaintext token appears once; only hash persists; valid scoped token fetches active prompt; revoked/cross-project/no-active cases fail safely | Verified (`api/tests/integration/test_deployments_tokens_serve.py`, `api/tests/unit/test_runtime_tokens.py`) |
| F8 | Rollback | Procedure creates a new deployment referencing an older immutable version, preserves history, requires a reason, and changes Serve output | Verified (`api/tests/integration/test_deployments_tokens_serve.py`) |
| F9 | Budgets and costs | Exact-limit, zero, unlimited, overlapping user/project, month-boundary, and concurrent attempts prove database enforcement | Verified (`test_runs_dashboard.py`, `tests/database/test_budget_enforcement.py`, `tests/concurrency/test_budget_race.py`) |
| F10 | Governance | Admin-only tests cover users, encrypted keys, immutable pricing, redacted audit, analytics reconciliation, partitions, and view freshness | Verified (`api/tests/integration/test_admin_governance.py`, `tests/concurrency/test_admin_role_race.py`) |
| F11 | Security | Security suite proves Argon2, JWT checks, parameterized/scoped SQL, encryption/hashing, safe errors/logs, CORS, DCL, and dependency review | Verified (`tests/security/`, `tests/database/test_roles.py`, `api/tests/unit/test_config.py`) |
| F12 | Delivery evidence | Clean-machine run builds containers, migrates, seeds 2,000 runs, passes all suites, runs showcase queries, and completes the storyboard | Verified (`evidence/release/latest.txt`, `evidence/release/full-stack-2026-09-28.md`) |

Deferred from v1: A/B tests, semantic search, LLM-as-judge, SSO, branch UI, and RLS multi-tenancy.

The backend clean-machine transcript and Docker-backed frontend browser record together provide the full F12 evidence boundary.
