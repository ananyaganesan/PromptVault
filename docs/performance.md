# Performance validation

PromptVault validates query shape against a deterministic representative ledger instead of relying on an empty development database. The loader creates a selective target project plus background traffic and 2,000 completed runs in the current monthly partition:

```bash
python3 scripts/simulate-traffic.py --runs 2000
```

The command is idempotent for the requested size and runs `ANALYZE runs`. `tests/performance/test_query_plans.py` inspects the optimizer's normal plans and proves that project, user, prompt, and version history queries select index-backed scans without disabling sequential scans. The bounded history queries include the current-month date range and assert PostgreSQL prunes every unrelated partition.

The run ledger indexes follow the API's primary access paths: `(user_id, created_at)`, `(project_id, created_at)`, `(prompt_id, created_at)`, `(version_id, created_at)`, status/time, and provider/model/time. Administration adds indexes for user-list filtering, provider-key history, and recently updated budgets. List endpoints cap `page_size` at 100, and repositories add stable ID tie-breakers.

## Operational expectations

- Create the next monthly partition before month rollover with `python3 scripts/create-partition.py`.
- Refresh reporting views with `python3 scripts/refresh-views.py`; API maintenance actions require an active Super Admin and are audited.
- Re-run representative plan tests after changing filters, ordering, joins, indexes, partitions, or PostgreSQL versions.
- This prototype records correctness-focused plan evidence, not a production latency SLO. Load, connection-pool, and provider-capacity testing remain deployment-specific.
