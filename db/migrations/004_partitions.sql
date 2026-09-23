CREATE OR REPLACE FUNCTION create_run_partition(p_month DATE)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    partition_start DATE := date_trunc('month', p_month)::date;
    partition_end DATE := (date_trunc('month', p_month) + INTERVAL '1 month')::date;
    partition_name TEXT := format('runs_%s', to_char(partition_start, 'YYYY_MM'));
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF runs FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        partition_start,
        partition_end
    );
    RETURN partition_name;
END;
$$;

SELECT create_run_partition(current_date);
SELECT create_run_partition((current_date + INTERVAL '1 month')::date);
