#!/bin/bash
# LIVE VERIFICATION - Gerçek zamanlı test

echo "=========================================="
echo "LIVE VERIFICATION - Gerçek zamanlı test"
echo "=========================================="
echo ""

BASE="http://localhost:8000"

echo "1. Container Status:"
docker ps | grep minder-api | awk '{print "   " $0}'
echo ""

echo "2. Root Endpoint:"
curl -s "$BASE/" | jq -c '{status: .status, auth: .authentication}'
echo ""

echo "3. Health Check:"
curl -s "$BASE/health" | jq -c '{status: .status}'
echo ""

echo "4. Login Test:"
TOKEN=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r '.access_token')
echo "   Token: ${TOKEN:0:40}..."
echo ""

echo "5. Plugins (with token):"
curl -s "$BASE/plugins" -H "Authorization: Bearer $TOKEN" | jq -c '{total: .total, enabled: .enabled}'
echo ""

echo "6. Chat Test:"
curl -s -X POST "$BASE/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"test"}' | jq -c '{character: .character, plugins: .plugins_used | length}'
echo ""

echo "7. Rate Limit Test (5 requests):"
for i in {1..5}; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/health")
  echo "   Request $i: HTTP $CODE"
done
echo ""

echo "8. Network Headers:"
curl -s -D - "$BASE/health" -o /dev/null | grep -E "x-network-type|x-client-ip" | head -2
echo ""

echo "9. Security Headers:"
curl -s -D - "$BASE/health" -o /dev/null | grep -E "x-content-type|x-frame|x-xss|strict-transport" | head -4
echo ""

echo "10. Databases:"
echo "   Redis: $(docker exec redis redis-cli ping 2>/dev/null)"
echo "   PostgreSQL: $(docker exec postgres psql -U postgres -d fundmind -tAc "SELECT 1;" 2>/dev/null)"
echo ""

echo "=========================================="
echo "✅ LIVE VERIFICATION COMPLETE"
echo "=========================================="
