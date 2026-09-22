# PromptVault v1 API conventions

## Transport

- JSON over HTTPS in deployed environments; local base URL is `VITE_API_BASE_URL`.
- Dates are ISO-8601 UTC strings. Clients render in the user's timezone.
- Money is a decimal string with two-to-six fractional digits; token counts are integers.
- List endpoints use `page` (1-based), `page_size` (default 25, maximum 100), and stable `sort`/`direction` parameters.
- Filters are explicit query parameters; unknown filters are rejected with HTTP 400.
- Mutating requests require `Authorization: Bearer <JWT>` and a transaction-aware service.

## Error envelope

Every non-2xx response uses:

```json
{"code":"validation_error","message":"Request is invalid","field_errors":{"email":"Invalid email"},"request_id":"req_..."}
```

`field_errors` is optional. Codes include `validation_error`, `unauthorized`, `forbidden`, `not_found`, `conflict`, `budget_exceeded`, `provider_error`, and `internal_error`.

## Core operations

| Operation | Method and path | Result |
|---|---|---|
| Register/login | `POST /auth/register`, `POST /auth/login` | User summary and JWT; login never accepts a role |
| Current user | `GET /auth/me` | Identity, role, and active status |
| Projects | `GET/POST /projects`; `GET/PATCH /projects/{id}` | Paginated projects or project; owner controls metadata |
| Members | `GET/POST/DELETE /projects/{id}/members` | Membership list and changes |
| Prompts | `GET/POST /projects/{id}/prompts`; `GET /prompts/{id}` | Prompt metadata and stable key |
| New version | `POST /prompts/{id}/versions` | New immutable version; never update an existing version |
| History/diff/lineage | `GET /prompts/{id}/versions`; `GET /versions/{id}/diff`; `GET /versions/{id}/lineage` | Snapshot list, comparison, and ordered ancestors |
| Runs | `POST /runs`; `GET /runs` | Execution result/ledger row and filtered history |
| Deployments | `POST /deployments`; `GET /deployments`; `POST /deployments/{id}/cancel` | Dev/staging activation or pending production request |
| Admin review | `GET /admin/deployments/pending`; `POST /admin/deployments/{id}/approve`; `POST /admin/deployments/{id}/reject` | Atomic review; repeated review returns 409 |
| Serve | `GET /serve/v1/prompts/{key}?env=prod` | Active version, template, variables, model config, and activation metadata |
| Budgets/costs | `GET /dashboard/me`; admin budget CRUD | Personal or organization aggregates and budget state |
| Tokens | `POST/GET/DELETE /api-tokens` | Plaintext shown once on creation; stored value is only a hash |
| Governance | `GET /admin/users`, `/admin/runs`, `/admin/audit`, `/admin/model-pricing`, `/admin/maintenance` | Super Admin-only views and controls |

## Authorization classes

Endpoints are classified as anonymous, authenticated, project-member, project-owner, or super-admin. Repositories must scope queries by the authorized subject; UI visibility is not a security boundary.
