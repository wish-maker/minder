#!/bin/bash
###############################################################################
# Ollama Automatic Model Download Script
# Purpose: Download default models on first startup
###############################################################################

set -e

# Default models to download
DEFAULT_MODELS=("llama3.2" "nomic-embed-text")

# Get models from environment or use defaults
if [ -n "$OLLAMA_MODELS" ]; then
    IFS=',' read -ra MODELS <<< "$OLLAMA_MODELS"
else
    MODELS=("${DEFAULT_MODELS[@]}")
fi

echo "═══════════════════════════════════════════════════════════════"
echo "     Ollama Automatic Model Download Script"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Check if automatic pull is enabled
if [ "$OLLAMA_AUTOMATIC_PULL" != "true" ]; then
    echo "ℹ️  OLLAMA_AUTOMATIC_PULL is not set to 'true'"
    echo "   Skipping automatic model download"
    echo "   To enable: Set OLLAMA_AUTOMATIC_PULL=true in environment"
    exit 0
fi

echo "🔍 Checking for existing models..."
EXISTING_MODELS=$(ollama list 2>/dev/null | grep -c "NAME" || echo "0")

if [ "$EXISTING_MODELS" -gt 0 ]; then
    echo "✓ Found $EXISTING_MODELS existing model(s)"
    echo "  Skipping automatic download"
    ollama list
    exit 0
fi

echo ""
echo "🚀 Starting automatic model download..."
echo ""

SUCCESS_COUNT=0
FAILED_MODELS=()

for model in "${MODELS[@]}"; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📥 Downloading: $model"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if ollama pull "$model"; then
        echo "✅ Successfully downloaded: $model"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo "❌ Failed to download: $model"
        FAILED_MODELS+=("$model")
    fi

    echo ""
done

echo "═══════════════════════════════════════════════════════════════"
echo "                    Download Summary"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "✅ Successfully downloaded: $SUCCESS_COUNT model(s)"

if [ ${#FAILED_MODELS[@]} -gt 0 ]; then
    echo "❌ Failed to download:"
    for model in "${FAILED_MODELS[@]}"; do
        echo "   • $model"
    done
fi

echo ""
echo "📋 Current model inventory:"
ollama list

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "              Ollama initialization complete!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
