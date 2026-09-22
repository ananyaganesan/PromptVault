# v1 requirements matrix (Phase 0)

| ID | Requirement | Acceptance evidence | Status |
|---|---|---|---|
| F1 | Authentication and two roles | Register/login/current-user; no client role selector | Planned |
| F2 | Projects and membership | Owner/member permissions and duplicate-member errors | Planned |
| F3 | Immutable prompt versioning | Every save creates a numbered snapshot with parent and commit | Planned |
| F4 | Diff and lineage | Side-by-side diff and recursive ancestor view | Planned |
| F5 | Playground and run ledger | Mock/live provider result with tokens, latency, status, and cost | Planned |
| F6 | Dev/staging/prod deployments | Prod requests require Super Admin review | Planned |
| F7 | Serve API | Hashed token fetches active prompt by project-scoped key/environment | Planned |
| F8 | Rollback | Creates a new deployment pointing to an earlier immutable version | Planned |
| F9 | Budgets and costs | User/project limits block runs at database boundary | Planned |
| F10 | Governance | Users, keys, pricing, audit, maintenance, organization analytics | Planned |
| F11 | Security | Argon2, JWT, encryption, token hashing, least privilege, redaction | Planned |
| F12 | Delivery evidence | Tests, ERD/3NF report, queries, Docker, demo and viva materials | Planned |

Deferred from v1: A/B tests, semantic search, LLM-as-judge, SSO, branch UI, and RLS multi-tenancy.
