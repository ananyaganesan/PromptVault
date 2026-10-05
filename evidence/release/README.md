# Release evidence

Run `python3 scripts/verify-release.py` from the repository root to replace `latest.txt` with a redacted transcript for the current commit. A passing transcript covers container builds, startup ordering, the full backend quality suite, OpenAPI consistency, HTTP/login smoke checks, race demonstrations, and showcase SQL.

Evidence is valid only for the commit hash recorded in the transcript. Runtime tokens, JWTs, database passwords, and provider secrets must never be copied here.

The checked-in transcript verifies commit `51b8cadd5ba7758767f70b97ff165e07209257b7`, tagged locally as `v0.1.0-backend`. It is backend/container evidence only; frontend storyboard and cross-browser acceptance remain separate.
