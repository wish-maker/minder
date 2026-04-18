#!/bin/bash
###############################################################################
# Minder Data Verification Script
# Version: 1.0.0
# Description: Verifies data collection is working correctly
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

if [ -z "$POSTGRES_PASSWORD" ]; then
    echo -e "${RED}Error: POSTGRES_PASSWORD environment variable not set${NC}"
    exit 1
fi

echo -e "${GREEN}=== Minder Data Verification ===${NC}"
echo "Host: $POSTGRES_HOST:$POSTGRES_PORT"
echo ""

# Export PGPASSWORD
export PGPASSWORD="$POSTGRES_PASSWORD"

# Verify each database
databases=(
    "fundmind:tefas_fund_data:TEFAS Fund Data"
    "minder_news:news_articles:News Articles"
    "minder_weather:weather_data:Weather Data"
    "minder_crypto:crypto_data:Crypto Prices"
    "minder_network:network_metrics:Network Metrics"
)

all_passed=true

for db_info in "${databases[@]}"; do
    IFS=':' read -r db table description <<< "$db_info"

    echo -e "${YELLOW}Verifying $description...${NC}"

    # Check if database exists
    db_exists=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -tc \
        "SELECT 1 FROM pg_database WHERE datname = '$db'" 2>/dev/null | head -1)

    if [ "$db_exists" != "1" ]; then
        echo -e "  ${RED}✗ Database '$db' does not exist${NC}"
        all_passed=false
        continue
    fi

    # Check if table exists
    table_exists=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$db" -tc \
        "SELECT 1 FROM information_schema.tables WHERE table_name = '$table'" 2>/dev/null | head -1)

    if [ "$table_exists" != "1" ]; then
        echo -e "  ${RED}✗ Table '$table' does not exist${NC}"
        all_passed=false
        continue
    fi

    # Count records
    count=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$db" -t -c \
        "SELECT COUNT(*) FROM $table;" 2>/dev/null | tr -d ' ')

    # Check latest timestamp
    latest=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$db" -t -c \
        "SELECT MAX(timestamp) FROM $table;" 2>/dev/null | tr -d ' ')

    # Determine data freshness
    if [ -n "$latest" ] && [ "$latest" != "NULL" ]; then
        # Calculate age in hours
        latest_epoch=$(date -d "$latest" +%s 2>/dev/null || echo "0")
        current_epoch=$(date +%s)
        age_hours=$(( (current_epoch - latest_epoch) / 3600 ))

        if [ $age_hours -lt 1 ]; then
            freshness="${GREEN}Fresh (< 1 hour)${NC}"
        elif [ $age_hours -lt 24 ]; then
            freshness="${YELLOW}Moderate ($age_hours hours)${NC}"
        else
            freshness="${RED}Stale ($age_hours hours)${NC}"
        fi
    else
        freshness="${RED}No data${NC}"
    fi

    # Print result
    if [ "$count" -gt 0 ]; then
        echo -e "  ${GREEN}✓ $count records${NC} | Latest: $latest | $freshness"
    else
        echo -e "  ${YELLOW}⚠ No records (data collection may not have run yet)${NC}"
    fi

    echo ""
done

# Overall result
echo -e "${YELLOW}=== Summary ===${NC}"

if [ "$all_passed" = true ]; then
    echo -e "${GREEN}✓ All databases and tables exist${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. If no data: Run data collection manually or wait for scheduled jobs"
    echo "  2. If stale: Check plugin health logs"
    echo "  3. View data: Connect to database and run SELECT queries"
    exit 0
else
    echo -e "${RED}✗ Some databases or tables are missing${NC}"
    echo ""
    echo "Fix: Run ./scripts/database/01_init_databases.sh"
    exit 1
fi

# Unset PGPASSWORD
unset PGPASSWORD
