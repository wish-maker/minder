-- infrastructure/postgres/migrations/003_create_idempotency_store.sql

-- Processed Events Table (Idempotency Tracking)
CREATE TABLE IF NOT EXISTS minder_processed_events (
    event_id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_id UUID NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    handler_name TEXT NOT NULL,
    processing_duration_ms INT
);

-- Index for processed events
CREATE INDEX idx_processed_events_handler ON minder_processed_events(handler_name, processed_at DESC);