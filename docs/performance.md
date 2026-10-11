# Performance validation

PromptVault validates query shape against a deterministic representative ledger instead of relying on an empty development database. The loader creates a selective target project plus background traffic and 2,000 completed runs in the current monthly partition:

```bash
python3 scripts/simulate-traffic.py --runs 2000
```

The command is idempotent for the requested size and runs `ANALYZE runs`. `tests/performance/test_query_plans.py` inspects the optimizer's normal plans and proves that project, user, prompt, and version history queries select index-backed scans without disabling sequential scans. The bounded history queries include the current-month date range and assert PostgreSQL prunes every unrelated partition.

The run ledger indexes follow the API's primary access paths: `(user_id, created_at)`, `(project_id, created_at)`, `(prompt_id, created_at)`, `(version_id, created_at)`, status/time, and provider/model/time. Administration adds indexes for user-list filtering, provider-key history, and recently updated budgets. List endpoints cap `page_size` at 100, and repositories add stable ID tie-breakers.

`python3 scripts/run-showcase.py` discovers stable demo IDs, safely renders the parameterized SQL in `db/showcase/`, and executes cost, deployment, lineage, and `EXPLAIN (ANALYZE, BUFFERS)` examples. It fails when no seeded version exists or a query/placeholder drifts from the schema.

## Operational expectations

- Create the next monthly partition before month rollover with `python3 scripts/create-partition.py`.
- Refresh reporting views with `python3 scripts/refresh-views.py`; API maintenance actions require an active Super Admin and are audited.
- Re-run representative plan tests after changing filters, ordering, joins, indexes, partitions, or PostgreSQL versions.
- The reference capacity dataset is 2,000 partitioned run rows. It validates the pilot query/index shape, not a universal production latency SLO.
- API requests are limited to 1 MiB by default, templates to 100,000 characters, list pages to 100 rows, and model output configuration to 1,000,000 tokens. Paid execution is additionally bounded to four concurrent calls per user by default and by atomic user/project budgets.
- Concurrency tests cover 12 simultaneous budget reservations plus membership, version, approval, rollback, and final-admin races. Re-run them against the intended PostgreSQL instance size before raising pool or execution limits.
- Live-provider throughput and quota are controlled by Gemini and the deployed network. Measure them in staging with non-production budgets and credentials; do not infer paid-provider capacity from deterministic mock timings.
