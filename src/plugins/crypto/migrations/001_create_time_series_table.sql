-- Crypto Plugin Time-Series Migration
-- Fixes duplicate key issue by adding timestamp to primary key

-- Step 1: Create new time-series table
CREATE TABLE IF NOT EXISTS crypto_data_history (
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(100),
    price NUMERIC(18,4),
    market_cap BIGINT,
    volume_24h BIGINT,
    change_24h_pct NUMERIC(8,4),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol, timestamp)
);

-- Step 2: Create index for faster queries by symbol only
CREATE INDEX IF NOT EXISTS idx_crypto_data_history_symbol ON crypto_data_history(symbol, timestamp DESC);

-- Step 3: Create index for latest price queries
CREATE INDEX IF NOT EXISTS idx_crypto_data_history_latest ON crypto_data_history(symbol, timestamp DESC);

-- Step 4: Migrate existing data from old table
INSERT INTO crypto_data_history (symbol, name, price, market_cap, volume_24h, change_24h_pct, timestamp)
SELECT
    symbol,
    name,
    price,
    market_cap,
    volume_24h,
    change_24h_pct,
    timestamp::timestamptz
FROM crypto_data
ON CONFLICT (symbol, timestamp) DO NOTHING;

-- Step 5: Create view for latest prices (convenience)
CREATE OR REPLACE VIEW v_crypto_latest AS
SELECT DISTINCT ON (symbol)
    symbol,
    name,
    price,
    market_cap,
    volume_24h,
    change_24h_pct,
    timestamp
FROM crypto_data_history
ORDER BY symbol, timestamp DESC;

-- Step 6: Add comment for documentation
COMMENT ON TABLE crypto_data_history IS 'Time-series cryptocurrency price data with composite primary key (symbol, timestamp)';
COMMENT ON VIEW v_crypto_latest IS 'Latest cryptocurrency prices - convenience view for current prices';
