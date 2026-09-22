# Authorization matrix (Phase 0)

| Capability | Anonymous | User | Super Admin | Scope |
|---|---:|---:|---:|---|
| Register/login/health | Allow | Allow | Allow | Public |
| Read own dashboard, costs, profile, tokens | Deny | Allow | Allow | Current user |
| Create project | Deny | Allow | Allow | Current user becomes owner |
| Read/edit project metadata | Deny | Member/read; owner/write | Allow | Project membership |
| Manage project members | Deny | Owner only | Allow | Project |
| Create prompt/version; diff/lineage | Deny | Project member | Allow | Project |
| Run playground / read runs | Deny | Permitted project runs | Allow | User/project membership |
| Create deployment / cancel own pending | Deny | Project member | Allow | Project; production remains pending |
| Approve/reject production | Deny | Deny | Allow | Organization |
| Rollback production | Deny | Deny | Allow | Organization/project |
| Provider keys, budgets, pricing, maintenance | Deny | Deny | Allow | Organization |
| Organization runs and audit | Deny | Deny | Allow | Organization |
| Serve API | Deny | Token-scoped | Token-scoped | Token + project + environment |

Rules: inactive users are denied; every protected endpoint returns 401 without valid authentication and 403 when authenticated but outside its role/scope; object IDs must not bypass membership checks.
