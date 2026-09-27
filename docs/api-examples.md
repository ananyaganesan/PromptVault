# API examples

Start the stack with `docker compose up -d --build --wait`. The examples use the development-only seeded accounts and require `jq` for shell value extraction.

```bash
PROMPTVAULT_USER_JWT=$(curl --fail --silent http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@promptvault.dev","password":"UserDemo2026!"}' | jq -r .access_token)

curl --fail --silent http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer ${PROMPTVAULT_USER_JWT}"
```

Request production deployment of the stable seeded version, approve it as the seeded Super Admin, create a project-scoped runtime token, and fetch the active prompt:

```bash
PROMPTVAULT_DEPLOYMENT_ID=$(curl --fail --silent http://localhost:8000/api/v1/deployments \
  -H "Authorization: Bearer ${PROMPTVAULT_USER_JWT}" \
  -H 'Content-Type: application/json' \
  -d @examples/production-deployment/deployment-request.json | jq -r .id)

PROMPTVAULT_ADMIN_JWT=$(curl --fail --silent http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@promptvault.dev","password":"AdminDemo2026!"}' | jq -r .access_token)

curl --fail --silent -X POST \
  "http://localhost:8000/api/v1/admin/deployments/${PROMPTVAULT_DEPLOYMENT_ID}/approve" \
  -H "Authorization: Bearer ${PROMPTVAULT_ADMIN_JWT}" \
  -H 'Content-Type: application/json' \
  -d '{"review_note":"Approved for the local demo"}'

PROMPTVAULT_SERVE_TOKEN=$(curl --fail --silent http://localhost:8000/api/v1/api-tokens \
  -H "Authorization: Bearer ${PROMPTVAULT_USER_JWT}" \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"33333333-3333-4333-8333-333333333333","name":"Local demo"}' | jq -r .token)

python3 scripts/serve-client.py \
  --token "${PROMPTVAULT_SERVE_TOKEN}" \
  --key support-reply \
  --env prod
```

The runtime token is returned once. The API stores only its SHA-256 hash; do not place the plaintext token in source control, screenshots, or release evidence. Rerunning the deployment request creates another pending event, so approve or cancel it before repeating the flow.
