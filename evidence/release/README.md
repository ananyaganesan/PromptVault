# Release evidence

Run `python3 scripts/verify-release.py` from the repository root to replace `latest.txt` with a redacted transcript for the current commit. A passing transcript covers container builds, startup ordering, the full backend quality suite, OpenAPI consistency, HTTP/login smoke checks, race demonstrations, and showcase SQL.

Evidence is valid only for the commit hash recorded in the transcript. Runtime tokens, JWTs, database passwords, and provider secrets must never be copied here.
