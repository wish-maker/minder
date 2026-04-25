-- Create marketplace database
-- Note: Run this manually if needed: CREATE DATABASE minder_marketplace;
-- The script assumes we're connected to the minder_marketplace database

-- Categories table
CREATE TABLE marketplace_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    description TEXT,
    icon VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Users table (marketplace users, can sync with main auth)
CREATE TABLE marketplace_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user', -- 'user', 'developer', 'admin'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Plugins table (marketplace metadata)
CREATE TABLE marketplace_plugins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    description TEXT,
    author VARCHAR(100),
    author_email VARCHAR(255),

    -- Distribution
    repository_url VARCHAR(500),
    distribution_type VARCHAR(20) NOT NULL DEFAULT 'git', -- 'git', 'docker', 'hybrid'
    docker_image VARCHAR(255),
    current_version VARCHAR(50),

    -- Pricing & Tiers
    pricing_model VARCHAR(20) NOT NULL DEFAULT 'free', -- 'free', 'paid', 'freemium'
    base_tier VARCHAR(20) NOT NULL DEFAULT 'community', -- 'community', 'professional', 'enterprise'

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'archived'
    featured BOOLEAN DEFAULT FALSE,
    download_count INTEGER DEFAULT 0,
    rating_average DECIMAL(3,2),
    rating_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    published_at TIMESTAMP,

    -- Relationships
    developer_id UUID REFERENCES marketplace_users(id),
    category_id UUID REFERENCES marketplace_categories(id)
);

-- Plugin versions (for version management)
CREATE TABLE marketplace_plugin_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    version VARCHAR(50) NOT NULL,

    -- Version metadata
    changelog TEXT,
    requires_minder_version VARCHAR(50),
    manifest_json JSONB NOT NULL,

    -- Package info
    download_url VARCHAR(500),
    docker_image_tag VARCHAR(255),
    checksum_sha256 VARCHAR(64),

    -- Status
    stability VARCHAR(20) DEFAULT 'stable', -- 'alpha', 'beta', 'stable'
    deprecated BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    downloads INTEGER DEFAULT 0,

    UNIQUE(plugin_id, version)
);

-- Plugin tiers (for tier-based pricing)
CREATE TABLE marketplace_plugin_tiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    tier_name VARCHAR(50) NOT NULL,

    -- Pricing
    price_monthly_cents INTEGER DEFAULT 0,
    price_yearly_cents INTEGER DEFAULT 0,

    -- Features
    features JSONB NOT NULL, -- {"features": ["feature1", "feature2"]}
    limitations JSONB, -- {"limits": {"api_calls_per_day": 1000}}

    -- AI Tools per tier
    ai_tools JSONB, -- {"tools": ["tool1", "tool2"]} or "all"

    UNIQUE(plugin_id, tier_name)
);

-- User licenses
CREATE TABLE marketplace_licenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES marketplace_users(id),
    plugin_id UUID REFERENCES marketplace_plugins(id),

    -- License details
    tier VARCHAR(50) NOT NULL,
    license_key VARCHAR(100) UNIQUE NOT NULL,

    -- Validity
    valid_from TIMESTAMP DEFAULT NOW(),
    valid_until TIMESTAMP,
    active BOOLEAN DEFAULT TRUE,

    -- Usage tracking
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(user_id, plugin_id, active)
);

-- Plugin installations (per-user/plugin instances)
CREATE TABLE marketplace_installations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES marketplace_users(id),
    plugin_id UUID REFERENCES marketplace_plugins(id),
    version VARCHAR(50),

    -- Installation state
    status VARCHAR(20) NOT NULL, -- 'installing', 'installed', 'failed', 'uninstalled'
    enabled BOOLEAN DEFAULT TRUE,

    -- Configuration
    config_json JSONB,

    -- Timestamps
    installed_at TIMESTAMP DEFAULT NOW(),
    last_updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(user_id, plugin_id)
);

-- AI Tools Registry (central tool catalog)
CREATE TABLE marketplace_ai_tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID REFERENCES marketplace_plugins(id),

    -- Tool definition
    tool_name VARCHAR(100) NOT NULL,
    tool_type VARCHAR(20) NOT NULL, -- 'analysis', 'action', 'query'
    description TEXT,

    -- Technical details
    endpoint_path VARCHAR(200) NOT NULL,
    http_method VARCHAR(10) NOT NULL,
    parameters_schema JSONB NOT NULL,
    response_schema JSONB,

    -- Tier requirements
    required_tier VARCHAR(50) DEFAULT 'community',

    -- Status
    active BOOLEAN DEFAULT TRUE,

    UNIQUE(plugin_id, tool_name)
);

-- Create indexes
CREATE INDEX idx_marketplace_plugins_name ON marketplace_plugins(name);
CREATE INDEX idx_marketplace_plugins_status ON marketplace_plugins(status);
CREATE INDEX idx_marketplace_plugins_category ON marketplace_plugins(category_id);
CREATE INDEX idx_marketplace_plugins_developer ON marketplace_plugins(developer_id);

CREATE INDEX idx_marketplace_plugin_versions_plugin ON marketplace_plugin_versions(plugin_id);
CREATE INDEX idx_marketplace_plugin_versions_version ON marketplace_plugin_versions(version);

CREATE INDEX idx_marketplace_licenses_user_id ON marketplace_licenses(user_id);
CREATE INDEX idx_marketplace_licenses_plugin_id ON marketplace_licenses(plugin_id);
CREATE INDEX idx_marketplace_licenses_license_key ON marketplace_licenses(license_key);
CREATE INDEX idx_marketplace_licenses_active ON marketplace_licenses(active) WHERE active = TRUE;

CREATE INDEX idx_marketplace_installations_user_id ON marketplace_installations(user_id);
CREATE INDEX idx_marketplace_installations_plugin_id ON marketplace_installations(plugin_id);
CREATE INDEX idx_marketplace_installations_user_plugin ON marketplace_installations(user_id, plugin_id);

CREATE INDEX idx_marketplace_ai_tools_plugin ON marketplace_ai_tools(plugin_id);
CREATE INDEX idx_marketplace_ai_tools_active ON marketplace_ai_tools(active) WHERE active = TRUE;

-- Insert default categories
INSERT INTO marketplace_categories (name, display_name, description, icon) VALUES
('finance', 'Finance & Trading', 'Financial analysis and trading tools', '💰'),
('news', 'News & Media', 'News aggregation and analysis', '📰'),
('monitoring', 'Monitoring', 'System monitoring and alerts', '📊'),
('security', 'Security', 'Security analysis and tools', '🔒'),
('productivity', 'Productivity', 'Productivity enhancement tools', '⚡'),
('ai', 'AI & Machine Learning', 'AI and ML tools', '🤖'),
('integrations', 'Integrations', 'Third-party integrations', '🔗'),
('utilities', 'Utilities', 'General utilities', '🛠️');

-- Insert admin user
INSERT INTO marketplace_users (id, username, email, role) VALUES
('00000000-0000-0000-0000-000000000001', 'admin', 'admin@minder.local', 'admin');
