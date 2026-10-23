-- Development-only activity for the seeded Demo User. Stable IDs keep reseeding safe.
WITH seed_rows (
    id, user_id, project_id, prompt_id, version_id, status, provider, model,
    input_variables, output_text, prompt_tokens, completion_tokens, latency_ms,
    cost, created_at
) AS (VALUES
    (
        '77777777-7777-4777-8777-777777777771',
        '11111111-1111-4111-8111-111111111111',
        '33333333-3333-4333-8333-333333333333',
        '44444444-4444-4444-8444-444444444444',
        '55555555-5555-4555-8555-555555555555',
        'completed', 'gemini', 'gemini-3.5-flash-lite',
        '{"customer_message":"Can you check my payment?","order_id":"10482"}'::jsonb,
        'Your payment is being reviewed. We will update you shortly.', 42, 18, 190, 0,
        CURRENT_TIMESTAMP - INTERVAL '4 minutes'
    ),
    (
        '77777777-7777-4777-8777-777777777772',
        '11111111-1111-4111-8111-111111111111',
        '33333333-3333-4333-8333-333333333333',
        '44444444-4444-4444-8444-444444444444',
        '55555555-5555-4555-8555-555555555555',
        'completed', 'gemini', 'gemini-3.5-flash-lite',
        '{"customer_message":"Where is my order?","order_id":"10483"}'::jsonb,
        'Your order is in progress. We will share the next update soon.', 40, 17, 184, 0,
        CURRENT_TIMESTAMP - INTERVAL '3 minutes'
    ),
    (
        '77777777-7777-4777-8777-777777777773',
        '11111111-1111-4111-8111-111111111111',
        '33333333-3333-4333-8333-333333333333',
        '44444444-4444-4444-8444-444444444444',
        '55555555-5555-4555-8555-555555555555',
        'completed', 'gemini', 'gemini-3.5-flash-lite',
        '{"customer_message":"Is checkout available?","order_id":"10484"}'::jsonb,
        'Checkout is available. Please try again and let us know if you need help.', 39, 19, 176, 0,
        CURRENT_TIMESTAMP - INTERVAL '2 minutes'
    ),
    (
        '77777777-7777-4777-8777-777777777774',
        '11111111-1111-4111-8111-111111111111',
        '33333333-3333-4333-8333-333333333333',
        '44444444-4444-4444-8444-444444444444',
        '55555555-5555-4555-8555-555555555555',
        'completed', 'gemini', 'gemini-3.5-flash-lite',
        '{"customer_message":"Please confirm my order.","order_id":"10485"}'::jsonb,
        'Your order has been received. We will send a confirmation shortly.', 41, 18, 181, 0,
        CURRENT_TIMESTAMP - INTERVAL '1 minute'
    )
)
INSERT INTO runs (
    id, user_id, version_id, status,
    output_text, prompt_tokens, completion_tokens, latency_ms,
    cost, created_at
)
SELECT seeded.id::uuid, seeded.user_id::uuid, seeded.version_id::uuid, seeded.status::run_status,
       seeded.output_text,
       seeded.prompt_tokens, seeded.completion_tokens, seeded.latency_ms,
       seeded.cost, seeded.created_at
FROM seed_rows AS seeded
WHERE NOT EXISTS (SELECT 1 FROM runs AS existing WHERE existing.id = seeded.id::uuid);

-- Development-only activity for the seeded Demo User. Stable IDs keep reseeding safe.
WITH seed_rows (
    id, user_id, project_id, prompt_id, version_id, status, provider, model,
    input_variables, output_text, prompt_tokens, completion_tokens, latency_ms,
    cost, created_at
) AS (VALUES
    (
        '77777777-7777-4777-8777-777777777771',
        '11111111-1111-4111-8111-111111111111',
        '33333333-3333-4333-8333-333333333333',
        '44444444-4444-4444-8444-444444444444',
        '55555555-5555-4555-8555-555555555555',
        'completed', 'gemini', 'gemini-3.5-flash-lite',
        '{"customer_message":"Can you check my payment?","order_id":"10482"}'::jsonb,
        'Your payment is being reviewed. We will update you shortly.', 42, 18, 190, 0,
        CURRENT_TIMESTAMP - INTERVAL '4 minutes'
    ),
    (
        '77777777-7777-4777-8777-777777777772',
        '11111111-1111-4111-8111-111111111111',
        '33333333-3333-4333-8333-333333333333',
        '44444444-4444-4444-8444-444444444444',
        '55555555-5555-4555-8555-555555555555',
        'completed', 'gemini', 'gemini-3.5-flash-lite',
        '{"customer_message":"Where is my order?","order_id":"10483"}'::jsonb,
        'Your order is in progress. We will share the next update soon.', 40, 17, 184, 0,
        CURRENT_TIMESTAMP - INTERVAL '3 minutes'
    ),
    (
        '77777777-7777-4777-8777-777777777773',
        '11111111-1111-4111-8111-111111111111',
        '33333333-3333-4333-8333-333333333333',
        '44444444-4444-4444-8444-444444444444',
        '55555555-5555-4555-8555-555555555555',
        'completed', 'gemini', 'gemini-3.5-flash-lite',
        '{"customer_message":"Is checkout available?","order_id":"10484"}'::jsonb,
        'Checkout is available. Please try again and let us know if you need help.', 39, 19, 176, 0,
        CURRENT_TIMESTAMP - INTERVAL '2 minutes'
    ),
    (
        '77777777-7777-4777-8777-777777777774',
        '11111111-1111-4111-8111-111111111111',
        '33333333-3333-4333-8333-333333333333',
        '44444444-4444-4444-8444-444444444444',
        '55555555-5555-4555-8555-555555555555',
        'completed', 'gemini', 'gemini-3.5-flash-lite',
        '{"customer_message":"Please confirm my order.","order_id":"10485"}'::jsonb,
        'Your order has been received. We will send a confirmation shortly.', 41, 18, 181, 0,
        CURRENT_TIMESTAMP - INTERVAL '1 minute'
    )
)
INSERT INTO run_inputs(run_id,run_created_at,name,value)
SELECT r.id,r.created_at,i.key,i.value FROM seed_rows seeded
JOIN runs r ON r.id=seeded.id::uuid
CROSS JOIN LATERAL jsonb_each_text(seeded.input_variables) i
ON CONFLICT DO NOTHING;
