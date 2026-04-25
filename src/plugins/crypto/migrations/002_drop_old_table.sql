-- Crypto Plugin Migration: Drop Old Table
-- After verifying crypto_data_history is working, drop the old table

-- Step 1: Verify new table has data
DO $$
BEGIN
    IF (SELECT COUNT(*) FROM crypto_data_history) = 0 THEN
        RAISE EXCEPTION 'Cannot drop crypto_data: crypto_data_history is empty!';
    END IF;

    IF (SELECT COUNT(*) FROM crypto_data_history) < (SELECT COUNT(*) FROM crypto_data) THEN
        RAISE EXCEPTION 'Cannot drop crypto_data: crypto_data_history has fewer records!';
    END IF;
END $$;

-- Step 2: Drop old table
DROP TABLE IF EXISTS crypto_data CASCADE;

-- Step 3: Add comment
COMMENT ON TABLE crypto_data_history IS 'Time-series cryptocurrency price data (replaced old crypto_data table)';
