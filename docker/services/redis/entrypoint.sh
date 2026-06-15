#!/bin/bash
set -e

# Read password from secret
if [ -f /run/secrets/redis_password ]; then
    REDIS_PASSWORD=$(cat /run/secrets/redis_password)
else
    echo "ERROR: Redis password secret not found!"
    exit 1
fi

# Start Redis with the password from secret
exec redis-server \
    --appendonly yes \
    --requirepass "$REDIS_PASSWORD" \
    --masterauth "$REDIS_PASSWORD" \
    "$@"
