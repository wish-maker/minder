-- Integration tests for Event Store schema

-- Test 1: Insert and retrieve event
INSERT INTO events (
    event_id, event_type, timestamp,
    aggregate_type, aggregate_id, version, data
) VALUES (
    '123e4567-e89b-12d3-a456-426614174000'::UUID,
    'PluginRegistered',
    '2026-05-03T12:00:00Z'::TIMESTAMP WITH TIME ZONE,
    'Plugin',
    '123e4567-e89b-12d3-a456-426614174001'::UUID,
    1,
    '{"plugin_id": "crypto", "version": "1.0.0"}'::JSONB
);

-- Verify insert
SELECT COUNT(*) FROM events WHERE event_type = 'PluginRegistered';
-- Expected: 1

-- Test 2: Verify version constraint (should fail)
-- This should violate the unique constraint
INSERT INTO events (
    event_id, event_type, timestamp,
    aggregate_type, aggregate_id, version, data
) VALUES (
    '223e4567-e89b-12d3-a456-426614174002'::UUID,
    'PluginStateChanged',
    '2026-05-03T12:01:00Z'::TIMESTAMP WITH TIME ZONE,
    'Plugin',
    '123e4567-e89b-12d3-a456-426614174001'::UUID,
    1,  -- Duplicate version!
    '{"state": "active"}'::JSONB
);
-- Expected: ERROR - violates unique constraint

-- Test 3: Insert snapshot
INSERT INTO snapshots (
    aggregate_type, aggregate_id, version, state
) VALUES (
    'Plugin',
    '123e4567-e89b-12d3-a456-426614174001'::UUID,
    100,
    '{"plugin_id": "crypto", "state": "active", "version": "1.0.0"}'::JSONB
);

-- Verify snapshot
SELECT COUNT(*) FROM snapshots
WHERE aggregate_type = 'Plugin' AND version = 100;
-- Expected: 1

-- Test 4: Verify indexes
-- Check if indexes exist
SELECT indexname
FROM pg_indexes
WHERE tablename = 'events';
-- Expected: 5 indexes (events_aggregate_version_unique + 4 user indexes)

SELECT indexname
FROM pg_indexes
WHERE tablename = 'snapshots';
-- Expected: 3 indexes (snapshots_aggregate_version_unique + 2 user indexes)

-- Cleanup
DELETE FROM events WHERE event_id = '123e4567-e89b-12d3-a456-426614174000'::UUID;
DELETE FROM snapshots WHERE aggregate_id = '123e4567-e89b-12d3-a456-426614174001'::UUID;
