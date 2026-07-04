#!/bin/bash
###############################################################################
# Ollama Model Auto-Download Script for Minder Platform
# This script is automatically executed on container startup if OLLAMA_AUTOMATIC_PULL=true
# NOTE: Uses bash TCP checks and ollama CLI (curl not available in ollama image)
###############################################################################

set -e

# Check for remote Ollama mode
# If OLLAMA_BASE_URL is set, we're using a remote host - skip auto-pull
if [ -n "$OLLAMA_BASE_URL" ]; then
    echo "========================================"
    echo "REMOTE OLLAMA MODE DETECTED"
    echo "OLLAMA_BASE_URL is set to: $OLLAMA_BASE_URL"
    echo "Skipping model auto-pull (cannot pull to remote host)"
    echo "========================================"
    exit 0
fi

# Wait for Ollama service to be ready (using TCP check)
echo "Waiting for Ollama service to be ready..."
while ! timeout 5 bash -c '</dev/tcp/127.0.0.1/11434' 2>/dev/null; do
    echo "Ollama not ready yet, waiting..."
    sleep 3
done

echo "Ollama is ready. Checking required models..."

# Get models from environment or use defaults.
# NOTE: read OLLAMA_PULL_MODELS, NOT OLLAMA_MODELS — the ollama server treats
# OLLAMA_MODELS as its model STORAGE DIRECTORY, so passing a model list in it
# made ollama store models outside the volume (see #29). The compose maps the
# host's model list into the container under this non-colliding name.
OLLAMA_PULL_MODELS="${OLLAMA_PULL_MODELS:-llama3.2,nomic-embed-text}"
OLLAMA_AUTOMATIC_PULL="${OLLAMA_AUTOMATIC_PULL:-true}"

echo "Required models: $OLLAMA_PULL_MODELS"
echo "Auto-pull enabled: $OLLAMA_AUTOMATIC_PULL"

if [ "$OLLAMA_AUTOMATIC_PULL" = "true" ]; then
    echo "Auto-pulling required models..."

    # Parse comma-separated models using a loop (more portable than read -ra)
    # Save original IFS
    OLD_IFS="$IFS"
    IFS=','
    for MODEL in $OLLAMA_PULL_MODELS; do
        # Trim whitespace from model name
        MODEL=$(echo "$MODEL" | xargs)

        echo "Checking model: $MODEL"

        # Check if model already exists using ollama CLI
        # Ollama auto-adds :latest if not specified, so we check with :latest
        if ollama list 2>/dev/null | grep -q "${MODEL}:latest"; then
            echo "✅ Model ${MODEL}:latest already exists, skipping download"
        else
            echo "❌ Model ${MODEL}:latest not found, pulling..."
            echo "Pulling ${MODEL}:latest (this may take a while for large models)..."

            # Pull the model (Ollama auto-adds :latest tag)
            ollama pull "$MODEL"

            if [ $? -eq 0 ]; then
                echo "✅ Successfully pulled $MODEL"
            else
                echo "❌ Failed to pull $MODEL"
                exit 1
            fi
        fi
    done
    # Restore original IFS
    IFS="$OLD_IFS"

    echo "✅ All required models are available"
else
    echo "Auto-pull disabled, skipping model downloads"
fi

echo "Ollama model initialization complete!"
echo "Available models:"
ollama list
