SELECT create_run_partition(current_date);
SELECT create_run_partition((current_date + INTERVAL '1 month')::date);
