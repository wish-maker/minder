-- Event Store Schema for Event Sourcing
-- This stores ALL domain events in append-only log

-- Enable UUID extension if not exists
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Events table: Append-only event log
CREATE TABLE IF NOT EXISTS events (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Event identification
    event_id UUID NOT NULL UNIQUE,
    event_type VARCHAR(255) NOT NULL,

    -- Event metadata
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    correlation_id UUID,
    causation_id UUID,
    user_id VARCHAR(255),
    trace_id VARCHAR(255),

    -- Event payload
    data JSONB NOT NULL,

    -- Aggregation info (for event replay)
    aggregate_type VARCHAR(255) NOT NULL,
    aggregate_id UUID NOT NULL,
    version BIGINT NOT NULL,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT events_aggregate_version_unique
        UNIQUE (aggregate_type, aggregate_id, version)
);

-- Indexes for performance
CREATE INDEX idx_events_event_type ON events(event_type);
CREATE INDEX idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX idx_events_aggregate ON events(aggregate_type, aggregate_id);
CREATE INDEX idx_events_correlation_id ON events(correlation_id) WHERE correlation_id IS NOT NULL;
CREATE INDEX idx_events_trace_id ON events(trace_id) WHERE trace_id IS NOT NULL;

-- Comments for documentation
COMMENT ON TABLE events IS 'Append-only event log for Event Sourcing';
COMMENT ON COLUMN events.event_id IS 'Unique identifier for this event instance';
COMMENT ON COLUMN events.event_type IS 'Type name of the event (e.g., PluginRegistered)';
COMMENT ON COLUMN events.aggregate_type IS 'Type of aggregate (e.g., Plugin, User)';
COMMENT ON COLUMN events.aggregate_id IS 'Identifier of the aggregate instance';
COMMENT ON COLUMN events.version IS 'Optimistic locking version for aggregate';
COMMENT ON COLUMN events.data IS 'Event payload as JSONB';
COMMENT ON COLUMN events.correlation_id IS 'Links multiple events in a workflow';
COMMENT ON COLUMN events.causation_id IS 'Links this event to the command that caused it';
