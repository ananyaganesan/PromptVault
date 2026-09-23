SELECT
    month,
    provider,
    model,
    sum(completed_runs) AS completed_runs,
    sum(cost)::NUMERIC(18, 6) AS total_cost
FROM monthly_costs
GROUP BY month, provider, model
ORDER BY month DESC, total_cost DESC, provider, model;
