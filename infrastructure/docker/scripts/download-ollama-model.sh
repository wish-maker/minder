#!/bin/bash
# Download llama3.2 model for Ollama

set -e

echo "🤖 Downloading llama3.2 model for Ollama..."

# Check if Ollama container is running
if ! docker ps | grep -q "minder-ollama"; then
    echo "❌ Error: Ollama container not running"
    echo "Start it with: docker compose up -d ollama"
    exit 1
fi

# Pull llama3.2 model
echo "📥 Pulling llama3.2 model..."
docker exec minder-ollama ollama pull llama3.2

# Verify model is available
echo "🔍 Verifying model installation..."
if docker exec minder-ollama ollama list | grep -q "llama3.2"; then
    echo "✅ llama3.2 model successfully installed"
    docker exec minder-ollama ollama list
else
    echo "❌ Error: llama3.2 model not found after download"
    exit 1
fi

echo "🎉 Model download complete!"
