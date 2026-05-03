-- infrastructure/postgres/migrations/001_create_event_store.sql

-- Events Table (Append-Only Log)
CREATE TABLE IF NOT EXISTS minder_events (
    global_offset BIGSERIAL PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    aggregate_version INT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    extra_metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (aggregate_id, aggregate_version)
);

-- Indexes for Event Replay
CREATE INDEX idx_events_replay ON minder_events (aggregate_id, aggregate_version);
CREATE INDEX idx_events_type ON minder_events (event_type);
CREATE INDEX idx_events_global_offset ON minder_events (global_offset);

-- Snapshots Table
CREATE TABLE IF NOT EXISTS minder_snapshots (
    aggregate_id UUID NOT NULL,
    last_event_version INT NOT NULL,
    state JSONB NOT NULL,
    is_major_version BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (aggregate_id, last_event_version)
);

-- Index for Snapshot Loading
CREATE INDEX idx_snapshots_latest ON minder_snapshots (aggregate_id, last_event_version DESC);

-- Index for Retention Policy
CREATE INDEX idx_snapshots_retention ON minder_snapshots (created_at)
WHERE (is_major_version IS FALSE);

-- Outbox Table
CREATE TABLE IF NOT EXISTS minder_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    extra_metadata JSONB DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending',
    retry_count INT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE,

    INDEX idx_outbox_pending (status, created_at)
);