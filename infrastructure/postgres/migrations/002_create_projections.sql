-- infrastructure/postgres/migrations/002_create_projections.sql

-- Model Catalog Projection
CREATE TABLE IF NOT EXISTS model_catalog_projection (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    model_type TEXT NOT NULL,
    base_model TEXT,
    resource_profile TEXT NOT NULL,
    latest_version TEXT,
    total_versions INT DEFAULT 0,
    status TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_catalog_status ON model_catalog_projection(status);
CREATE INDEX idx_catalog_type ON model_catalog_projection(model_type);

-- Model Deployment Projection
CREATE TABLE IF NOT EXISTS model_deployment_projection (
    id UUID PRIMARY KEY,
    model_id UUID NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL,
    previous_status TEXT,
    health_status TEXT DEFAULT 'UNKNOWN',
    endpoint_url TEXT,
    runtime_env TEXT NOT NULL,
    node_id TEXT,
    deployed_at TIMESTAMP WITH TIME ZONE,
    reason_code TEXT,
    error_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_deployment_status ON model_deployment_projection(status);
CREATE INDEX idx_deployment_model ON model_deployment_projection(model_id);
CREATE INDEX idx_deployment_health ON model_deployment_projection(health_status);

-- Documentation comments
COMMENT ON TABLE model_catalog_projection IS 'Read model for model catalog queries';
COMMENT ON TABLE model_deployment_projection IS 'Read model for deployment state queries';

-- Plugin Catalog Projection (for Marketplace)
CREATE TABLE IF NOT EXISTS plugin_catalog_projection (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    developer_id UUID NOT NULL,
    category TEXT NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    is_listed BOOLEAN DEFAULT TRUE,
    listed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Plugin State Projection (for State Manager)
CREATE TABLE IF NOT EXISTS plugin_state_projection (
    plugin_id UUID PRIMARY KEY,
    current_state TEXT NOT NULL,
    last_activity TIMESTAMP WITH TIME ZONE,
    tool_execution_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- License Projection (for Marketplace)
CREATE TABLE IF NOT EXISTS license_projection (
    id UUID PRIMARY KEY,
    plugin_id UUID NOT NULL,
    user_id UUID NOT NULL,
    license_type TEXT NOT NULL,
    expiry_date TIMESTAMP WITH TIME ZONE,
    purchase_date TIMESTAMP WITH TIME ZONE NOT NULL,
    is_expired BOOLEAN DEFAULT FALSE,
    expired_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_license_plugin ON license_projection(plugin_id);
CREATE INDEX idx_license_user ON license_projection(user_id);
CREATE INDEX idx_license_type ON license_projection(license_type);
CREATE INDEX idx_license_expired ON license_projection(is_expired);

-- Gateway Routing Audit Table (for API Gateway)
CREATE TABLE IF NOT EXISTS gateway_routing_audit (
    rule_id UUID PRIMARY KEY,
    path_pattern TEXT NOT NULL,
    target_service TEXT NOT NULL,
    priority INT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_routing_audit_pattern ON gateway_routing_audit(path_pattern);
CREATE INDEX idx_routing_audit_service ON gateway_routing_audit(target_service);