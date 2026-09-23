CREATE VIEW prompt_version_lineage AS
WITH RECURSIVE lineage AS (
    SELECT
        version.id AS descendant_version_id,
        version.id AS version_id,
        version.parent_version_id,
        0 AS depth,
        ARRAY[version.id] AS path,
        FALSE AS cycle_detected
    FROM prompt_versions AS version

    UNION ALL

    SELECT
        lineage.descendant_version_id,
        parent.id,
        parent.parent_version_id,
        lineage.depth + 1,
        lineage.path || parent.id,
        parent.id = ANY(lineage.path)
    FROM lineage
    JOIN prompt_versions AS parent ON parent.id = lineage.parent_version_id
    WHERE NOT lineage.cycle_detected
      AND lineage.depth < 1000
)
SELECT
    descendant_version_id,
    version_id,
    parent_version_id,
    depth,
    cycle_detected
FROM lineage;

CREATE VIEW deployment_history AS
SELECT
    deployment.id,
    deployment.prompt_id,
    prompt.project_id,
    deployment.version_id,
    version.version_number,
    deployment.environment,
    deployment.status,
    deployment.request_note,
    deployment.review_note,
    deployment.rollback_reason,
    deployment.rollback_of_id,
    deployment.requested_by,
    deployment.reviewed_by,
    deployment.requested_at,
    deployment.reviewed_at,
    deployment.activated_at
FROM deployments AS deployment
JOIN prompts AS prompt ON prompt.id = deployment.prompt_id
JOIN prompt_versions AS version ON version.id = deployment.version_id;

CREATE VIEW monthly_costs AS
SELECT
    date_trunc('month', created_at) AS month,
    user_id,
    project_id,
    provider,
    model,
    count(*) FILTER (WHERE status = 'completed') AS completed_runs,
    count(*) FILTER (WHERE status = 'failed') AS failed_runs,
    count(*) FILTER (WHERE status = 'blocked') AS blocked_runs,
    COALESCE(sum(cost) FILTER (WHERE status = 'completed'), 0)::NUMERIC(18, 6) AS cost
FROM runs
GROUP BY date_trunc('month', created_at), user_id, project_id, provider, model;
