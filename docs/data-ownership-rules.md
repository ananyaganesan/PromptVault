# Data ownership and write rules (Phase 0)

- A user owns the projects they create. Project membership grants prompt/version/run visibility; only the owner manages membership and project metadata (Super Admin may administer all projects).
- Prompts belong to exactly one project and are identified by a key unique within that project. Prompt versions belong to exactly one prompt and are immutable after insertion.
- Saving a prompt always inserts a new version with creator, commit message, variables, model configuration, timestamp, and parent pointer.
- Dev/staging deployment activation is atomic. Production deployment creation always starts `pending`; only a Super Admin can approve or reject it.
- Rollback never rewrites history: it inserts a new deployment referencing an existing immutable version and requires a reason.
- Runs are append-only ledger records. Provider secrets are encrypted and never returned; Serve tokens are shown in plaintext only once and stored as hashes.
- User and project budgets are independent limits. A run is admitted only when every applicable budget passes; the database is the final enforcement point.
- Significant writes set the acting user in transaction-local context so audit triggers can attribute changes.
