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

## 2026-10-12 provider scope clarification

- **Accepted product scope (user instruction):** Gemini, OpenRouter and Groq only for external LLM execution; free access only, with no payments or
  subscriptions. Mock remains an internal development/test provider.
- **Pending A1 contract:** credential ownership, discovery fields, model allowlists,
  verified free-access eligibility, per-provider quotas and normalized errors.
- **Final provider scope (2026-10-12 user instruction):** DeepSeek is excluded.
  Gemini, OpenRouter and Groq are the fixed external allowlist throughout the
  project and demonstration; no extra provider or fallback can be introduced.
  Mock is internal to local development/tests and is blocked in production.
- This records scope; the allowlist is enforced in request validation and execution. OpenRouter
  and Groq adapters are still pending; recording credentials does not enable execution.

## A1 local execution/discovery contract (2026-10-12)

Use the existing admin-managed encrypted project keys (shared credentials). Add
`GET /api/v1/providers/models` for authenticated users: exactly three providers,
reviewed free-access models, credential availability, model limits, availability
reasons, account quota guidance, timeout and concurrency limits. No keys, aliases,
ciphertext or secrets are returned. `POST /runs` continues to execute an immutable
version; Playground configuration changes create a version through the existing
version API. External runs record zero cost and need no pricing setup; a nonzero
stored model price is rejected before admission. Unsupported models are denied.
OpenRouter sends a zero-price ceiling and disables fallback. Gemini/Groq keys must
come from free-tier accounts; their API keys do not expose billing-tier metadata.
Quota/auth rejection uses 429 `provider_quota_exceeded` or 503
`provider_configuration_error`; timeouts/uncertain calls retain no-replay behavior.

## A4 self-profile contract (2026-10-12)

`PATCH /api/v1/auth/me` accepts only `display_name` (trimmed, nonblank, at most
120 characters) and returns the existing safe User representation. The target user
comes from authentication, never the body/path/query. Role/email/password/status
fields are forbidden. A narrowly scoped database function checks the active user
and the specific unrevoked/unexpired session under locks before updating only the
existing `users.display_name`; broad direct UPDATE permission stays revoked.
The UI refreshes auth context only if the same session is still current.
