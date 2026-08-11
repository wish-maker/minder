-- api-gateway database schema (issue #17)
-- Users table for JWT auth (bcrypt password hashes).

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- OIDC login against Authelia (#<issue>). Authelia's file-backed users have no
-- numeric id, only a stable "sub" claim (its username) -- this column maps that
-- identity to Minder's existing integer user id, which several other tables
-- (e.g. marketplace_installations.user_id) already treat as a real foreign
-- key, so first-time OIDC login provisions or links a row here rather than
-- inventing a second, parallel identity system.
ALTER TABLE users ADD COLUMN IF NOT EXISTS authelia_subject VARCHAR(255) UNIQUE;
