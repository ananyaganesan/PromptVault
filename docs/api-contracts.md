# PromptVault v1 API contract

This document is the shared frontend/backend contract. Application paths below are relative to `/api/v1`. Operational and Serve paths are written in full.

The currently implemented FastAPI surface is exported deterministically to `docs/openapi.json`. Frontend types and clients should be generated from that file; regenerate it with `python3 scripts/export-openapi.py` whenever response models or routes change. This narrative contract includes planned endpoints until their implementation reaches the OpenAPI artifact.

Runnable login, deployment approval, runtime-token, and Serve requests are in `docs/api-examples.md`.

## Transport and representation

- JSON over HTTPS in deployed environments.
- UUIDs are lower-case canonical strings; properties use `snake_case`.
- Dates are ISO-8601 UTC strings such as `2026-09-23T10:30:00Z`.
- Money is a decimal string with two-to-six fractional digits, never a JSON float.
- Unknown JSON fields and unsupported query filters are rejected.
- Request bodies are capped by `MAX_REQUEST_BODY_BYTES` (1 MiB by default); larger bodies return `413 request_too_large`.

## Authentication

Application endpoints accept `Authorization: Bearer <JWT>`. The short-lived JWT contains `sub`, `role`, `iat`, and `exp`; every protected request also loads the current database user so role changes and deactivation apply immediately.

Serve endpoints accept `Authorization: Bearer <serve-token>`. Serve tokens are not JWTs and are scoped to one project.

## Request IDs and errors

Clients may send `X-Request-ID` using 1-128 visible ASCII characters; otherwise the API creates one. Every response returns it and every non-2xx JSON body uses:

```json
{
  "code": "validation_error",
  "message": "Request is invalid",
  "field_errors": {"email": ["Enter a valid email address"]},
  "request_id": "req_01K..."
}
```

`field_errors` is `null` for non-field errors. Stable codes include `bad_request`, `invalid_filter`, `invalid_variables`, `request_too_large`, `unauthorized`, `invalid_token`, `token_expired`, `forbidden`, `inactive_user`, `not_found`, `no_active_deployment`, `conflict`, `invalid_state`, `invalid_rollback_target`, `duplicate_email`, `duplicate_key`, `already_reviewed`, `last_admin`, `validation_error`, `rate_limited`, `budget_exceeded`, `pricing_not_configured`, `provider_error`, `provider_timeout`, `not_ready`, `missing_partition`, and `internal_error`.

Database constraint names, SQL text, stack traces, hashes, and encrypted values never appear in a response.

## Pagination

Lists accept `page` (default `1`), `page_size` (default `25`, maximum `100`), and endpoint-specific `sort` plus `direction=asc|desc` values. All list responses use:

```json
{"items": [], "page": 1, "page_size": 25, "total": 0}
```

Stable ordering includes an ID tie-breaker. Invalid paging, sorting, or filters return `400 invalid_filter`.

## Shared representations

### User

```json
{
  "id": "uuid",
  "email": "alex@example.com",
  "display_name": "Alex Morgan",
  "role": "user",
  "is_active": true,
  "created_at": "2026-09-23T10:30:00Z"
}
```

`role` is `user` or `admin`; the UI displays `admin` as Super Admin.

### Project

```json
{
  "id": "uuid",
  "name": "Checkout Assistant",
  "key": "checkout-assistant",
  "description": "Checkout support prompts",
  "owner": {"id": "uuid", "display_name": "Alex Morgan"},
  "member_count": 4,
  "prompt_count": 8,
  "created_at": "2026-09-23T10:30:00Z",
  "updated_at": "2026-09-23T10:30:00Z"
}
```

Project and prompt keys match `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$` and contain at most 63 characters.

### Prompt version

```json
{
  "id": "uuid",
  "prompt_id": "uuid",
  "version_number": 3,
  "parent_version_id": "uuid",
  "template_body": "Reply to {{customer_message}}",
  "variables": ["customer_message"],
  "model_config": {
    "provider": "mock",
    "model": "deterministic-v1",
    "temperature": 0,
    "max_output_tokens": 500
  },
  "commit_message": "Improve response instructions",
  "created_by": {"id": "uuid", "display_name": "Alex Morgan"},
  "created_at": "2026-09-23T10:30:00Z"
}
```

The first version has `parent_version_id: null`. Clients never send `version_number` or `variables`; server/database logic derives them.

### Run

```json
{
  "id": "uuid",
  "version_id": "uuid",
  "status": "completed",
  "provider": "mock",
  "model": "deterministic-v1",
  "output_text": "Rendered provider output",
  "prompt_tokens": 42,
  "completion_tokens": 18,
  "latency_ms": 25,
  "cost": "0.000120",
  "error_code": null,
  "created_at": "2026-09-23T10:30:00Z"
}
```

Run status is `completed`, `failed`, or `blocked`. Lists may truncate output; detail returns the stored value.

### Deployment

```json
{
  "id": "uuid",
  "prompt_id": "uuid",
  "version_id": "uuid",
  "environment": "prod",
  "status": "pending",
  "request_note": "Validated in staging",
  "review_note": null,
  "requested_by": {"id": "uuid", "display_name": "Alex Morgan"},
  "reviewed_by": null,
  "requested_at": "2026-09-23T10:30:00Z",
  "reviewed_at": null,
  "activated_at": null
}
```

Environments are `dev`, `staging`, and `prod`. Statuses are `pending`, `active`, `rejected`, `cancelled`, `superseded`, and `rolled_back`.

## Operational endpoints

| Method and path | Authorization | Success |
|---|---|---|
| `GET /health` | Public | `200 {"status":"ok"}` when the process answers |
| `GET /ready` | Public | `200 {"status":"ready","database":"ok"}` after a DB round trip; otherwise `503` |

## Authentication endpoints

| Method and path | Request | Success |
|---|---|---|
| `POST /auth/register` | `email`, `password`, `display_name` | `201` with `access_token`, `token_type`, `expires_in`, and `user` |
| `POST /auth/login` | `email`, `password` | `200` with the same session shape |
| `POST /auth/password-reset` | `email` | `202`; sends a one-use link for an active account when SMTP is configured |
| `POST /auth/password-reset/confirm` | `token`, `password` | `204`; consumes the token and changes the password |
| `GET /auth/me` | None | `200` User |

Passwords contain 12-128 characters. Register/login never accept a role. Email comparison is case-insensitive and normalized.
Password-reset requests return `503 email_delivery_unavailable` when SMTP is not configured or delivery fails. Confirmation returns `400 invalid_reset_token` for an expired or used link.

## Project and member endpoints

| Method and path | Request/query | Success |
|---|---|---|
| `GET /projects` | `search`, paging, `sort=name|created_at|updated_at` | `200` membership-scoped Project page |
| `POST /projects` | `name`, `key`, `description?` | `201` Project; creator becomes owner/member atomically |
| `GET /projects/{project_id}` | None | `200` Project detail |
| `PATCH /projects/{project_id}` | Any of `name`, `description` | `200` Project; owner/admin only |
| `GET /projects/{project_id}/members` | Paging | `200` User page with `is_owner` |
| `POST /projects/{project_id}/members` | `email` | `201` member; owner/admin only |
| `DELETE /projects/{project_id}/members/{user_id}` | None | `204`; owner cannot be removed |

## Prompt and version endpoints

| Method and path | Request/query | Success |
|---|---|---|
| `GET /projects/{project_id}/prompts` | `search`, paging, `sort=key|name|updated_at` | `200` prompt-summary page |
| `POST /projects/{project_id}/prompts` | `key`, `name`, `description?`, `template_body`, `model_config`, `commit_message` | `201` prompt with initial version |
| `GET /prompts/{prompt_id}` | None | `200` metadata, latest version, active environment versions |
| `PATCH /prompts/{prompt_id}` | `name?`, `description?` | `200`; never changes key or versions |
| `POST /prompts/{prompt_id}/versions` | `parent_version_id`, `template_body`, `model_config`, `commit_message` | `201` Prompt version |
| `GET /prompts/{prompt_id}/versions` | Paging, `sort=version_number|created_at` | `200` version page |
| `GET /versions/{version_id}` | None | `200` Prompt version |
| `GET /versions/{version_id}/diff?against={other_id}` | Same-prompt comparison ID | `200` structured template/variable/config changes |
| `GET /versions/{version_id}/lineage` | None | `200 {"items":[...],"cycle_detected":false}` current-to-root |

Variable names match `^[A-Za-z_][A-Za-z0-9_]*$`. Duplicate placeholders appear once in first-seen order. New versions require a parent from the same prompt.

## Run endpoints

| Method and path | Request/query | Success |
|---|---|---|
| `POST /runs` | `version_id`, `variables` object | `201` Run; budget rejection is `409 budget_exceeded` and records a blocked ledger row |
| `GET /runs` | Literal prompt-key/run-ID search, project/prompt/version/status/model/date filters, and paging | `200` permitted run page; filtering occurs before pagination |
| `GET /runs/{run_id}` | None | `200` Run detail |

Variable keys must exactly match the version. Provider timeouts are bounded and normalized; provider output is untrusted text.

## Deployment endpoints

| Method and path | Request/query | Success |
|---|---|---|
| `POST /deployments` | `version_id`, `environment`, `request_note?` | `201` active dev/staging or pending prod deployment |
| `GET /deployments` | Project/prompt/environment/status filters and paging | `200` permitted deployment page |
| `GET /deployments/{deployment_id}` | None | `200` detail and timeline |
| `POST /deployments/{deployment_id}/cancel` | None | `200` cancelled; requester and pending only |
| `GET /admin/deployments/pending` | Filters and paging | `200` pending production queue |
| `GET /admin/deployments/{deployment_id}` | None | `200` review detail with active/requested versions and evidence |
| `POST /admin/deployments/{deployment_id}/approve` | `review_note?` | `200` active Deployment |
| `POST /admin/deployments/{deployment_id}/reject` | Required `review_note` | `200` rejected Deployment |
| `POST /admin/prompts/{prompt_id}/rollback` | `target_version_id`, `reason` | `201` active rollback deployment |

Production requests always start pending. Repeated/competing reviews return `409 already_reviewed`.

## Serve tokens and runtime

| Method and path | Request/query | Success |
|---|---|---|
| `GET /api-tokens` | Paging | `200` metadata; never plaintext/hash |
| `POST /api-tokens` | `project_id`, `name`, `expires_at?` | `201` metadata plus `token` plaintext once |
| `DELETE /api-tokens/{token_id}` | None | `204` revocation |
| `GET /serve/v1/prompts/{key}?env=prod` | Serve bearer token | `200` active prompt payload |

Serve returns project ID, prompt key, environment, version, template, variables, model configuration, and activation time. It includes an identity-based `ETag` and `Cache-Control: private, max-age=30`.

## Dashboard and governance endpoints

| Method and path | Request/query | Success |
|---|---|---|
| `GET /dashboard/me` | Optional month `YYYY-MM` | `200` personal counts, spend, budgets, trend, recent runs, freshness/timezone |
| `GET /admin/dashboard` | Optional month | `200` organization metrics, trends, spenders, models, errors, blocked runs |
| `GET /admin/users` | Search/role/status/paging | `200` user page |
| `PATCH /admin/users/{user_id}` | `role?`, `is_active?` | `200` User with last-admin/self-lockout guards |
| `GET/POST /admin/budgets` | Filters or scope, one target, monthly limit, timezone | List or `201` budget |
| `PATCH/DELETE /admin/budgets/{budget_id}` | Update or none | `200` budget or `204` |
| `GET/POST /admin/provider-keys` | List or provider, alias, secret | Metadata list or `201`; no existing plaintext |
| `DELETE /admin/provider-keys/{key_id}` | None | `204` |
| `GET/POST /admin/model-pricing` | List or effective-dated prices | History or `201` immutable price row |
| `GET /admin/runs` | User/project/prompt/model/status/date filters | Organization run page |
| `GET /admin/audit` | Actor/action/entity/date filters | Redacted audit page |
| `GET /admin/maintenance` | None | View/partition/provider/job status without secrets |
| `POST /admin/maintenance/refresh-views` | None | `202` refresh result/job |
| `POST /admin/maintenance/create-next-partition` | None | `200` idempotent result |

Budgets require exactly one target. Prices are append-only; corrections create a new effective-dated row. Admin run/audit date filters require timezone offsets. Maintenance operations execute synchronously in v1, report their last completed status, and write attributed audit events.

## Universal acceptance rules

Every endpoint requires Pydantic validation, stable OpenAPI documentation, correct authorization, parameterized SQL, bounded paging where applicable, safe errors, and tests for success, validation, anonymous, forbidden, missing, conflict, and database failure. Mutating operations prove complete rollback on failure.
