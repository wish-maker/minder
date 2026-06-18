#!/bin/bash
###############################################################################
# Ollama Docker Entrypoint for Minder Platform
# This script starts Ollama and runs the model initialization script
###############################################################################

set -e

# Start Ollama server in background
/usr/bin/ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready using TCP check (curl not available in image)
echo "Waiting for Ollama to start..."
while ! timeout 5 bash -c '</dev/tcp/127.0.0.1/11434' 2>/dev/null; do
    echo "Ollama not ready yet, waiting..."
    sleep 2
done

echo "Ollama is ready"

# Run init script if exists
if [ -f /docker-entrypoint-initdb.d/init-models.sh ]; then
    echo "Running automatic model download..."
    /bin/bash /docker-entrypoint-initdb.d/init-models.sh
fi

# Keep container running
wait $OLLAMA_PID
