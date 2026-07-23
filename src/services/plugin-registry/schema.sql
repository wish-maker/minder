-- plugin-registry database schema (issue #17)
-- Plugin registration/persistence (in-memory cache is hydrated from this on startup).

CREATE TABLE IF NOT EXISTS plugins (
    name VARCHAR(255) PRIMARY KEY,
    version VARCHAR(50) NOT NULL DEFAULT '1.0.0',
    description TEXT,
    author VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'registered',
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    dependencies TEXT,
    capabilities JSONB,
    data_sources JSONB,
    databases JSONB,
    health_status VARCHAR(50) DEFAULT 'unknown',
    last_health_check TIMESTAMP WITH TIME ZONE,
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Central plugin configuration set over the API (persisted overrides of a plugin's
-- CONFIG_SCHEMA defaults/env; applied to the running instance without a restart).
CREATE TABLE IF NOT EXISTS plugin_configs (
    plugin_name VARCHAR(255) PRIMARY KEY,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
