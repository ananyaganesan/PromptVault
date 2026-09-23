INSERT INTO model_pricing (
    id,
    provider,
    model,
    input_price_per_million,
    output_price_per_million,
    effective_from
)
VALUES (
    '00000000-0000-4000-8000-000000000001',
    'mock',
    'deterministic-v1',
    1.000000,
    2.000000,
    '2026-01-01T00:00:00Z'
)
ON CONFLICT DO NOTHING;
