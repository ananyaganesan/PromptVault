-- Demo credentials are documented in README.md and are development-only.
INSERT INTO users (id, email, display_name, password_hash, role, is_active)
VALUES
    (
        '11111111-1111-4111-8111-111111111111',
        'user@promptvault.local',
        'Demo User',
        '$argon2id$v=19$m=65536,t=3,p=4$xAN45CUlqDFAYsFYhckiRw$BEFJ8S4TAkFtQY9ht0NQQf/kcr7ehXsddWNUr9I5TwA',
        'user',
        TRUE
    ),
    (
        '22222222-2222-4222-8222-222222222222',
        'admin@promptvault.local',
        'Demo Super Admin',
        '$argon2id$v=19$m=65536,t=3,p=4$2Kh79+q0mqLIGNTr1o6Crw$op6gF9TZlG1WhrAqxb01DtHlIUahQSVPlW+v2e9Kw2k',
        'admin',
        TRUE
    )
ON CONFLICT (email) DO UPDATE
SET display_name = EXCLUDED.display_name,
    password_hash = EXCLUDED.password_hash,
    role = EXCLUDED.role,
    is_active = TRUE;
