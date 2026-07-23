-- plugin-state-manager database schema (issue #17)
-- Plugin state + default-plugin bootstrap + dependency graph + subscriptions.

CREATE TABLE IF NOT EXISTS plugin_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_name VARCHAR(255) UNIQUE NOT NULL,
    state VARCHAR(50) NOT NULL,
    license_tier VARCHAR(50) DEFAULT 'community',
    license_key VARCHAR(255),
    config JSONB DEFAULT '{}'::jsonb,
    enabled_at TIMESTAMP,
    disabled_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_state CHECK (
        state IN ('installed', 'enabled', 'disabled', 'error',
                  'INSTALLED', 'ENABLED', 'DISABLED', 'ERROR')
    )
);

CREATE TABLE IF NOT EXISTS default_plugins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_name VARCHAR(255) UNIQUE NOT NULL,
    priority INTEGER NOT NULL,
    auto_enable BOOLEAN NOT NULL,
    required BOOLEAN NOT NULL,
    min_tier VARCHAR(50) NOT NULL,
    description TEXT,
    version VARCHAR(50),
    config JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS plugin_dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_name VARCHAR(255) NOT NULL,
    depends_on VARCHAR(255) NOT NULL,
    required BOOLEAN NOT NULL,
    UNIQUE(plugin_name, depends_on)
);

CREATE TABLE IF NOT EXISTS user_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) UNIQUE NOT NULL,
    tier VARCHAR(50) NOT NULL,
    license_key VARCHAR(255),
    valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_until TIMESTAMP,
    auto_renew BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
