CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TYPE user_role AS ENUM ('user', 'admin');
CREATE TYPE run_status AS ENUM ('completed', 'failed', 'blocked');
CREATE TYPE deployment_environment AS ENUM ('dev', 'staging', 'prod');
CREATE TYPE deployment_status AS ENUM (
    'pending',
    'active',
    'rejected',
    'cancelled',
    'superseded',
    'rolled_back'
);
