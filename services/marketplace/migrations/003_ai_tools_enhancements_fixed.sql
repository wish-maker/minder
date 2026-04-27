-- AI Tools Enhancements for Plugin Marketplace - Fixed Version
-- Adds advanced AI tools management with configuration, tier-based access, and lifecycle management

-- First, let's check what columns we need to add
DO $$
BEGIN
    -- Add missing columns to marketplace_ai_tools
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'marketplace_ai_tools'
        AND column_name = 'configuration_schema'
    ) THEN
        ALTER TABLE marketplace_ai_tools
        ADD COLUMN configuration_schema JSONB;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'marketplace_ai_tools'
        AND column_name = 'default_configuration'
    ) THEN
        ALTER TABLE marketplace_ai_tools
        ADD COLUMN default_configuration JSONB;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'marketplace_ai_tools'
        AND column_name = 'is_enabled'
    ) THEN
        ALTER TABLE marketplace_ai_tools
        ADD COLUMN is_enabled BOOLEAN DEFAULT TRUE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'marketplace_ai_tools'
        AND column_name = 'category'
    ) THEN
        ALTER TABLE marketplace_ai_tools
        ADD COLUMN category VARCHAR(50) DEFAULT 'custom';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'marketplace_ai_tools'
        AND column_name = 'tags'
    ) THEN
        ALTER TABLE marketplace_ai_tools
        ADD COLUMN tags JSONB DEFAULT '[]';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'marketplace_ai_tools'
        AND column_name = 'requires_configuration'
    ) THEN
        ALTER TABLE marketplace_ai_tools
        ADD COLUMN requires_configuration BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'marketplace_ai_tools'
        AND column_name = 'allow_user_configuration'
    ) THEN
        ALTER TABLE marketplace_ai_tools
        ADD COLUMN allow_user_configuration BOOLEAN DEFAULT TRUE;
    END IF;
END $$;

-- AI Tools Configuration Storage
CREATE TABLE IF NOT EXISTS marketplace_ai_tools_configurations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,

    -- Configuration Schema
    configuration_schema JSONB NOT NULL,
    default_configuration JSONB NOT NULL,

    -- Validation
    required_parameters JSONB,
    optional_parameters JSONB,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(plugin_id, tool_name)
);

-- AI Tools Registrations (plugin tool instances per installation)
CREATE TABLE IF NOT EXISTS marketplace_ai_tools_registrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,
    installation_id UUID REFERENCES marketplace_installations(id) ON DELETE CASCADE,

    -- Instance Configuration
    configuration JSONB NOT NULL,

    -- State Management
    is_enabled BOOLEAN DEFAULT TRUE,
    activation_status VARCHAR(20) DEFAULT 'pending',

    -- Validation
    last_validated_at TIMESTAMP,
    validation_status VARCHAR(20),
    validation_errors JSONB,

    -- Usage Tracking
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,

    -- Timestamps
    registered_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(plugin_id, tool_name, installation_id)
);

-- Add constraint for activation_status
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'marketplace_ai_tools_registrations_activation_status_check'
    ) THEN
        ALTER TABLE marketplace_ai_tools_registrations
        ADD CONSTRAINT marketplace_ai_tools_registrations_activation_status_check
        CHECK (activation_status IN ('pending', 'active', 'inactive', 'error'));
    END IF;
END $$;

-- Plugin AI Tools Relationship (many-to-many with configuration)
CREATE TABLE IF NOT EXISTS marketplace_plugin_ai_tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    tool_id UUID REFERENCES marketplace_ai_tools(id) ON DELETE CASCADE,

    -- Tool Assignment
    is_default BOOLEAN DEFAULT FALSE,
    required_tier VARCHAR(50) DEFAULT 'community',
    configuration_override JSONB,
    is_enabled BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,

    UNIQUE(plugin_id, tool_id)
);

-- Create indexes for enhanced AI tools queries
CREATE INDEX IF NOT EXISTS idx_ai_tools_configurations_plugin
ON marketplace_ai_tools_configurations(plugin_id);

CREATE INDEX IF NOT EXISTS idx_ai_tools_configurations_tool
ON marketplace_ai_tools_configurations(tool_name);

CREATE INDEX IF NOT EXISTS idx_ai_tools_registrations_plugin
ON marketplace_ai_tools_registrations(plugin_id);

CREATE INDEX IF NOT EXISTS idx_ai_tools_registrations_installation
ON marketplace_ai_tools_registrations(installation_id);

CREATE INDEX IF NOT EXISTS idx_ai_tools_registrations_enabled
ON marketplace_ai_tools_registrations(is_enabled)
WHERE is_enabled = TRUE;

CREATE INDEX IF NOT EXISTS idx_ai_tools_registrations_status
ON marketplace_ai_tools_registrations(activation_status);

CREATE INDEX IF NOT EXISTS idx_plugin_ai_tools_plugin
ON marketplace_plugin_ai_tools(plugin_id);

CREATE INDEX IF NOT EXISTS idx_plugin_ai_tools_tool
ON marketplace_plugin_ai_tools(tool_id);

CREATE INDEX IF NOT EXISTS idx_plugin_ai_tools_enabled
ON marketplace_plugin_ai_tools(is_enabled)
WHERE is_enabled = TRUE;

-- Enhanced indexes for marketplace_ai_tools
CREATE INDEX IF NOT EXISTS idx_ai_tools_tier
ON marketplace_ai_tools(required_tier);

CREATE INDEX IF NOT EXISTS idx_ai_tools_category
ON marketplace_ai_tools(category);

-- Add comments for documentation
COMMENT ON TABLE marketplace_ai_tools_configurations IS 'Stores configuration schemas for AI tools';
COMMENT ON TABLE marketplace_ai_tools_registrations IS 'Tracks AI tool instances per plugin installation';
COMMENT ON TABLE marketplace_plugin_ai_tools IS 'Manages plugin-tool relationships with tier-based access';

-- Insert default AI tool categories if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM marketplace_categories WHERE name = 'ai-tools') THEN
        INSERT INTO marketplace_categories (name, display_name, description, icon) VALUES
        ('ai-tools', 'AI Tools', 'Plugins that provide AI-powered tools and capabilities', '🤖');
    END IF;
END $$;