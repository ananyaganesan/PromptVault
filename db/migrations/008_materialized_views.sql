CREATE MATERIALIZED VIEW organization_monthly_metrics AS
SELECT
    date_trunc('month', created_at) AS month,
    count(*) AS run_count,
    count(*) FILTER (WHERE status = 'completed') AS completed_runs,
    count(*) FILTER (WHERE status = 'failed') AS failed_runs,
    count(*) FILTER (WHERE status = 'blocked') AS blocked_runs,
    COALESCE(sum(cost) FILTER (WHERE status = 'completed'), 0)::NUMERIC(18, 6) AS total_cost,
    max(created_at) AS refreshed_through
FROM runs
GROUP BY date_trunc('month', created_at);

CREATE UNIQUE INDEX uq_organization_monthly_metrics
    ON organization_monthly_metrics (month);

CREATE MATERIALIZED VIEW user_monthly_metrics AS
SELECT
    date_trunc('month', created_at) AS month,
    user_id,
    count(*) AS run_count,
    count(*) FILTER (WHERE status = 'completed') AS completed_runs,
    count(*) FILTER (WHERE status = 'failed') AS failed_runs,
    count(*) FILTER (WHERE status = 'blocked') AS blocked_runs,
    COALESCE(sum(cost) FILTER (WHERE status = 'completed'), 0)::NUMERIC(18, 6) AS total_cost,
    max(created_at) AS refreshed_through
FROM runs
GROUP BY date_trunc('month', created_at), user_id;

CREATE UNIQUE INDEX uq_user_monthly_metrics
    ON user_monthly_metrics (month, user_id);
