#!/bin/bash
###############################################################################
# Minder Database Initialization Script
# Version: 1.0.0
# Description: Creates all databases and required tables for Minder platform
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

if [ -z "$POSTGRES_PASSWORD" ]; then
    echo -e "${RED}Error: POSTGRES_PASSWORD environment variable not set${NC}"
    exit 1
fi

echo -e "${GREEN}=== Minder Database Initialization ===${NC}"
echo "Host: $POSTGRES_HOST:$POSTGRES_PORT"
echo "User: $POSTGRES_USER"
echo ""

# Export PGPASSWORD for non-interactive psql
export PGPASSWORD="$POSTGRES_PASSWORD"

###############################################################################
# 1. Create Databases
###############################################################################

echo -e "${YELLOW}Step 1: Creating databases...${NC}"

databases=(
    "fundmind"
    "minder_news"
    "minder_weather"
    "minder_crypto"
    "minder_network"
)

for db in "${databases[@]}"; do
    echo -n "  Creating database '$db'... "
    if psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -tc "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1; then
        echo -e "${YELLOW}already exists${NC}"
    else
        createdb -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$db"
        echo -e "${GREEN}✓ created${NC}"
    fi
done

echo ""

###############################################################################
# 2. Create Tables
###############################################################################

echo -e "${YELLOW}Step 2: Creating tables...${NC}"

# FundMind Database (TEFAS)
echo -n "  Creating fundmind tables... "
psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d fundmind << 'EOF' > /dev/null 2>&1
-- TEFAS fund data table
CREATE TABLE IF NOT EXISTS tefas_fund_data (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL,
    title VARCHAR(255),
    date DATE NOT NULL,
    price DECIMAL(15, 4),
    market_cap DECIMAL(20, 2),
    number_of_shares DECIMAL(20, 2),
    number_of_investors DEC(20, 2),
    bank_bills DECIMAL(10, 2),
    government_bond DECIMAL(10, 2),
    stock DECIMAL(10, 2),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, date)
);

CREATE INDEX IF NOT EXISTS idx_tefas_code ON tefas_fund_data(code);
CREATE INDEX IF NOT EXISTS idx_tefas_date ON tefas_fund_data(date);
EOF
echo -e "${GREEN}✓${NC}"

# News Database
echo -n "  Creating minder_news tables... "
psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d minder_news << 'EOF' > /dev/null 2>&1
-- News articles table
CREATE TABLE IF NOT EXISTS news_articles (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    source VARCHAR(100) NOT NULL,
    url TEXT,
    summary TEXT,
    sentiment_score DECIMAL(5, 4),
    published_date TIMESTAMP,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_news_source ON news_articles(source);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_articles(published_date);
CREATE INDEX IF NOT EXISTS idx_news_timestamp ON news_articles(timestamp);
EOF
echo -e "${GREEN}✓${NC}"

# Weather Database
echo -n "  Creating minder_weather tables... "
psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d minder_weather << 'EOF' > /dev/null 2>&1
-- Weather data table
CREATE TABLE IF NOT EXISTS weather_data (
    id SERIAL PRIMARY KEY,
    location VARCHAR(100) NOT NULL,
    temperature_c DECIMAL(5, 2),
    humidity_pct INTEGER,
    pressure_hpa DECIMAL(7, 2),
    wind_speed_kmh DECIMAL(6, 2),
    weather_description VARCHAR(100),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_weather_location ON weather_data(location);
CREATE INDEX IF NOT EXISTS idx_weather_timestamp ON weather_data(timestamp);
EOF
echo -e "${GREEN}✓${NC}"

# Crypto Database
echo -n "  Creating minder_crypto tables... "
psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d minder_crypto << 'EOF' > /dev/null 2>&1
-- Crypto data table
CREATE TABLE IF NOT EXISTS crypto_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(100),
    price DECIMAL(20, 8),
    market_cap DECIMAL(30, 2),
    volume_24h DECIMAL(30, 2),
    change_24h_pct DECIMAL(10, 4),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_crypto_symbol ON crypto_data(symbol);
CREATE INDEX IF NOT EXISTS idx_crypto_timestamp ON crypto_data(timestamp);
EOF
echo -e "${GREEN}✓${NC}"

# Network Database
echo -n "  Creating minder_network tables... "
psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d minder_network << 'EOF' > /dev/null 2>&1
-- Network metrics table
CREATE TABLE IF NOT EXISTS network_metrics (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(20, 4),
    hostname VARCHAR(255),
    interface VARCHAR(50),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_network_metric ON network_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_network_timestamp ON network_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_network_hostname ON network_metrics(hostname);
EOF
echo -e "${GREEN}✓${NC}"

echo ""

###############################################################################
# 3. Verify Tables
###############################################################################

echo -e "${YELLOW}Step 3: Verifying tables...${NC}"

for db in "${databases[@]}"; do
    echo -n "  Checking '$db' tables... "
    table_count=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$db" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
    echo -e "${GREEN}$table_count tables${NC}"
done

echo ""

###############################################################################
# 4. Grant Permissions (if needed)
###############################################################################

echo -e "${YELLOW}Step 4: Granting permissions...${NC}"
psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d fundmind << 'EOF' > /dev/null 2>&1
-- Grant all permissions on all tables to the postgres user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
EOF
echo -e "${GREEN}✓ Permissions granted${NC}"

echo ""
echo -e "${GREEN}=== Database Initialization Complete ===${NC}"
echo -e "${GREEN}All databases and tables created successfully!${NC}"
echo ""
echo "Next steps:"
echo "  1. Load sample data (optional): ./scripts/database/02_load_sample_data.sh"
echo "  2. Run the application: docker-compose up -d"
echo "  3. Verify data collection: ./scripts/database/05_verify_data.sh"
echo ""

# Unset PGPASSWORD for security
unset PGPASSWORD
