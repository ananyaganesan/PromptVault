# Phase 0 risk register

| Risk | Impact | Mitigation / owner |
|---|---|---|
| Provider outage or quota | Runs fail or demo stalls | Deterministic mock adapter is mandatory; provider errors are normalized / Backend |
| Lost or leaked secrets | Account/provider compromise | Argon2, JWT expiry, encrypted provider keys, hashed Serve tokens, redacted logs / Security |
| Concurrent version saves or approvals | Duplicate numbers or multiple production actives | Database locks, unique/partial indexes, atomic procedures, race tests / SQL |
| Missing monthly run partition | Ledger insert fails at rollover | Idempotent next-partition job and maintenance check / Operations |
| Budget race or overspend | Governance failure | Lock budget rows and enforce admission in PostgreSQL / SQL |
| Dashboard staleness | Misleading cost/governance data | Show `refreshed_at`, reconcile aggregates to runs, controlled materialized-view refresh / Analytics |
| Authorization bypass | Cross-project or admin data exposure | Endpoint matrix, scoped repositories, 401/403 tests, backend checks / Backend |
| Clean-machine setup failure | Submission/demo blocked | Docker Compose, explicit migration/seed commands, CI, clean-machine rehearsal / Delivery |
