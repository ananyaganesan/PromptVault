# Release evidence

Run `python3 scripts/verify-release.py` from the repository root to replace `latest.txt` with a redacted transcript for the current commit. A passing transcript covers container builds, startup ordering, the full backend quality suite, OpenAPI consistency, HTTP/login smoke checks, race demonstrations, and showcase SQL.

Evidence is valid only for the commit hash recorded in the transcript. Runtime tokens, JWTs, database passwords, and provider secrets must never be copied here.

The checked-in transcript verifies commit `1ac5ed8ca8789003a8b3110d30c5f13c535950cb`. It covers the API, PostgreSQL, production-target frontend build, packaged stack, HTTP smoke boundary, concurrency demonstrations, representative traffic, showcase queries, and an isolated dump/restore drill. Connected cross-browser acceptance remains separately recorded in `docs/browser-smoke.md`.

Known acceptance limits: real SMTP and Gemini delivery are not exercised without deployment credentials; Playwright WebKit does not certify physical macOS/iOS Safari; physical devices, screen readers, and manual accessibility review remain human checks; and DNS, off-site encrypted backup scheduling, Alertmanager/log routing, and cloud secret rotation require the target infrastructure.
