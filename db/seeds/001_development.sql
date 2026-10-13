-- Demo credentials are documented in README.md and are development-only.
INSERT INTO users (
    id, email, display_name, password_hash, role, is_active, email_verified_at
)
VALUES
    (
        '11111111-1111-4111-8111-111111111111',
        'user@promptvault.dev',
        'Demo User',
        '$argon2id$v=19$m=65536,t=3,p=4$xAN45CUlqDFAYsFYhckiRw$BEFJ8S4TAkFtQY9ht0NQQf/kcr7ehXsddWNUr9I5TwA',
        'user',
        TRUE,
        CURRENT_TIMESTAMP
    ),
    (
        '22222222-2222-4222-8222-222222222222',
        'admin@promptvault.dev',
        'Demo Super Admin',
        '$argon2id$v=19$m=65536,t=3,p=4$2Kh79+q0mqLIGNTr1o6Crw$op6gF9TZlG1WhrAqxb01DtHlIUahQSVPlW+v2e9Kw2k',
        'admin',
        TRUE,
        CURRENT_TIMESTAMP
    ),
    (
        '33333333-3333-4333-8333-333333333333',
        'alice@promptvault.dev',
        'Alice Demo',
        '$argon2id$v=19$m=65536,t=3,p=4$e4FRPgLJ/Xao7nDRuRHRCQ$y3s+D/N5yoAZsY4+YTvE9l0QISSL2vObcyOh2t7wHn0',
        'user',
        TRUE,
        CURRENT_TIMESTAMP
    ),
    (
        '44444444-4444-4444-8444-444444444444',
        'bob@promptvault.dev',
        'Bob Demo',
        '$argon2id$v=19$m=65536,t=3,p=4$IRENgpVou2Q5wAC120yT9Q$W00HsVAUX2LewpKfxx4xhPaFOoEJHjtEueg4huHPk8g',
        'user',
        TRUE,
        CURRENT_TIMESTAMP
    ),
    (
        '55555555-5555-4555-8555-555555555555',
        'inactive@promptvault.dev',
        'Inactive Demo',
        '$argon2id$v=19$m=65536,t=3,p=4$psr9BzcDkjgFUedrU/AfTQ$etM4wJB4ZRgCX1HY4+be2TL5xPugmqvxxWlohvhUGAQ',
        'user',
        FALSE,
        CURRENT_TIMESTAMP
    )
ON CONFLICT (email) DO UPDATE
SET display_name = EXCLUDED.display_name,
    password_hash = EXCLUDED.password_hash,
    role = EXCLUDED.role,
    is_active = EXCLUDED.is_active,
    email_verified_at = EXCLUDED.email_verified_at;
