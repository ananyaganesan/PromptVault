# Fixed LLM provider scope

The user has fixed this project's external LLM providers to **Gemini, OpenRouter,
and Groq** for the entire project and demonstration. Do not add DeepSeek, OpenAI,
Anthropic, or any other external provider, including fallback execution paths.
Do not broaden this allowlist through configuration, discovery or future work.

Use verified free-access API/model configurations only. Payments, purchased
credits, subscriptions and automatic fallback to paid models are outside scope.

`mock` is an internal deterministic adapter for local development and automated
tests, not an external LLM provider. It must remain unavailable in production.

Preserve provider validation in API writes and execution, the fixed UI options,
and regression tests proving excluded providers and production mock are rejected.
OpenRouter and Groq adapters are implemented and verified with simulated provider
HTTP. Do not claim real account execution has passed until it is tested with free-tier keys. Provider/model discovery must stay within the fixed external scope.

# Local project scope

The user clarified on 2026-10-12 that this project is for local use and demonstration,
not deployment or production. Do not require a staging URL, public domain, hosting,
production infrastructure or hosted release sign-off. Validate features using the
local application and isolated test databases. Historical production checklist items
must not block completion or create new deployment work. Preserve application-level
security, provider restrictions, data integrity and meaningful local tests.

# Authentication scope

The user excluded email verification on 2026-10-12. Do not implement verification
tokens, verification/resend endpoints, verification emails or verification UI, and
do not gate registration or login on verified email. Historical A3 checklist items
are out of scope. Preserve existing authentication, session revocation and password
reset behavior; verify those flows locally.

# Stable local database connection

Normal local app startup must reuse the existing PostgreSQL server on
localhost:5432, matching pgAdmin, with the persistent `promptvault` database from
the root `.env`. Use `.venv/bin/python scripts/start-local.py` (web 5173, API 8000).
Never move the normal app to a randomly chosen database port or disposable test
database. Keep test/simulator databases explicitly separate. Preserve existing
data and migration checksum checks; do not reset or overwrite accounts at startup.
