SELECT
    prompt_id,
    environment,
    version_number,
    status,
    requested_at,
    reviewed_at,
    activated_at,
    rollback_of_id
FROM deployment_history
ORDER BY prompt_id, environment, requested_at DESC;
