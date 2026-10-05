-- Local development login accounts. Password hashes are generated with api.app.security.hash_password.
INSERT INTO users (email, display_name, password_hash, role, is_active)
VALUES
    ('testuser1@example.com', 'Test User 1', '$argon2id$v=19$m=65536,t=3,p=4$osCSmJnS3L/X3yL0CLyr/A$9sh5cAINdMV8jGB+JVsUh5A0SFzgymQvnLB3ZbZOXpQ', 'user', TRUE),
    ('testuser2@example.com', 'Test User 2', '$argon2id$v=19$m=65536,t=3,p=4$zjV88RiHlZAWzCVC1DzQSg$tFi5fcUf9/MxFt7fd0kNB0FH2V/fHsaAwpePLOiHARo', 'user', TRUE),
    ('admin@example.com', 'Test Admin', '$argon2id$v=19$m=65536,t=3,p=4$64Tj0uacmjc4RZ6OGLYiMg$8N5wWEaNnu1xLN/cYsbWzpTHmfrVqfzMbqxDBjq1M4s', 'admin', TRUE)
ON CONFLICT (email) DO UPDATE
SET display_name = EXCLUDED.display_name,
    password_hash = EXCLUDED.password_hash,
    role = EXCLUDED.role,
    is_active = EXCLUDED.is_active;
