# Data ownership and write rules (Phase 0)

- A user owns the projects they create. Project membership grants prompt/version/run visibility; only the owner manages membership and project metadata (Super Admin may administer all projects).
- Projects and prompts use lowercase hyphenated keys matching `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`, limited to 63 characters. Prompts belong to exactly one project and their key is unique within that project. Prompt versions belong to exactly one prompt and are immutable after insertion.
- Saving a prompt always inserts a new version with creator, commit message, variables, model configuration, timestamp, and parent pointer.
- Dev/staging deployment activation is atomic. Production deployment creation always starts `pending`; only a Super Admin can approve or reject it.
- Rollback never rewrites history: it inserts a new deployment referencing an existing immutable version and requires a reason.
- Runs are append-only ledger records. Provider secrets are encrypted and never returned; Serve tokens are shown in plaintext only once and stored as hashes.
- Each Serve token belongs to exactly one project, resolving prompt-key collisions without placing a project identifier in the runtime URL.
- User and project budgets are independent limits. A run is admitted only when every applicable budget passes; the database is the final enforcement point.
- Significant writes set the acting user in transaction-local context so audit triggers can attribute changes.
