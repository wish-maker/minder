#!/bin/bash

# Update Script: Upgrade Library Versions to Latest Versions

cd "$(dirname "$0")"

echo "=== UPDATE LIBRARY VERSIONS ==="

# 1. Update requirements.txt
echo "1. Updating requirements.txt..."
sed -i 's/fastapi>=0\.110\.0,<0\.120\.0/fastapi>=0.115.0,<0\.120\.0/g' requirements.txt
sed -i 's/pydantic>=2\.1\.0,<2\.2\.0/pydantic>=2.10.0,<2\.20\.0/g' requirements.txt
sed -i 's/httpx>=0\.26\.0,<0\.28\.0/httpx>=0.28.0,<0\.29\.0/g' requirements.txt
sed -i 's/asyncpg>=0\.29\.0,<0\.30\.0/asyncpg>=0.30.0,<0\.31\.0/g' requirements.txt
sed -i 's/redis>=5\.0\.0,<5\.1\.0/redis>=5.4.2,<5\.5\.0/g' requirements.txt
sed -i 's/qdrant>=1\.8\.0,<1\.12\.0/qdrant>=1.12.0,<1\.13\.0/g' requirements.txt
sed -i 's/neo4j>=4\.4\.0,<5\.0\.0/neo4j>=5.26.0,<5\.27\.0/g' requirements.txt
sed -i 's/ollama>=0\.5\.0,<0\.6\.0/ollama>=0.5.7,<0\.6\.0/g' requirements.txt

echo "✅ requirements.txt updated"

# 2. Update version variables in AI services
echo "2. Updating AI services..."
sed -i 's/OLLAMA_VERSION = "0\.5\.0"/OLLAMA_VERSION = "0.5.7"/g' services/ai-services-unified/main.py
sed -i 's/QDRANT_VERSION = "1\.8\.0"/QDRANT_VERSION = "1.12.0"/g' services/ai-services-unified/main.py
sed -i 's/NEO4J_VERSION = "4\.4\.0"/NEO4J_VERSION = "5.26.0"/g' services/ai-services-unified/main.py
sed -i 's/REDIS_VERSION = "5\.0\.0"/REDIS_VERSION = "5.4.2"/g' services/ai-services-unified/main.py
sed -i 's/FASTAPI_VERSION = "0\.110\.0"/FASTAPI_VERSION = "0.115.0"/g' services/ai-services-unified/main.py
sed -i 's/PYDANTIC_VERSION = "2\.1\.0"/PYDANTIC_VERSION = "2.10.0"/g' services/ai-services-unified/main.py

echo "✅ AI services updated"

# 3. Validation
echo ""
echo "=== VALIDATION ==="

# Check AI services
echo "AI services:"
grep -E "OLLAMA_VERSION|QDRANT_VERSION|NEO4J_VERSION|REDIS_VERSION|FASTAPI_VERSION|PYDANTIC_VERSION" services/ai-services-unified/main.py

echo ""
echo "requirements.txt check:"
grep -E "fastapi|pydantic|httpx|asyncpg|redis|qdrant|neo4j|ollama" requirements.txt

echo ""
echo "=== COMPLETE ==="
