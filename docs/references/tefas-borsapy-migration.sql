-- Borsapy Integration Migration for TEFAS Module v3.0
-- This migration adds new tables for risk metrics, allocation, tax info, and metadata
-- Existing tables are preserved for backward compatibility

-- Run this migration manually when ready for Phase 2:
-- psql -U postgres -d minder_tefas -f migrations/001_create_borsapy_tables.sql

-- ============================================================================
-- 1. Fund Metadata Table (Enhanced fund information)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tefas_fund_metadata (
    fund_code VARCHAR(20) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    fund_type VARCHAR(10) NOT NULL,  -- YAT, EMK, BYF
    isin VARCHAR(20),
    management_fee DECIMAL(5, 2),     -- Yıllık yönetim ücreti (%)
    prospectus_fee DECIMAL(5, 2),   -- İzahname ücreti (%)
    max_expense_ratio DECIMAL(5, 2), -- Azami toplam gider kesinti (%)
    inception_date DATE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_fund_type CHECK (fund_type IN ('YAT', 'EMK', 'BYF'))
);

-- Create index for fund type queries
CREATE INDEX IF NOT EXISTS idx_fund_metadata_type ON tefas_fund_metadata(fund_type);
CREATE INDEX IF NOT EXISTS idx_fund_metadata_category ON tefas_fund_metadata(category);

-- Comment
COMMENT ON TABLE tefas_fund_metadata IS 'Enhanced fund metadata from borsapy integration';

-- ============================================================================
-- 2. Risk Metrics Table (Sharpe, Sortino, max drawdown, etc.)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tefas_risk_metrics (
    id SERIAL PRIMARY KEY,
    fund_code VARCHAR(20) NOT NULL,
    period VARCHAR(10) NOT NULL,     -- '1y', '3y', '5y'

    -- Risk-adjusted returns
    sharpe_ratio DECIMAL(8, 4),      -- Sharpe ratio (risk-adjusted return)
    sortino_ratio DECIMAL(8, 4),     -- Sortino ratio (downside risk)

    -- Risk metrics
    max_drawdown DECIMAL(8, 4),      -- Maximum peak-to-trough decline (%)
    annualized_volatility DECIMAL(8, 4),  -- Annualized volatility (%)

    -- Return metrics
    annualized_return DECIMAL(8, 4), -- Annualized return (%)
    calmar_ratio DECIMAL(8, 4),      -- Return / max drawdown ratio

    -- Value at Risk (optional, future)
    var_95 DECIMAL(8, 4),            -- Value at Risk at 95% confidence

    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_period CHECK (period IN ('1y', '3y', '5y')),
    CONSTRAINT fk_risk_fund
        FOREIGN KEY (fund_code)
        REFERENCES tefas_fund_metadata(fund_code)
        ON DELETE CASCADE
);

-- Create indexes for efficient queries
CREATE UNIQUE INDEX IF NOT EXISTS idx_risk_metrics_fund_period
    ON tefas_risk_metrics(fund_code, period);
CREATE INDEX IF NOT EXISTS idx_risk_metrics_sharpe
    ON tefas_risk_metrics(sharpe_ratio DESC);
CREATE INDEX IF NOT EXISTS idx_risk_metrics_calculated
    ON tefas_risk_metrics(calculated_at DESC);

-- Comments
COMMENT ON TABLE tefas_risk_metrics IS 'Risk metrics from borsapy: Sharpe, Sortino, max drawdown, volatility';
COMMENT ON COLUMN tefas_risk_metrics.sharpe_ratio IS 'Sharpe ratio: (Return - RiskFree) / Volatility';
COMMENT ON COLUMN tefas_risk_metrics.max_drawdown IS 'Maximum peak-to-trough decline (%)';

-- ============================================================================
-- 3. Asset Allocation Table (Fund portfolio composition)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tefas_allocation (
    id SERIAL PRIMARY KEY,
    fund_code VARCHAR(20) NOT NULL,
    date DATE NOT NULL,

    -- Asset details
    asset_type VARCHAR(50) NOT NULL,  -- Hisse, Tahvil, Eurobond, etc.
    asset_name VARCHAR(100) NOT NULL,  -- Specific asset name
    weight DECIMAL(8, 4) NOT NULL,     -- Portfolio weight (0-1, sum to 1.0 per fund)

    -- Additional info (optional)
    value_usd BIGINT,                 -- Asset value in USD (if applicable)
    count DECIMAL(18, 2),            -- Number of shares/units (if applicable)

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_weight CHECK (weight >= 0 AND weight <= 1),
    CONSTRAINT fk_allocation_fund
        FOREIGN KEY (fund_code)
        REFERENCES tefas_fund_metadata(fund_code)
        ON DELETE CASCADE
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_allocation_fund_date
    ON tefas_allocation(fund_code, date DESC);
CREATE INDEX IF NOT EXISTS idx_allocation_fund_type
    ON tefas_allocation(fund_code, asset_type);
CREATE INDEX IF NOT EXISTS idx_allocation_date
    ON tefas_allocation(date DESC);

-- Comment
COMMENT ON TABLE tefas_allocation IS 'Fund asset allocation from borsapy: portfolio composition over time';

-- ============================================================================
-- 4. Tax Rates Table (Withholding tax by fund category)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tefas_tax_rates (
    id SERIAL PRIMARY KEY,
    fund_code VARCHAR(20) NOT NULL,

    -- Tax classification
    tax_category VARCHAR(50) NOT NULL,  -- degisken_karma_doviz, pay_senedi_yogun, etc.
    effective_date DATE NOT NULL,

    -- Tax rate
    rate DECIMAL(5, 4) NOT NULL,     -- Tax rate (0.175 = %17.5)

    -- Reference
    regulation TEXT,                 -- Applicable regulation (e.g., "Gelir Vergisi Kanunu Geçici 67. Madde")

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_tax_fund
        FOREIGN KEY (fund_code)
        REFERENCES tefas_fund_metadata(fund_code)
        ON DELETE CASCADE,
    CONSTRAINT chk_tax_rate CHECK (rate >= 0 AND rate <= 1)
);

-- Create indexes for efficient queries
CREATE UNIQUE INDEX IF NOT EXISTS idx_tax_fund_date
    ON tefas_tax_rates(fund_code, effective_date);
CREATE INDEX IF NOT EXISTS idx_tax_category
    ON tefas_tax_rates(tax_category);
CREATE INDEX IF NOT EXISTS idx_tax_date
    ON tefas_tax_rates(effective_date DESC);

-- Comment
COMMENT ON TABLE tefas_tax_rates IS 'Withholding tax rates by fund category from borsapy integration';

-- ============================================================================
-- 5. Fund Performance Table (Detailed performance metrics)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tefas_performance (
    id SERIAL PRIMARY KEY,
    fund_code VARCHAR(20) NOT NULL,
    date DATE NOT NULL,

    -- Performance metrics
    daily_return DECIMAL(8, 4),     -- Daily return (%)
    weekly_return DECIMAL(8, 4),    -- Weekly return (%)
    monthly_return DECIMAL(8, 4),   -- Monthly return (%)
    ytd_return DECIMAL(8, 4),       -- Year-to-date return (%)
    return_1y DECIMAL(8, 4),        -- 1-year return (%)
    return_3y DECIMAL(8, 4),        -- 3-year return (%)
    return_5y DECIMAL(8, 4),        -- 5-year return (%)

    -- Benchmark comparison (vs XU100 or XU030)
    benchmark_return_1y DECIMAL(8, 4),  -- Benchmark 1-year return
    excess_return_1y DECIMAL(8, 4),     -- Excess return over benchmark
    tracking_error_1y DECIMAL(8, 4),   -- Tracking error vs benchmark

    -- Volatility
    volatility_1y DECIMAL(8, 4),     -- 1-year volatility (%)

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_performance_fund
        FOREIGN KEY (fund_code)
        REFERENCES tefas_fund_metadata(fund_code)
        ON DELETE CASCADE
);

-- Create indexes for efficient queries
CREATE UNIQUE INDEX IF NOT EXISTS idx_performance_fund_date
    ON tefas_performance(fund_code, date);
CREATE INDEX IF NOT EXISTS idx_performance_date
    ON tefas_performance(date DESC);

-- Comment
COMMENT ON TABLE tefas_performance IS 'Detailed fund performance metrics from borsapy';

-- ============================================================================
-- 6. Technical Indicators Table (RSI, MACD, Bollinger Bands, etc.)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tefas_technical_indicators (
    id SERIAL PRIMARY KEY,
    fund_code VARCHAR(20) NOT NULL,
    date DATE NOT NULL,

    -- RSI (Relative Strength Index)
    rsi_14 DECIMAL(6, 2),           -- 14-period RSI (0-100)
    rsi_7 DECIMAL(6, 2),            -- 7-period RSI (0-100)

    -- MACD (Moving Average Convergence Divergence)
    macd DECIMAL(10, 6),             -- MACD line
    macd_signal DECIMAL(10, 6),      -- Signal line
    macd_histogram DECIMAL(10, 6),   -- MACD histogram

    -- Bollinger Bands
    bb_upper DECIMAL(12, 4),         -- Upper band
    bb_middle DECIMAL(12, 4),        -- Middle band (SMA)
    bb_lower DECIMAL(12, 4),         -- Lower band
    bb_width DECIMAL(8, 4),          -- Band width (%)

    -- Moving Averages
    sma_20 DECIMAL(12, 4),           -- 20-day SMA
    sma_50 DECIMAL(12, 4),           -- 50-day SMA
    ema_12 DECIMAL(12, 4),           -- 12-day EMA
    ema_26 DECIMAL(12, 4),           -- 26-day EMA

    -- Other indicators
    atr_14 DECIMAL(12, 4),           -- Average True Range (14-period)
    stoch_k DECIMAL(6, 2),          -- Stochastic %K
    stoch_d DECIMAL(6, 2),          -- Stochastic %D

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_technical_fund
        FOREIGN KEY (fund_code)
        REFERENCES tefas_fund_metadata(fund_code)
        ON DELETE CASCADE,
    CONSTRAINT chk_rsi_range CHECK (rsi_14 BETWEEN 0 AND 100),
    CONSTRAINT chk_rsi_7_range CHECK (rsi_7 BETWEEN 0 AND 100),
    CONSTRAINT chk_stoch_range CHECK (stoch_k BETWEEN 0 AND 100)
);

-- Create indexes for efficient queries
CREATE UNIQUE INDEX IF NOT EXISTS idx_technical_fund_date
    ON tefas_technical_indicators(fund_code, date);
CREATE INDEX IF NOT EXISTS idx_technical_date
    ON tefas_technical_indicators(date DESC);

-- Comment
COMMENT ON TABLE tefas_technical_indicators IS 'Technical analysis indicators from borsapy: RSI, MACD, Bollinger Bands';

-- ============================================================================
-- 7. Collection Log Table (Track data collection runs)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tefas_collection_log (
    id SERIAL PRIMARY KEY,
    collection_run_id VARCHAR(50) NOT NULL,

    -- Collection details
    feature_name VARCHAR(50) NOT NULL,  -- risk_metrics, allocation, etc.
    status VARCHAR(20) NOT NULL,       -- success, partial, failed
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,

    -- Results
    funds_processed INTEGER,
    records_collected INTEGER,
    records_updated INTEGER,
    errors INTEGER,

    -- Performance metrics
    duration_seconds DECIMAL(8, 3),

    -- Error details
    error_message TEXT,

    CONSTRAINT chk_status CHECK (status IN ('success', 'partial', 'failed'))
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_collection_run
    ON tefas_collection_log(collection_run_id);
CREATE INDEX IF NOT EXISTS idx_collection_feature
    ON tefas_collection_log(feature_name);
CREATE INDEX IF NOT EXISTS idx_collection_status
    ON tefas_collection_log(status);
CREATE INDEX IF NOT EXISTS idx_collection_started
    ON tefas_collection_log(started_at DESC);

-- Comment
COMMENT ON TABLE tefas_collection_log IS 'Data collection run log for tracking and monitoring';

-- ============================================================================
-- 8. Fund Screening Results Table (Cached screening results)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tefas_screening_cache (
    id SERIAL PRIMARY KEY,
    screening_id VARCHAR(50) NOT NULL,  -- Unique ID for screening run

    -- Screening criteria (JSON)
    criteria JSONB NOT NULL,          -- Screening criteria used

    -- Results (fund codes)
    results JSONB NOT NULL,           -- Array of matching fund codes

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,   -- Cache expiration time

    CONSTRAINT chk_criteria_not_empty CHECK (jsonb_array_length(criteria) > 0)
);

-- Create indexes for efficient queries and cleanup
CREATE INDEX IF NOT EXISTS idx_screening_expires
    ON tefas_screening_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_screening_id
    ON tefas_screening_cache(screening_id);

-- Comment
COMMENT ON TABLE tefas_screening_cache IS 'Cached fund screening results for performance';

-- ============================================================================
-- 9. Fund Comparison Results Table (Cached comparison results)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tefas_comparison_cache (
    id SERIAL PRIMARY KEY,
    comparison_id VARCHAR(50) NOT NULL,  -- Unique ID for comparison

    -- Funds being compared
    fund_codes JSONB NOT NULL,        -- Array of fund codes

    -- Comparison results (JSON)
    rankings JSONB,                  -- Ranking by various metrics
    summary JSONB,                    -- Summary statistics

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,   -- Cache expiration time

    CONSTRAINT chk_fund_codes_not_empty CHECK (jsonb_array_length(fund_codes) > 0)
);

-- Create indexes for efficient queries and cleanup
CREATE INDEX IF NOT EXISTS idx_comparison_expires
    ON tefas_comparison_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_comparison_id
    ON tefas_comparison_cache(comparison_id);

-- Comment
COMMENT ON TABLE tefas_comparison_cache IS 'Cached fund comparison results for performance';

-- ============================================================================
-- Migration metadata
-- ============================================================================
CREATE TABLE IF NOT EXISTS tefas_migration_log (
    id SERIAL PRIMARY KEY,
    migration_version VARCHAR(20) NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    status VARCHAR(20) DEFAULT 'success'
);

-- Log this migration
INSERT INTO tefas_migration_log (migration_version, description, status)
VALUES ('001_create_borsapy_tables', 'Create tables for borsapy integration (Phase 1)', 'success');

-- ============================================================================
-- Create views for common queries
-- ============================================================================

-- View: Fund summary with latest metrics
CREATE OR REPLACE VIEW v_fund_summary AS
SELECT
    m.fund_code,
    m.title,
    m.fund_type,
    m.category,
    COALESCE(p.return_1y, 0) as return_1y,
    COALESCE(r.sharpe_ratio, NULL) as sharpe_ratio_1y,
    COALESCE(r.max_drawdown, NULL) as max_drawdown_1y,
    m.updated_at as last_updated
FROM tefas_fund_metadata m
LEFT JOIN tefas_performance p ON p.fund_code = m.fund_code AND p.date = (
    SELECT MAX(date) FROM tefas_performance WHERE fund_code = m.fund_code
)
LEFT JOIN tefas_risk_metrics r ON r.fund_code = m.fund_code AND r.period = '1y';

COMMENT ON VIEW v_fund_summary IS 'Fund summary with latest performance and risk metrics';

-- View: Latest asset allocation by fund type
CREATE OR REPLACE VIEW v_latest_allocation AS
SELECT
    fund_code,
    asset_type,
    SUM(weight) as total_weight,
    COUNT(DISTINCT date) as data_points,
    MAX(date) as latest_date
FROM tefas_allocation
GROUP BY fund_code, asset_type
HAVING MAX(date) >= CURRENT_DATE - INTERVAL '30 days';

COMMENT ON VIEW v_latest_allocation IS 'Latest asset allocation by fund type (last 30 days)';

-- ============================================================================
-- Grant permissions (if needed)
-- ============================================================================
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO minder_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO minder_user;

-- ============================================================================
-- Migration complete
-- ============================================================================
SELECT 'Migration 001_create_borsapy_tables completed successfully!' as status;

-- Tables created:
-- 1. tefas_fund_metadata (enhanced fund info)
-- 2. tefas_risk_metrics (Sharpe, Sortino, max drawdown)
-- 3. tefas_allocation (asset allocation)
-- 4. tefas_tax_rates (withholding tax)
-- 5. tefas_performance (detailed performance)
-- 6. tefas_technical_indicators (RSI, MACD, BB)
-- 7. tefas_collection_log (data collection tracking)
-- 8. tefas_screening_cache (screening results cache)
-- 9. tefas_comparison_cache (comparison results cache)

-- Views created:
-- 1. v_fund_summary (fund summary with latest metrics)
-- 2. v_latest_allocation (latest allocation by fund type)

-- Next steps:
-- 1. Test migration: SELECT * FROM tefas_fund_metadata LIMIT 5;
-- 2. Update permissions if needed
-- 3. Create indexes on existing tefas_funds table for foreign keys
-- 4. Back up existing data before migration
