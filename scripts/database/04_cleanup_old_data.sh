#!/bin/bash
###############################################################################
# Minder Database Cleanup Script
# Version: 1.0.0
# Description: Removes old data from databases to save disk space
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

# Retention policies (days)
RETENTION_NEWS="${RETENTION_NEWS:-90}"      # Keep news for 90 days
RETENTION_WEATHER="${RETENTION_WEATHER:-30}" # Keep weather for 30 days
RETENTION_CRYPTO="${RETENTION_CRYPTO:-60}"  # Keep crypto for 60 days
RETENTION_NETWORK="${RETENTION_NETWORK:-7}" # Keep network metrics for 7 days
RETENTION_TEFAS="${RETENTION_TEFAS:-365}"   # Keep TEFAS for 1 year

if [ -z "$POSTGRES_PASSWORD" ]; then
    echo -e "${RED}Error: POSTGRES_PASSWORD environment variable not set${NC}"
    exit 1
fi

echo -e "${YELLOW}=== Minder Database Cleanup ===${NC}"
echo "Retention policies:"
echo "  News: $RETENTION_NEWS days"
echo "  Weather: $RETENTION_WEATHER days"
echo "  Crypto: $RETENTION_CRYPTO days"
echo "  Network: $RETENTION_NETWORK days"
echo "  TEFAS: $RETENTION_TEFAS days"
echo ""

# Export PGPASSWORD
export PGPASSWORD="$POSTGRES_PASSWORD"

# Confirm cleanup
read -p "$(echo -e ${RED}This will DELETE old data. Continue? (yes/no): ${NC})" confirm

if [ "$confirm" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo ""
echo -e "${YELLOW}Cleaning up old data...${NC}"

# News cleanup
echo -n "  Cleaning news articles older than $RETENTION_NEWS days... "
deleted=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d minder_news -t -c \
    "DELETE FROM news_articles WHERE timestamp < NOW() - INTERVAL '$RETENTION_NEWS days';")
echo -e "${GREEN}✓ $deleted records deleted${NC}"

# Weather cleanup
echo -n "  Cleaning weather data older than $RETENTION_WEATHER days... "
deleted=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d minder_weather -t -c \
    "DELETE FROM weather_data WHERE timestamp < NOW() - INTERVAL '$RETENTION_WEATHER days';")
echo -e "${GREEN}✓ $deleted records deleted${NC}"

# Crypto cleanup
echo -n "  Cleaning crypto data older than $RETENTION_CRYPTO days... "
deleted=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d minder_crypto -t -c \
    "DELETE FROM crypto_data WHERE timestamp < NOW() - INTERVAL '$RETENTION_CRYPTO days';")
echo -e "${GREEN}✓ $deleted records deleted${NC}"

# Network cleanup
echo -n "  Cleaning network metrics older than $RETENTION_NETWORK days... "
deleted=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d minder_network -t -c \
    "DELETE FROM network_metrics WHERE timestamp < NOW() - INTERVAL '$RETENTION_NETWORK days';")
echo -e "${GREEN}✓ $deleted records deleted${NC}"

# TEFAS cleanup (keep longer)
echo -n "  Cleaning TEFAS data older than $RETENTION_TEFAS days... "
deleted=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d fundmind -t -c \
    "DELETE FROM tefas_fund_data WHERE timestamp < NOW() - INTERVAL '$RETENTION_TEFAS days';")
echo -e "${GREEN}✓ $deleted records deleted${NC}"

echo ""

# Vacuum databases to reclaim space
echo -e "${YELLOW}Vacuuming databases to reclaim space...${NC}"

databases=("fundmind" "minder_news" "minder_weather" "minder_crypto" "minder_network")

for db in "${databases[@]}"; do
    echo -n "  Vacuuming '$db'... "
    psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$db" -c "VACUUM ANALYZE;" > /dev/null 2>&1
    echo -e "${GREEN}✓${NC}"
done

echo ""
echo -e "${GREEN}=== Cleanup Complete ===${NC}"
echo "Old data removed and databases vacuumed."
echo ""

# Unset PGPASSWORD
unset PGPASSWORD
