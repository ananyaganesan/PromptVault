# Authorization matrix (Phase 0)

Stored roles are `user` and `admin`; the UI label for `admin` is Super Admin. Inactive users fail every JWT-protected operation. Missing/invalid authentication returns 401; valid authentication without scope returns 403. Repositories scope queries before returning data so object-ID guessing cannot bypass membership.

| Endpoint group | Anonymous | User | Admin | Required scope |
|---|---:|---:|---:|---|
| `GET /health`, `GET /ready` | Allow | Allow | Allow | Public status; no secrets |
| `POST /api/v1/auth/register`, `/login` | Allow | Allow | Allow | Public; no role input |
| `GET /api/v1/auth/me` | Deny | Allow | Allow | Current active user |
| `GET/POST /api/v1/projects` | Deny | Allow | Allow | List scoped to memberships; creator owns project |
| `GET /api/v1/projects/{id}` | Deny | Member | Allow | Member or admin |
| `PATCH /api/v1/projects/{id}` | Deny | Owner | Allow | Owner or admin |
| Project member listing | Deny | Member | Allow | Member or admin |
| Project member add/remove | Deny | Owner | Allow | Owner/admin; owner cannot be removed |
| Project prompt list/create | Deny | Member | Allow | Member or admin |
| Prompt metadata read/update | Deny | Member | Allow | Prompt-project member or admin |
| Version create/read/history/diff/lineage | Deny | Member | Allow | Prompt-project member or admin |
| `POST /api/v1/runs` | Deny | Member | Allow | Version-project member or admin |
| User run list/detail | Deny | Permitted | Allow | Own runs or current project membership |
| Deployment create/list/detail | Deny | Member | Allow | Version-project member or admin |
| Cancel deployment | Deny | Requester | Allow | Requester plus pending status, or admin |
| Admin queue/review/rollback | Deny | Deny | Allow | Active admin only |
| User dashboard/costs | Deny | Allow | Allow | Current user's permitted records |
| API-token list/create/revoke | Deny | Owner | Allow | Project owner/admin; project-scoped token |
| `/serve/v1/prompts/{key}` | Serve token | Serve token | Serve token | Valid active token, project and environment |
| Admin dashboard/users/budgets | Deny | Deny | Allow | Active admin only |
| Admin provider keys/pricing | Deny | Deny | Allow | Active admin only |
| Admin runs/audit/maintenance | Deny | Deny | Allow | Active admin only |

## Mandatory safeguards

- Admin access to shared project capabilities is deliberate and significant writes are audited.
- An admin cannot demote or deactivate the last active admin.
- Self-demotion/deactivation is rejected when it would lock out administration.
- A project owner cannot be removed while still owning the project.
- Users cannot approve, reject, or activate production requests; only the admin procedure can transition them.
- A Serve token cannot list data or cross its project scope.
- Password hashes, signing secrets, provider secrets, token hashes, and encrypted values never enter public response schemas.
