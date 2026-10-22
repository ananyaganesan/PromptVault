# Real free-tier provider verification

Normal local startup now uses **localhost:5432/promptvault**, web **5173** and API
**8000**, matching pgAdmin. Add keys at `http://localhost:5173/admin/provider-keys`.
The older test-stack addresses below are isolated acceptance instructions.
For Gemini readiness on the persistent local database, use
`.venv/bin/python scripts/verify-real-providers.py --local-development-database --provider gemini`.
The runner reads the connection settings from the root `.env` without putting
credentials in command arguments. The API defaults to `http://localhost:8000/api/v1`. Execution adds
verification project/version/run records to the selected database; it never resets
it. Genuine calls still require confirmed free-tier keys.

Status on 2026-10-12: **not yet executed; credentials required**.

The configured application database has no provider-key rows. The current isolated
demo database (`promptvault_academic_test`, API 8005, web 5178) has no active keys
for Gemini, OpenRouter or Groq. The older browser database has one active Gemini
record that cannot be decrypted using the available local configuration. It is not
treated as a usable credential. No genuine external inference request was sent.

The readiness result is recorded in
[real-provider-check.json](../evidence/a1/real-provider-check.json).
`credential_available` is a local configuration signal, not proof of valid keys,
free account tier, remaining quota or upstream availability.

## Setup

Sign in to the local demo as its seeded admin and use
`http://127.0.0.1:5178/admin/provider-keys` to add each free-tier API key. Do not
paste keys into chat, command arguments, Git files or evidence. Gemini and Groq
keys must come from accounts configured for free access without enabled paid
usage. The provider API key itself does not prove billing-tier eligibility.

Supported routes were rechecked against official documentation:

- Gemini's [API pricing](https://ai.google.dev/gemini-api/docs/pricing) lists
  standard Gemini 3.5 Flash-Lite input/output as free on the Free Tier.
- OpenRouter's [LFM2.5 free model](https://openrouter.ai/liquid/lfm-2.5-2.6b:free)
  lists zero-priced prompt/completion tokens. The adapter additionally requires
  `:free`, sends a zero-price ceiling and disables fallback.
- Groq's [rate-limit documentation](https://console.groq.com/docs/rate-limits)
  distinguishes Free Plan and Developer Plan limits. Use a Free Plan account.

This check does not add models or broaden the fixed external-provider allowlist.

## Run

Readiness only (no external inference; sign-in/discovery/logout against local API):

```bash
.venv/bin/python scripts/verify-real-providers.py --api-url http://127.0.0.1:8005/api/v1 --database-url postgresql://promptvault@127.0.0.1:55435/promptvault_academic_test
```

Once free-tier account keys are configured and confirmed, execute one small real
request per configured provider:

```bash
.venv/bin/python scripts/verify-real-providers.py --api-url http://127.0.0.1:8005/api/v1 --database-url postgresql://promptvault@127.0.0.1:55435/promptvault_academic_test --execute --free-tier-accounts-confirmed
```

`--provider gemini`, `--provider openrouter` or `--provider groq` can select a
subset. The model comes from the reviewed application catalog. There is no
arbitrary provider/model/endpoint override. A loopback API and disposable `_test`
database are required. The default seeded user is used; `PV_VERIFY_EMAIL` and
`PV_VERIFY_PASSWORD` may select another local account without command arguments.

The verifier creates a project and immutable prompt version for each ready
provider and submits a fixed, non-sensitive connection-check prompt with at most
512 output tokens. It checks SQL/API output and usage agreement, completion,
latency, zero **application** cost, run-detail reload and an idempotent replay.
The second run request must return the original run rather than invoke inference
again. Requests are not automatically retried and unavailable providers are not
replaced by another provider or a paid model.

The report contains result identifiers, token counts, latency and an output
checksum/length. It omits credentials, response bodies, JWTs and output text.
Zero application accounting does not independently prove external account charges
are zero; that depends on the confirmed free-tier account configuration.

Exit status 0 means every selected provider was verified. Status 2 means readiness
only, a missing/unavailable provider, unsuccessful execution or local sign-in/
database mismatch. Status 1 means verification stopped on an unexpected error.
An interrupted external request remains `request_pending` in the saved report;
inspect the recorded version/reservation before attempting another request.

## Verifier validation

Four new tests passed: rejected unconfirmed execution, an excluded provider and a
non-loopback API before connecting; then a complete simulated three-provider
API/SQL/replay reconciliation. All HTTP in that test is intercepted, with exactly
three simulated provider calls. These are tests of the verifier, not evidence of
real provider success. Ruff and whitespace checks passed.

After real API verification succeeds, confirm the recorded prompt versions and
run details in the local UI. Do not mark A1 real-account acceptance complete while
the report is blocked or only simulated tests have passed.
