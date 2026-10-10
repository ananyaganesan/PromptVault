import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

// Read-only SQL assertions against an explicitly selected acceptance-test database.
// Never include passwords, hashes, or runtime-token values in assertion output.
export function databaseRows(query: string, parameters: unknown[] = []): Record<string, unknown>[] {
  if (!process.env.E2E_DATABASE_URL) throw new Error('Set E2E_DATABASE_URL for database reconciliation tests.')
  const python = process.env.E2E_PYTHON ?? fileURLToPath(new URL('../../../.venv/bin/python', import.meta.url))
  const script = `import json, os, sys, psycopg
from psycopg.rows import dict_row
with psycopg.connect(os.environ['E2E_DATABASE_URL'], row_factory=dict_row) as connection:
    connection.execute('SET TRANSACTION READ ONLY')
    rows = connection.execute(sys.argv[1], json.loads(sys.argv[2])).fetchall()
    print(json.dumps(rows, default=str))
`
  return JSON.parse(execFileSync(python, ['-c', script, query, JSON.stringify(parameters)], { encoding: 'utf8' }))
}
