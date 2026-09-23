EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT id, status, provider, model, cost, created_at
FROM runs
WHERE project_id = :'project_id'::uuid
ORDER BY created_at DESC, id
LIMIT 25;

EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT id, version_number, created_at
FROM prompt_versions
WHERE prompt_id = :'prompt_id'::uuid
ORDER BY version_number DESC, id
LIMIT 25;
