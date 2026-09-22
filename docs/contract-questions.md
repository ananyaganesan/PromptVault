# Contract decision log

Use this file to prevent silent frontend/backend contract drift. Proposed changes are recorded before modifying `api-contracts.md`, `route-map.md`, or `authorization-matrix.md`.

| Date | Decision | Reason | Status |
|---|---|---|---|
| 2026-09-23 | Application endpoints use `/api/v1`; health uses `/health` and `/ready`; Serve remains `/serve/v1`. | Separates operational and consumer APIs from the versioned application API. | Accepted for v1 |
| 2026-09-23 | JWTs are short-lived bearer tokens held in frontend memory; no refresh token in v1. | Keeps the course implementation small while avoiding persistent browser token storage. | Accepted for v1 |
| 2026-09-23 | Project ownership grants metadata/member management; membership grants prompt, version, run, and deployment access. | Provides one deterministic authorization rule across UI and API. | Accepted for v1 |
| 2026-09-23 | Serve tokens are scoped to exactly one project; prompt keys are unique only inside a project. | Prevents collisions without exposing project identifiers in the Serve URL. | Accepted for v1 |
| 2026-09-23 | List responses use `{items,page,page_size,total}` and default to 25 items with a maximum of 100. | Gives the frontend one stable pagination model. | Accepted for v1 |
| 2026-09-23 | Money is serialized as a decimal string, never a JSON floating-point number. | Prevents rounding drift between PostgreSQL, Python, and JavaScript. | Accepted for v1 |

When a change is needed, add a row with status `Proposed`, name the affected fields/routes, and notify both owners. Change the shared contract only after agreement, then mark the row `Accepted` or `Rejected`.
