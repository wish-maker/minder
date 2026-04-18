-- Minder Plugin-Specific Database Initialization
-- Creates separate databases for each plugin to avoid chaos

-- Create plugin-specific databases
CREATE DATABASE minder_news;
CREATE DATABASE minder_tefas;
CREATE DATABASE minder_weather;
CREATE DATABASE minder_crypto;
CREATE DATABASE minder_network;

-- Grant permissions to postgres user
GRANT ALL PRIVILEGES ON DATABASE minder_news TO postgres;
GRANT ALL PRIVILEGES ON DATABASE minder_tefas TO postgres;
GRANT ALL PRIVILEGES ON DATABASE minder_weather TO postgres;
GRANT ALL PRIVILEGES ON DATABASE minder_crypto TO postgres;
GRANT ALL PRIVILEGES ON DATABASE minder_network TO postgres;

-- Create schemas and tables for each database

-- News database schema
\c minder_news
CREATE TABLE IF NOT EXISTS news_articles (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    source VARCHAR(100) NOT NULL,
    url VARCHAR(1000),
    summary TEXT,
    sentiment_score FLOAT,
    published_date TIMESTAMP,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- TEFAS database schema
\c minder_tefas

-- Main TEFAS fund data table (used by tefas_module.py)
CREATE TABLE IF NOT EXISTS tefas_fund_data (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL,
    title TEXT NOT NULL,  -- Changed from VARCHAR(10) to TEXT for long fund names
    date DATE NOT NULL,
    price DECIMAL(12, 4),
    market_cap BIGINT,
    number_of_shares BIGINT,
    number_of_investors BIGINT,
    bank_bills DECIMAL(8, 4),
    government_bond DECIMAL(8, 4),
    stock DECIMAL(8, 4),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, date)
);

-- Legacy TEFAS funds table (kept for compatibility)
CREATE TABLE IF NOT EXISTS tefas_funds (
    id SERIAL PRIMARY KEY,
    fund_code VARCHAR(20) NOT NULL,
    fund_name VARCHAR(255) NOT NULL,
    price DECIMAL(12, 4),
    date DATE NOT NULL,
    volume BIGINT,
    daily_return DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fund_code, date)
);

-- Weather database schema
\c minder_weather
CREATE TABLE IF NOT EXISTS weather_data (
    id SERIAL PRIMARY KEY,
    location VARCHAR(50) NOT NULL,
    temperature_c FLOAT,
    humidity_pct INTEGER,
    pressure_hpa INTEGER,
    wind_speed_kmh FLOAT,
    weather_description VARCHAR(100),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Crypto database schema
\c minder_crypto
CREATE TABLE IF NOT EXISTS crypto_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    name VARCHAR(100) NOT NULL,
    price_usd DECIMAL(18, 8),
    market_cap_usd BIGINT,
    volume_24h_usd BIGINT,
    price_change_24h_pct FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Network database schema
\c minder_network
CREATE TABLE IF NOT EXISTS network_stats (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(50) NOT NULL,
    metric_value FLOAT NOT NULL,
    hostname VARCHAR(100),
    interface VARCHAR(50),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Log successful initialization
SELECT 'Minder databases initialized successfully!' as status;