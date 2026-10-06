# Full-stack release evidence — 2026-09-28

Branch: `Jobin`

## Packaged stack

- `docker compose up -d --build --wait` completed with healthy database, API, and web services.
- The reset path applied 14 checksum-tracked migrations and 2 deterministic seed files before each browser-project run.
- API startup was refreshed after each reset to replace invalidated pooled database connections.

## Frontend static and unit checks

- `npm run lint --prefix web` — pass.
- `npm run typecheck --prefix web` — pass.
- `npm test --prefix web -- --run` — 12 files, 31 tests passed.
- `npm run build --prefix web` — pass; 66 modules transformed.

## Docker-backed browser acceptance

Each project started from a fresh deterministic reset and used one worker because governance and budget cases intentionally mutate shared state.

| Playwright project | Live tests | Legacy mock-only tests | Result |
|---|---:|---:|---|
| Desktop Chrome | 9 | 12 skipped | Pass |
| Mobile Chrome (iPhone 13 viewport) | 9 | 12 skipped | Pass |
| Desktop Firefox | 9 | 12 skipped | Pass |

The live tests cover registration/login/session restoration/logout, forbidden-route recovery, project create/edit/member persistence, prompt v1→v3 and real diff/lineage, run output/tokens/latency/cost, history and costs, database budget rejection, staging/production approval, one-time runtime tokens, Serve, rollback, revocation, governance, maintenance, responsive layout, document overflow, and serious/critical axe-core checks.

`npm run screenshots --prefix web` also passed in desktop and mobile Chrome and refreshed eight committed live-stack screenshots.

## Backend/database verification

`docker compose --profile verification run --rm verify` completed successfully:

- Ruff: pass.
- Strict mypy: pass across 73 source files.
- Pytest: 280 passed, 6 skipped.
- Coverage: 90.34%, above the required 85% threshold.
- Dependency check: no broken requirements.
- OpenAPI export/drift check: pass.
- Showcase queries: cost analytics, deployment history, query plans, and version lineage executed.

The backend clean-machine transcript remains archived in `evidence/release/latest.txt`; this record adds the connected frontend and cross-browser acceptance boundary.
