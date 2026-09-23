# Testing strategy

Run all checks from the repository root. Database tests require an isolated PostgreSQL database through `TEST_DATABASE_URL`; fixtures apply migrations and development seeds before tests execute.

```bash
export TEST_DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_test
ruff check api scripts tests
mypy --config-file api/pyproject.toml api/app
pytest -q --cov=api.app --cov-config=api/pyproject.toml --cov-report=term-missing
```

## Run and budget coverage

- `api/tests/unit/test_providers_costs.py` proves deterministic provider output/usage, bounded timeout normalization, exact-variable rendering, and decimal cost rounding.
- `api/tests/integration/test_runs_dashboard.py` exercises real HTTP routes and PostgreSQL persistence for completed, failed, blocked, filtered, scoped, and aggregated run behavior, including membership removal during provider I/O and a single-connection pool-pressure check.
- `tests/database/test_budget_enforcement.py` proves zero, unlimited, exact, overlapping user/project, UTC month-boundary, and DST wall-time behavior at the database function boundary.
- `tests/concurrency/test_budget_race.py` submits 20 simultaneous charges against one budget and reconciles admitted, blocked, and stored totals.

Failure-path API tests verify that provider errors and budget rejection return a safe public envelope while the corresponding append-only ledger row commits. Unknown or inaccessible run identifiers have the same not-found behavior. Generated OpenAPI is compared byte-for-byte with `docs/openapi.json` so frontend contract drift fails CI.
