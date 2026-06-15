#!/bin/bash
# ============================================================================
# Authelia Secret Loader Entrypoint
# ============================================================================
# This entrypoint reads secrets from Docker secret files and exports them
# as environment variables before starting Authelia.
# ============================================================================

set -e

# Read secrets from files if they exist, otherwise use environment variables
if [ -f /run/secrets/authelia_storage_encryption_key ]; then
    export AUTHELIA_STORAGE_ENCRYPTION_KEY=$(cat /run/secrets/authelia_storage_encryption_key)
fi

if [ -f /run/secrets/authelia_jwt_secret ]; then
    export AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET=$(cat /run/secrets/authelia_jwt_secret)
fi

if [ -f /run/secrets/postgres_password ]; then
    export AUTHELIA_STORAGE_POSTGRES_PASSWORD=$(cat /run/secrets/postgres_password)
fi

# Start Authelia with the original command
exec /authelia --config /config/configuration.yml "$@"
