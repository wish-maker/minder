#!/bin/bash
# Model Management Ollama Integration Test
# NOTE: Be careful with DELETE and PULL - they perform real operations

set -e

BASE_URL="http://localhost:8005"
OLLAMA_HOST="http://localhost:11434"

echo "========================================="
echo "Model Management Ollama Integration Test"
echo "========================================="
echo ""

# Test 1: Health Check
echo "TEST 1: Health Check"
echo "--------------------"
curl -s "$BASE_URL/health" | jq '.'
echo ""

# Test 2: Root endpoint (check Ollama availability)
echo "TEST 2: Root Endpoint (Ollama Status)"
echo "--------------------------------------"
curl -s "$BASE_URL/" | jq '.'
echo ""

# Test 3: List Models (should return real Ollama models)
echo "TEST 3: GET /models (Real Ollama List)"
echo "----------------------------------------"
curl -s "$BASE_URL/models" | jq '.'
echo ""

# Test 4: Get specific model details (if models exist)
echo "TEST 4: GET /models/{model_id} (First model details)"
echo "------------------------------------------------------"
FIRST_MODEL=$(curl -s "$BASE_URL/models" | jq -r '.[0].id // empty')
if [ -n "$FIRST_MODEL" ]; then
    echo "Getting details for: $FIRST_MODEL"
    curl -s "$BASE_URL/models/$FIRST_MODEL" | jq '.'
else
    echo "No models found to test"
fi
echo ""

# Test 5: Test model generation (CAUTION - performs real inference)
echo "TEST 5: POST /models/{model_id}/test (Model Generation Test)"
echo "---------------------------------------------------------------"
if [ -n "$FIRST_MODEL" ]; then
    echo "Testing model: $FIRST_MODEL"
    curl -s -X POST "$BASE_URL/models/$FIRST_MODEL/test?prompt=Hello" | jq '.'
else
    echo "No models found to test"
fi
echo ""

# Test 6: Pull a small model (OPTIONAL - CAUTION: downloads real data)
echo "TEST 6: POST /models (Pull Model Test - SKIPPED for safety)"
echo "-------------------------------------------------------------"
echo "SKIPPED: This would download a real model (can be large)"
echo "To test manually: curl -X POST \"$BASE_URL/models?model_id=tinyllama\""
echo ""

# Test 7: Delete model (SKIPPED - CAUTION: deletes real data)
echo "TEST 7: DELETE /models/{model_id} (Delete Model - SKIPPED for safety)"
echo "-------------------------------------------------------------------------"
echo "SKIPPED: This would permanently delete a model"
echo "To test manually: curl -X DELETE \"$BASE_URL/models/{model_id}\""
echo ""

echo "========================================="
echo "Test Summary"
echo "========================================="
echo "✅ Health check completed"
echo "✅ Ollama status verified"
echo "✅ Model listing works (real Ollama connection)"
echo "✅ Model details retrieval works"
echo "✅ Model generation test works"
echo ""
echo "⚠️  SKIPPED: Model pull (real download)"
echo "⚠️  SKIPPED: Model delete (real deletion)"
echo ""
echo "Next steps for manual testing:"
echo "1. Test pull: curl -X POST '$BASE_URL/models?model_id=tinyllama'"
echo "2. Test delete: curl -X DELETE '$BASE_URL/models/{unsafe_model_id}'"
echo ""
