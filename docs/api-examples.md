# API examples

These examples target the local API at `http://localhost:8000`. Start PromptVault
from the repository root with:

```bash
.venv/bin/python scripts/start-local.py
```

The launcher reuses the persistent `promptvault` database on `localhost:5432`,
checks migration history, and starts the web app on `http://localhost:5173`.
Swagger is available at `http://localhost:8000/docs`.

The commands below require `curl` and `jq`. Use an existing verified and approved
project-owner account for the complete workflow. New accounts must complete email
verification and administrator approval before login. Keep passwords, JWTs, Gemini
keys, and runtime tokens out of source control and shell transcripts.

## Authenticate and inspect the current user

Set credentials in the current shell without adding them to a repository file:

```bash
export PROMPTVAULT_API=http://localhost:8000
read -r -p 'PromptVault email: ' PROMPTVAULT_EMAIL
read -r -s -p 'PromptVault password: ' PROMPTVAULT_PASSWORD; echo

PROMPTVAULT_JWT=$(curl --fail --silent --show-error \
  "$PROMPTVAULT_API/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg email "$PROMPTVAULT_EMAIL" \
    --arg password "$PROMPTVAULT_PASSWORD" \
    '{email: $email, password: $password}')" | jq -r '.access_token')

curl --fail --silent --show-error \
  "$PROMPTVAULT_API/api/v1/auth/me" \
  -H "Authorization: Bearer $PROMPTVAULT_JWT" | jq
```

Unset the password after login:

```bash
unset PROMPTVAULT_PASSWORD
```

## Discover the Gemini catalog

Gemini is the only selectable external provider. Discovery reports the reviewed
models, free-tier limits, and whether an active project credential is available;
it never returns the encrypted key.

```bash
curl --fail --silent --show-error \
  "$PROMPTVAULT_API/api/v1/providers/models" \
  -H "Authorization: Bearer $PROMPTVAULT_JWT" | jq
```

Removed providers and runtime-selectable mock adapters are rejected for all new
versions and executions. Automated tests simulate Gemini HTTP through test doubles,
not through a selectable application provider.

## Find a project, prompt, and immutable version

When the optional development seeds have deliberately been applied, the local demo
contains the Checkout Assistant workflow. Normal startup never seeds or resets the
database. If the fixture is absent, replace the searches below with an existing
project and prompt whose variables you know. These commands resolve IDs from API
responses instead of relying on hard-coded UUIDs:

```bash
PROJECT_ID=$(curl --fail --silent --show-error --get \
  "$PROMPTVAULT_API/api/v1/projects" \
  -H "Authorization: Bearer $PROMPTVAULT_JWT" \
  --data-urlencode 'search=Checkout Assistant' \
  --data-urlencode 'page_size=10' | jq -r '.items[0].id')

PROMPT_ID=$(curl --fail --silent --show-error --get \
  "$PROMPTVAULT_API/api/v1/projects/$PROJECT_ID/prompts" \
  -H "Authorization: Bearer $PROMPTVAULT_JWT" \
  --data-urlencode 'search=Checkout support reply' \
  --data-urlencode 'page_size=10' | jq -r '.items[0].id')

VERSION_ID=$(curl --fail --silent --show-error \
  "$PROMPTVAULT_API/api/v1/prompts/$PROMPT_ID/versions?page_size=10&direction=desc" \
  -H "Authorization: Bearer $PROMPTVAULT_JWT" | jq -r '.items[0].id')

curl --fail --silent --show-error \
  "$PROMPTVAULT_API/api/v1/versions/$VERSION_ID" \
  -H "Authorization: Bearer $PROMPTVAULT_JWT" | jq
```

The selected version is an immutable snapshot. Editing a prompt creates a new
version rather than changing this record.

## Validate and request a release

Every deployment requires a passing validation report for the exact version and
environment. This example defaults to development; set `RELEASE_ENV=prod` before
running it to create a production approval request instead. The case variables
must match the selected version's template variables.

```bash
VALIDATION_REQUEST_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
RELEASE_ENV=${RELEASE_ENV:-dev}

VALIDATION_ID=$(curl --fail --silent --show-error \
  "$PROMPTVAULT_API/api/v1/deployments/validations" \
  -H "Authorization: Bearer $PROMPTVAULT_JWT" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg id "$VALIDATION_REQUEST_ID" \
    --arg version "$VERSION_ID" \
    --arg environment "$RELEASE_ENV" \
    '{
      id: $id,
      version_id: $version,
      environment: $environment,
      suite: {
        goal: "Give a helpful next step for the checkout problem.",
        cases: [{
          name: "Checkout failure",
          variables: {
            customer_message: "Checkout failed. What should I try next?",
            order_id: "ORD-1001"
          },
          reference: "Retry checkout for order ORD-1001 and contact support if it still fails."
        }],
        requirements: {valid_json: false, required_fields: [], max_words: 100},
        weights: {
          correctness: 30,
          relevance: 25,
          instruction_following: 20,
          completeness: 15,
          clarity: 10
        }
      }
    }')" | jq -r '.id')

for _attempt in {1..60}; do
  VALIDATION=$(curl --fail --silent --show-error \
    "$PROMPTVAULT_API/api/v1/deployments/validations/$VALIDATION_ID" \
    -H "Authorization: Bearer $PROMPTVAULT_JWT")
  STATUS=$(jq -r '.status' <<<"$VALIDATION")
  [[ "$STATUS" == queued || "$STATUS" == running ]] || break
  sleep 2
done

jq '{id, status, summary, minimum_score, checks}' <<<"$VALIDATION"
if [[ "$STATUS" == queued || "$STATUS" == running ]]; then
  echo "Validation did not finish within 120 seconds" >&2
  exit 1
fi
test "$STATUS" = passed

DEPLOYMENT_ID=$(curl --fail --silent --show-error \
  "$PROMPTVAULT_API/api/v1/deployments" \
  -H "Authorization: Bearer $PROMPTVAULT_JWT" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg version "$VERSION_ID" \
    --arg validation "$VALIDATION_ID" \
    --arg environment "$RELEASE_ENV" \
    '{
      version_id: $version,
      validation_id: $validation,
      environment: $environment,
      request_note: "Validated local API example"
    }')" | jq -r '.id')
```

Development and staging releases activate after validation. With `RELEASE_ENV=prod`,
the request remains pending until an administrator explicitly approves or rejects
it. Approve that production request with the administrator endpoint:

```bash
curl --fail --silent --show-error -X POST \
  "$PROMPTVAULT_API/api/v1/admin/deployments/$DEPLOYMENT_ID/approve" \
  -H "Authorization: Bearer $PROMPTVAULT_ADMIN_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"review_note":"Reviewed for the local demonstration"}' | jq
```

`PROMPTVAULT_ADMIN_JWT` must belong to an administrator. Do not reuse a regular
user token for this step.

## Issue a runtime token and retrieve the active prompt

Only a project owner can issue a project-scoped runtime token. Its plaintext value
is returned once; the database stores only its hash.

```bash
umask 077
curl --fail --silent --show-error \
  "$PROMPTVAULT_API/api/v1/api-tokens" \
  -H "Authorization: Bearer $PROMPTVAULT_JWT" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg project "$PROJECT_ID" \
    '{project_id: $project, name: "Local API example"}')" \
  | jq -r '"PROMPTVAULT_SERVE_TOKEN=" + .token' \
  > /tmp/promptvault-serve-token.env

.venv/bin/python scripts/serve-client.py \
  --token-file /tmp/promptvault-serve-token.env \
  --key support-reply \
  --env dev
```

Revoke the token from the API Tokens page or with `DELETE /api/v1/api-tokens/{id}`
when the example is finished. Never include the token file in screenshots, evidence,
Git commits, or bug reports.
