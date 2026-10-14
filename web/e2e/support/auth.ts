import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import type { APIRequestContext } from '@playwright/test'

const apiBase = process.env.E2E_API_BASE_URL ?? 'http://localhost:8000/api/v1'
const repositoryRoot = fileURLToPath(new URL('../../../', import.meta.url))

export async function createVerifiedTestAccount(request: APIRequestContext, label: string) {
  if (!process.env.E2E_DATABASE_URL) throw new Error('Set E2E_DATABASE_URL for verified test accounts.')
  const python = process.env.E2E_PYTHON ?? fileURLToPath(new URL('../../../.venv/bin/python', import.meta.url))
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const email = `${label}-${suffix}@example.com`
  const password = 'VerifiedTestPassword2026!'
  const displayName = label.replaceAll('-', ' ').replace(/\b\w/g, (character) => character.toUpperCase())
  const script = `import os, sys
from urllib.parse import urlsplit
import psycopg
sys.path.insert(0, os.getcwd())
from api.app.security import hash_password
database_url, email, display_name, password = os.environ['E2E_DATABASE_URL'], sys.argv[1], sys.argv[2], sys.argv[3]
if not urlsplit(database_url).path.rstrip('/').endswith('_test'):
    raise SystemExit('Verified account helper requires a database ending in _test')
with psycopg.connect(database_url) as connection:
    connection.execute(
        """INSERT INTO users (email, display_name, password_hash, role, is_active, email_verified_at)
           VALUES (%s, %s, %s, 'user', TRUE, CURRENT_TIMESTAMP)""",
        (email, display_name, hash_password(password)),
    )
`
  execFileSync(python, ['-c', script, email, displayName, password], {
    cwd: repositoryRoot,
    encoding: 'utf8',
  })
  const login = await request.post(`${apiBase}/auth/login`, { data: { email, password } })
  if (login.status() !== 200) throw new Error(`Verified test account login failed: ${login.status()}`)
  return { email, password, session: await login.json() }
}
