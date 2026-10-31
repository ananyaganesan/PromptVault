# Shareable PromptVault demo on Vercel

The root `vercel.json` runs the Vite frontend and FastAPI backend as two Vercel Services on one origin. The frontend uses the same origin for `/api/v1` in production. React deep links are routed back to `index.html`. The normal local launcher and its persistent `localhost:5432/promptvault` database are unchanged.

## External resources

A shareable deployment needs a separate, reachable PostgreSQL database and Redis instance. Vercel's Postgres Marketplace currently connects an external provider such as Neon; Vercel does not supply a new built-in Postgres database. Do not point the deployment at the local `promptvault` database or upload the root `.env`.

For a fresh demo database, apply the ordered, checksummed `db/migrations/*.sql` files with `api.app.db.migrations.migrate_database` using a migration-capable connection. Provision the `promptvault_app` role expected by the migrations. Run schema changes before deploying; do not migrate on every serverless cold start. Do not run `db/seeds` against a public deployment because those files include known demonstration credentials. Create a unique, verified and approved initial Super Admin through a secure bootstrap process before inviting users.

## Vercel environment variables

Set these on the Vercel project for the target deployment environment; no values belong in source control:

- `ENVIRONMENT=production`
- `DATABASE_URL`: hosted PostgreSQL connection string (prefer a pooled runtime connection).
- `DATABASE_ROLE=promptvault_app`
- `RATE_LIMIT_REDIS_URL`: hosted Redis connection string.
- `SECRET_KEY`: new random secret, at least 32 characters, different from local.
- `PROVIDER_ENCRYPTION_KEY`: another new random secret, at least 32 characters, different from `SECRET_KEY` and local.
- `CORS_ORIGINS`: `https://<your-vercel-domain>`.
- `EMAIL_VERIFICATION_URL`: `https://<your-vercel-domain>/verify-email`.
- `PASSWORD_RESET_URL`: `https://<your-vercel-domain>/reset-password`.
- `PROJECT_INVITATION_URL`: `https://<your-vercel-domain>/project-invitations`.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM_EMAIL`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS`/`SMTP_SSL`: a mail account authorized for this hosted demo. Email registration and password reset require working SMTP.
- `DB_POOL_MIN_SIZE=0`, `DB_POOL_MAX_SIZE=2`: reduce per-instance connections for serverless scaling.
- `VITE_USE_DEMO_DATA=false`.

The frontend build should leave `VITE_API_BASE_URL` unset to use the same Vercel origin. Vercel's SPA rewrite and API rewrite were checked locally with `vercel dev --local`: `/login` returned 200, `/health` returned 200, and `/api/v1/auth/me` returned the expected 401 without a session.

Before sharing the URL, check a new account's email verification, admin approval, login, a project and prompt, and a small Gemini evaluation through the deployed URL. Confirm the Vercel deployment's protection setting permits your intended viewers to open the link.
