# PromptVault v1 route map

This is the Phase 0 contract for the web application. Paths are frontend routes; the API paths are listed separately in `api-contracts.md`.

| Area | Route | Access | Page responsibility |
|---|---|---|---|
| Public | `/login` | Anonymous | Sign in; preserve requested destination |
| Public | `/register` | Anonymous | Create account |
| Public | `/403`, `/404` | Any | Safe authorization/not-found recovery |
| User | `/dashboard` | Authenticated | Personal project, prompt, spend, and pending-approval summary |
| User | `/projects`, `/projects/new`, `/projects/:id` | Member/owner | List, create/edit, members, and project prompt library |
| User | `/prompts/new`, `/prompts/:id` | Project member | Create prompt and save immutable versions |
| User | `/versions/:id`, `/versions/:id/compare`, `/versions/:id/lineage` | Project member | Inspect snapshot, diff, and parent lineage |
| User | `/playground` | Project member | Render variables and execute a version |
| User | `/runs` | Authenticated | Filter and inspect own permitted run ledger |
| User | `/deployments/new`, `/deployments` | Project member | Request dev/staging/prod deployment and cancel own pending request |
| User | `/costs` | Authenticated | Personal spend, budgets, utilization, and trends |
| User | `/api-tokens`, `/profile` | Authenticated | Manage Serve tokens and account details |
| Admin | `/admin` | Super Admin | Organization dashboard |
| Admin | `/admin/approvals`, `/admin/approvals/:id` | Super Admin | Review, approve, or reject production requests |
| Admin | `/admin/rollback` | Super Admin | Create an auditable rollback to an immutable version |
| Admin | `/admin/users` | Super Admin | Manage users, roles, and active status |
| Admin | `/admin/provider-keys` | Super Admin | Add/list/deactivate provider key metadata; never expose plaintext |
| Admin | `/admin/budgets` | Super Admin | Manage user/project budget limits |
| Admin | `/admin/runs` | Super Admin | Organization-wide run explorer |
| Admin | `/admin/audit` | Super Admin | Read-only audit log with filters |
| Admin | `/admin/model-pricing` | Super Admin | Add and inspect effective-dated model prices |
| Admin | `/admin/maintenance` | Super Admin | Health, view refresh, and partition status |
| External | `GET /serve/v1/prompts/{key}?env={env}` | Valid Serve token | Runtime fetch of the active prompt |

Navigation must hide admin links for normal users, but backend authorization remains authoritative.
