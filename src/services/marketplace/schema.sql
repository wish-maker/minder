-- Marketplace Database Schema (Updated for code compatibility)
-- Minder Plugin Marketplace and Licensing System

-- Users table
CREATE TABLE IF NOT EXISTS marketplace_users (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    tier VARCHAR(50) DEFAULT 'community',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Plugins table (updated to match code expectations)
CREATE TABLE IF NOT EXISTS marketplace_plugins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    description TEXT,
    author VARCHAR(255),
    author_email VARCHAR(255),
    repository_url VARCHAR(500),
    distribution_type VARCHAR(50) NOT NULL DEFAULT 'git',
    docker_image VARCHAR(255),
    current_version VARCHAR(50),
    pricing_model VARCHAR(50) NOT NULL DEFAULT 'free',
    base_tier VARCHAR(50) NOT NULL DEFAULT 'community',
    status VARCHAR(50) NOT NULL DEFAULT 'approved',
    featured BOOLEAN DEFAULT FALSE,
    download_count INTEGER DEFAULT 0,
    rating_average DECIMAL(3,2),
    rating_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP,
    developer_id VARCHAR(255),
    category_id VARCHAR(255)
);

-- Plugin versions table
CREATE TABLE IF NOT EXISTS marketplace_plugin_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    version VARCHAR(50) NOT NULL,
    changelog TEXT,
    download_url VARCHAR(500),
    size_bytes BIGINT,
    checksum VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(plugin_id, version)
);

-- Plugin tiers table
CREATE TABLE IF NOT EXISTS marketplace_plugin_tiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    tier VARCHAR(50) NOT NULL,
    price DECIMAL(10,2),
    features JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(plugin_id, tier)
);

-- Categories table
CREATE TABLE IF NOT EXISTS marketplace_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    description TEXT,
    icon_url VARCHAR(500),
    parent_id INTEGER REFERENCES marketplace_categories(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Licenses table
CREATE TABLE IF NOT EXISTS marketplace_licenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) REFERENCES marketplace_users(user_id) ON DELETE CASCADE,
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    tier VARCHAR(50) NOT NULL,
    license_key VARCHAR(255) UNIQUE NOT NULL,
    valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_until TIMESTAMP,
    active BOOLEAN DEFAULT TRUE,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Installations table
CREATE TABLE IF NOT EXISTS marketplace_installations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) REFERENCES marketplace_users(user_id) ON DELETE CASCADE,
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    version VARCHAR(50),
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'installed',
    enabled BOOLEAN DEFAULT TRUE,
    config_json JSONB,
    UNIQUE(user_id, plugin_id)
);

-- AI Tools table (updated to match code expectations)
CREATE TABLE IF NOT EXISTS marketplace_ai_tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    tool_name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    description TEXT,
    tool_type VARCHAR(50),
    category VARCHAR(50),
    endpoint_path VARCHAR(500),
    http_method VARCHAR(10) DEFAULT 'POST',
    parameters_schema JSONB,
    response_schema JSONB,
    configuration_schema JSONB,
    default_configuration JSONB,
    required_tier VARCHAR(50) DEFAULT 'community',
    active BOOLEAN DEFAULT TRUE,
    allow_user_configuration BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,
    tags TEXT[],
    version VARCHAR(50) DEFAULT '1.0.0',
    author VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(plugin_id, tool_name)
);

-- AI Tools configurations table
CREATE TABLE IF NOT EXISTS marketplace_ai_tools_configurations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) REFERENCES marketplace_users(user_id) ON DELETE CASCADE,
    ai_tool_id UUID REFERENCES marketplace_ai_tools(id) ON DELETE CASCADE,
    configuration JSONB,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, ai_tool_id)
);

-- AI Tools registrations table
CREATE TABLE IF NOT EXISTS marketplace_ai_tools_registrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ai_tool_id UUID REFERENCES marketplace_ai_tools(id) ON DELETE CASCADE,
    service_name VARCHAR(255),
    endpoint_url VARCHAR(500),
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_verified_at TIMESTAMP,
    status VARCHAR(50) DEFAULT 'active'
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_name ON marketplace_plugins(name);
CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_category ON marketplace_plugins(category_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_tier ON marketplace_plugins(base_tier);
CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_status ON marketplace_plugins(status);
CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_pricing_model ON marketplace_plugins(pricing_model);
CREATE INDEX IF NOT EXISTS idx_marketplace_licenses_user_id ON marketplace_licenses(user_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_licenses_plugin_id ON marketplace_licenses(plugin_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_installations_user_id ON marketplace_installations(user_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_ai_tools_plugin_id ON marketplace_ai_tools(plugin_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_ai_tools_type ON marketplace_ai_tools(tool_type);
CREATE INDEX IF NOT EXISTS idx_marketplace_ai_tools_active ON marketplace_ai_tools(active);

-- Insert default categories
INSERT INTO marketplace_categories (name, display_name, description) VALUES
    ('data', 'Data Processing', 'Plugins for data collection and processing'),
    ('analysis', 'Analysis', 'Plugins for data analysis and visualization'),
    ('automation', 'Automation', 'Plugins for task automation'),
    ('integration', 'Integration', 'Plugins for third-party integrations')
ON CONFLICT (name) DO NOTHING;

-- Insert default admin user
INSERT INTO marketplace_users (user_id, username, email, tier) VALUES
    ('admin', 'Administrator', 'admin@minder.local', 'enterprise')
ON CONFLICT (user_id) DO NOTHING;
