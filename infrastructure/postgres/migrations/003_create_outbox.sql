-- Outbox table for reliable event publishing
-- Ensures atomicity between business transactions and event publishing

CREATE TABLE IF NOT EXISTS outbox (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Event identification
    event_id UUID NOT NULL UNIQUE,
    event_type VARCHAR(255) NOT NULL,

    -- Event payload
    payload JSONB NOT NULL,

    -- Publishing status
    status VARCHAR(50) NOT NULL DEFAULT 'pending',

    -- Metadata
    aggregate_type VARCHAR(255),
    aggregate_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    published_at TIMESTAMP WITH TIME ZONE,

    -- Retry tracking
    retry_count INT DEFAULT 0,
    error_message TEXT
);

-- Indexes for efficient polling
CREATE INDEX idx_outbox_status_created ON outbox(status, created_at)
WHERE status = 'pending';

CREATE INDEX idx_outbox_aggregate ON outbox(aggregate_type, aggregate_id)
WHERE aggregate_type IS NOT NULL;

-- Comments for documentation
COMMENT ON TABLE outbox IS 'Outbox pattern for reliable event publishing';
COMMENT ON COLUMN outbox.status IS 'pending, published, or failed';
COMMENT ON COLUMN outbox.published_at IS 'Set when successfully published';
COMMENT ON COLUMN outbox.retry_count IS 'Number of retry attempts';
COMMENT ON COLUMN outbox.error_message IS 'Error details if publishing failed';
