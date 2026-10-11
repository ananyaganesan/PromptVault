# Data lifecycle and account closure

PromptVault's pilot policy distinguishes revocable security data from immutable business records.

| Data | Active use | Automated lifecycle |
|---|---|---|
| JWT session rows | Authentication, logout, incident response | Expired/revoked rows are removed 30 days after expiry/revocation by default |
| Password-reset tokens | One password recovery | Used or long-expired rows are removed after the same 30-day security window |
| Run idempotency reservations | Duplicate prevention and pre-call budget accounting | Completed/failed/blocked rows are removed after 30 days; uncertain paid calls are retained for reconciliation |
| Runs, prompt versions, deployments, audit events | Billing, reproducibility, approval, and security evidence | Immutable during the pilot; organization retention changes require a reviewed migration/export/archive process |
| Local production dumps | Operational restore | 14 days by default |
| Encrypted off-site backups | Disaster recovery | 14 daily, 8 weekly, and 12 monthly snapshots by default |

`GET /api/v1/auth/account/export` returns the authenticated user's current profile, owned projects, memberships, authored prompt versions, executions, deployment activity, and safe runtime-token metadata. Password hashes, session/JWT values, runtime-token hashes, and provider credentials are never exported.

`DELETE /api/v1/auth/account` requires the current password. It atomically revokes every application session and runtime token created by the user, deletes reset tokens, deactivates provider keys created by that account, replaces the login email/display name/password with non-login pseudonymous values, demotes the role, and deactivates the account. It refuses closure of the final active Super Admin. Shared project/version/deployment/run/audit records remain referentially intact; their immutable content is retained under the business-record policy above. Users must export before closing because the closed account cannot authenticate again.

Retention values are explicit production settings: `SECURITY_RETENTION_DAYS`, `IDEMPOTENCY_RETENTION_DAYS`, `BACKUP_RETENTION_DAYS`, and the restic keep counts. Shortening immutable business-record retention is not a runtime toggle because it affects billing and audit integrity.
