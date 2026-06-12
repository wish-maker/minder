#!/bin/bash
set -e

# Read password from secret
if [ -f /run/secrets/rabbitmq_password ]; then
    RABBITMQ_PASSWORD=$(cat /run/secrets/rabbitmq_password)
else
    echo "ERROR: RabbitMQ password secret not found!"
    exit 1
fi

# Set the password as environment variable
export RABBITMQ_DEFAULT_PASS="$RABBITMQ_PASSWORD"

# Start RabbitMQ with default arguments
exec /usr/local/bin/docker-entrypoint.sh rabbitmq-server
