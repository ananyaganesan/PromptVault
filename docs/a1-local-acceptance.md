# A1 local provider execution and Playground acceptance

Real-account follow-up: see [real provider verification](real-provider-verification.md)
for the safe API/SQL runner and latest credential-readiness result. Actual inference
remains blocked until usable free-tier keys are added to the current local demo.

Date: 2026-10-12. Base revision: `89b86b5`; changes are in the uncommitted working tree.
No staging URL or deployment is required. The fixed external scope is Gemini,
OpenRouter and Groq. Mock remains internal to local development/tests.

## Implemented behavior

- Gemini REST and OpenRouter/Groq chat-completions execution through shared,
  admin-managed encrypted project keys. There is no provider/model fallback.
- Authenticated `GET /api/v1/providers/models` returns a small reviewed free-tier
  text catalog, safe credential availability, model availability/reasons, application
  input/output caps, timeout and concurrency limits. It returns no secret, ciphertext,
  key ID or alias. It is a supported-model catalog, not a promise that an upstream
  model is currently healthy or that a stored key is valid.
- OpenRouter requests use free model IDs, a zero prompt/completion/request price
  ceiling and disabled fallback. Gemini/Groq account keys must be from free-tier
  accounts: these APIs do not expose billing-tier verification through the key.
  A paid account key can still incur provider billing; the application never upgrades
  accounts or buys credits. Only the reviewed models can be saved or executed.
- External runs have zero recorded monetary cost without requiring pricing setup.
  Nonzero effective database pricing blocks execution before reservation/HTTP.
  Token usage, latency, outputs, immutable model configuration and errors persist.
- Output and rendered-input caps are checked before calls. Quota rejection is 429
  `provider_quota_exceeded`; rejected credentials are 503
  `provider_configuration_error`, with failed zero-cost ledger rows. Timeout and
  uncertain outcomes retain the no-replay reservation behavior.
- Playground provider/model/temperature/output edits must be saved as a new immutable
  version before Run is enabled. The original version is unchanged; the selected new version is stored in the URL so configuration survives reload. Discovery must
  finish before selecting a provider; missing keys/paid configuration disable Run.
  Provider refresh is explicit. New Prompt also offers the supported model catalog.
- Local endpoint settings cannot redirect Gemini to another external provider;
  loopback endpoints are permitted only for automated tests. OpenRouter and Groq
  endpoints are fixed in their adapter.

## Verified locally

- Full backend suite: **427 passed**, no skipped tests, **90.44% coverage**.
  Subsequent endpoint-policy checks: **37 passed** (configuration and chat adapters).
- Frontend: **150 unit tests passed**; lint, types and build passed. Backend Ruff,
  strict mypy and generated OpenAPI comparison passed.
- New API/SQL tests simulate each provider's HTTP and prove output/usage persistence,
  zero cost without price setup, idempotency, safe discovery, quota/auth errors,
  missing/revoked keys, input limits and unsupported-model denial.
- Provider browser acceptance: **6 passed**, desktop and mobile, with actual local
  UI/API/PostgreSQL and simulated outbound HTTP. SQL matches run provider/output/
  tokens/cost and immutable version lineage; reload preserves results. Groq quota
  rejection is verified in the UI. A final desktop Groq check also passed after
  adjusting the explanatory text's styling.
- The browser run found a selection-before-discovery race; provider selection now
  waits for the catalog. The full suite found a pre-existing admin-race assertion
  that assumed only 401. The test now verifies exactly one successful mutation,
  one precise allowed revocation/authorization denial and one remaining active admin.
  Application authorization behavior was not loosened.

The [Playground screenshot](../evidence/a1/playground-groq.png) was inspected for
layout. [Source fingerprints](../evidence/a1/source-fingerprints.json) identify the
implementation. The A2 local freshness regression also passes: nine cases passed in the full run,
and the mobile >100-record case passed on rerun with a separate artifact directory.
Its first failure was trace-file deletion by another concurrent Playwright process,
not a failed application assertion. The rerun took 29.2 seconds. Use separate
`--output` directories for simultaneous browser runs.

## Reproduce the simulated browser journey

Use a separate disposable PostgreSQL database ending in `_test`, with migrations
and development seeds applied. The simulator rejects all outbound async HTTP except
simulated requests to the three fixed provider hosts. No genuine LLM call is made.
Do not run this browser suite against an ordinary API: it stores dummy credentials.

```sh
E2E_DATABASE_URL=postgresql://promptvault@127.0.0.1:55435/promptvault_a1_browser_test \
  .venv/bin/python scripts/run-provider-simulation.py
```

In another terminal:

```sh
VITE_API_BASE_URL=http://127.0.0.1:8004 VITE_API_URL=http://127.0.0.1:8004 \
VITE_USE_DEMO_DATA=false npm --prefix web run dev -- --host 127.0.0.1 --port 5177
```

Then:

```sh
E2E_LIVE=1 E2E_PROVIDER_SIMULATION=1 E2E_BASE_URL=http://127.0.0.1:5177 \
E2E_API_BASE_URL=http://127.0.0.1:8004/api/v1 \
E2E_DATABASE_URL=postgresql://promptvault@127.0.0.1:55435/promptvault_a1_browser_test \
  npm --prefix web run test:e2e -- e2e/live-provider-execution.spec.ts \
  --project=desktop-chrome --project=mobile-chrome \
  --output=/private/tmp/promptvault-a1-provider-results
```

The normal local API/frontend remain at ports 8003/5176 and use their separate
`promptvault_integration_browser_test` database. The backend reset fixtures use
`promptvault_integration_test`; never share that database with browser fixtures.

## Real-account acceptance boundary

Implementation and simulated local acceptance are complete. Real Gemini/OpenRouter/
Groq account responses have **not** been verified: real free-tier project keys have
not been confirmed. Add those keys through Admin → Provider keys on the normal local
app, then select a catalog model, save configuration, run and inspect persisted details.
No SMTP, public domain, paid subscription or hosted setup is needed for A1.

Catalog references reviewed on 2026-10-12:
[Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing),
[Groq free-plan limits](https://console.groq.com/docs/rate-limits),
[Groq models](https://console.groq.com/docs/models),
[OpenRouter catalog](https://openrouter.ai/api/v1/models), and
[OpenRouter zero-price routing](https://openrouter.ai/docs/guides/routing/provider-selection#max-price).
The application caps (4096 output tokens and 12000 prompt characters) are conservative
project limits, not published per-account quotas. Review catalog model availability
when provider models change; the three-provider scope must remain fixed.
