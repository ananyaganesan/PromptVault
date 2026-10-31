# Fixed LLM provider scope

The user narrowed this project to **Gemini only** on 2026-10-23, including local
development and demonstrations. Do not add any other provider, fallback adapter,
or selectable mock provider in any environment. Use verified free-access Gemini
configuration only; payments and automatic fallback to paid models are outside scope.

Preserve immutable historical provider metadata, but reject removed providers in
all new writes, executions and activations. Existing historical versions can be
read and explicitly saved as new Gemini versions. Automated tests may simulate
Gemini HTTP or inject test doubles under tests/; those are not application adapters
and must not be selectable or enabled by runtime configuration.

# Local project scope

The user clarified on 2026-10-12 that this project is for local use and demonstration,
not deployment or production. Do not require a staging URL, public domain, hosting,
production infrastructure or hosted release sign-off. Validate features using the
local application and isolated test databases. Historical production checklist items
must not block completion or create new deployment work. Preserve application-level
security, provider restrictions, data integrity and meaningful local tests.

# Authentication scope

The user approved email verification on 2026-10-13. Preserve existing accounts by
marking them verified during migration. New accounts must verify a hashed, one-use
email link before login; links expire after 30 minutes. Resends use a 60-second
account cooldown and a maximum of five attempts per rolling hour for each client
and normalized-email hash, invalidate older links, and return generic responses
that do not reveal account state. Duplicate registration must clearly report that
the account already exists. Preserve existing authentication, session revocation
and password-reset behavior, and validate every flow locally with isolated test
databases and loopback SMTP capture.

# Stable Supabase database connection

Normal local app startup must use the Supabase session pooler for project
`ehnufhcdgxllubnpjfuc` at
`aws-0-eu-west-1.pooler.supabase.com:5432/postgres`, configured in the root `.env`
with `sslmode=require`. Use `.venv/bin/python scripts/start-local.py` (web 5173,
API 8000). Do not use the transaction pooler on port 6543, another Supabase
project, a randomly chosen database port, or a disposable test database for normal
startup. Keep test/simulator databases explicitly separate. Preserve existing data
and migration checksum checks; do not reset or overwrite accounts at startup.
