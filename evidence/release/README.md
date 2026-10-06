# Release evidence

Run `python3 scripts/verify-release.py` from the repository root to replace `latest.txt` with a redacted transcript for the current commit. A passing transcript covers container builds, startup ordering, the full backend quality suite, OpenAPI consistency, HTTP/login smoke checks, race demonstrations, and showcase SQL.

Evidence is valid only for the commit hash recorded in the transcript. Runtime tokens, JWTs, database passwords, and provider secrets must never be copied here.

The checked-in transcript verifies commit `5039a6c8e9fad0a3bfdae490f6bc44b3b7f64898`. It covers the API, PostgreSQL, production-target frontend build, packaged stack, HTTP smoke boundary, and an isolated dump/restore drill. Connected cross-browser acceptance remains separately recorded in `docs/browser-smoke.md`.

Known acceptance limits: SMTP delivery is not exercised without deployment credentials; the mock provider is deterministic and does not certify an external LLM; browser automation does not cover Safari/WebKit, physical devices, screen readers, or manual accessibility review; and local process rate limiting does not replace a distributed production edge limiter.
