SELECT 'CREATE DATABASE promptvault_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'promptvault_test')
\gexec
