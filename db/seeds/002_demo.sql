INSERT INTO projects (id, name, key, description, owner_id)
VALUES (
    '33333333-3333-4333-8333-333333333333',
    'Checkout Assistant',
    'checkout-assistant',
    'Demo project for the PromptVault deployment workflow.',
    '11111111-1111-4111-8111-111111111111'
)
ON CONFLICT (key) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description;

INSERT INTO project_members (project_id, user_id, added_by)
VALUES (
    '33333333-3333-4333-8333-333333333333',
    '22222222-2222-4222-8222-222222222222',
    '11111111-1111-4111-8111-111111111111'
)
ON CONFLICT (project_id, user_id) DO NOTHING;

INSERT INTO prompts (id, project_id, key, name, description)
VALUES (
    '44444444-4444-4444-8444-444444444444',
    '33333333-3333-4333-8333-333333333333',
    'support-reply',
    'Checkout support reply',
    'Responds to a customer checkout question.'
)
ON CONFLICT (project_id, key) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description;

INSERT INTO prompt_versions (
    id,
    prompt_id,
    version_number,
    parent_version_id,
    template_body,
    variables,
    model_config,
    commit_message,
    created_by
)
VALUES (
    '55555555-5555-4555-8555-555555555555',
    '44444444-4444-4444-8444-444444444444',
    1,
    NULL,
    'Reply helpfully to {{customer_message}} about order {{order_id}}.',
    '["customer_message", "order_id"]'::jsonb,
    '{"provider":"mock","model":"deterministic-v1","temperature":0,"max_output_tokens":500}'::jsonb,
    'Initial demo version',
    '11111111-1111-4111-8111-111111111111'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO budgets (id, user_id, monthly_limit, timezone, created_by)
VALUES (
    '66666666-6666-4666-8666-666666666666',
    '11111111-1111-4111-8111-111111111111',
    25.000000,
    'UTC',
    '22222222-2222-4222-8222-222222222222'
)
ON CONFLICT (user_id) WHERE user_id IS NOT NULL DO UPDATE
SET monthly_limit = EXCLUDED.monthly_limit,
    timezone = EXCLUDED.timezone;
