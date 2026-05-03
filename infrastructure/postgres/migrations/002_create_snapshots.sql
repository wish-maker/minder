-- Snapshots table: Aggregate state optimization
-- Stores periodic snapshots to reduce event replay time

CREATE TABLE IF NOT EXISTS snapshots (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Snapshot identification
    aggregate_type VARCHAR(255) NOT NULL,
    aggregate_id UUID NOT NULL,
    version BIGINT NOT NULL,

    -- Snapshot state
    state JSONB NOT NULL,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT snapshots_aggregate_version_unique
        UNIQUE (aggregate_type, aggregate_id, version)
);

-- Indexes for performance
CREATE INDEX idx_snapshots_aggregate ON snapshots(aggregate_type, aggregate_id);
CREATE INDEX idx_snapshots_version ON snapshots(aggregate_type, aggregate_id, version DESC);

-- Comments for documentation
COMMENT ON TABLE snapshots IS 'Aggregate snapshots for Event Sourcing optimization';
COMMENT ON COLUMN snapshots.aggregate_type IS 'Type of aggregate (e.g., Plugin, User)';
COMMENT ON COLUMN snapshots.aggregate_id IS 'Identifier of the aggregate instance';
COMMENT ON COLUMN snapshots.version IS 'Event version up to which snapshot applies';
COMMENT ON COLUMN snapshots.state IS 'Aggregate state as JSONB';
