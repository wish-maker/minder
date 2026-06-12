#!/bin/bash
set -e

# Start Ollama server in background
echo "Starting Ollama server..."
/usr/bin/ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama to start..."
while ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done
echo "Ollama is ready"

# Run init script if exists
if [ -f /docker-entrypoint-initdb.d/init-models.sh ]; then
    echo "Running automatic model download..."
    /bin/bash /docker-entrypoint-initdb.d/init-models.sh
fi

# Keep container running
echo "Ollama server running (PID: $OLLAMA_PID)"
wait $OLLAMA_PID
