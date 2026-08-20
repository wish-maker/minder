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

-- #747: a plugin's own stable identity (from its directory's committed
-- .plugin_id marker -- see core/plugin_identity.py), independent of `name`
-- (the directory name itself, which changes if the directory is renamed).
-- Lets a rename be detected (same stable_id, different name) and reconciled
-- in place instead of leaving an orphaned row under the old name.
-- marketplace_plugin_id is the marketplace catalog row this plugin was last
-- resolved to, persisted so subsequent syncs can update it by id instead of
-- searching (and possibly re-creating) by name.
ALTER TABLE plugins ADD COLUMN IF NOT EXISTS stable_id VARCHAR(64);
ALTER TABLE plugins ADD COLUMN IF NOT EXISTS marketplace_plugin_id VARCHAR(64);
CREATE INDEX IF NOT EXISTS idx_plugins_stable_id ON plugins (stable_id)
    WHERE stable_id IS NOT NULL;

-- Central plugin configuration set over the API (persisted overrides of a plugin's
-- CONFIG_SCHEMA defaults/env; applied to the running instance without a restart).
CREATE TABLE IF NOT EXISTS plugin_configs (
    plugin_name VARCHAR(255) PRIMARY KEY,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Webhook plugin manifests (#269): persisted so registered webhook routes survive
-- a registry restart. Previously in-memory-only, backed by a "/tmp/*-manifest.yml"
-- restart-safety workaround -- restored from here on startup instead.
CREATE TABLE IF NOT EXISTS plugin_manifests (
    plugin_name VARCHAR(255) PRIMARY KEY,
    manifest JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
