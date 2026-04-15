#!/bin/bash
# Manual Component Testing - Step by Step Verification

echo "=========================================="
echo "MANUAL COMPONENT TESTING"
echo "Her bir component'i ayrı ayrı test ediyoruz"
echo "=========================================="
echo ""

BASE_URL="http://localhost:8000"

echo "=== 1. CONTAINER STATUS ==="
echo "Tüm container'lar çalışıyor mu?"
docker compose ps
echo ""

echo "=== 2. API BAĞLANTISI ==="
echo "API yanıt veriyor mu?"
curl -i -X GET "$BASE_URL/health" 2>&1 | head -20
echo ""

echo "=== 3. AUTHENTICATION - LOGIN ==="
echo "Admin kullanıcısı ile login deniyoruz..."
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}')
echo "$LOGIN_RESPONSE" | jq '.'
echo ""

echo "JWT Token:"
TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')
echo "${TOKEN:0:50}..."
echo ""

echo "=== 4. PROTECTED ENDPOINT - TOKEN İLE ==="
echo "Token ile plugins endpoint'ine erişim..."
curl -s "$BASE_URL/plugins" \
  -H "Authorization: Bearer $TOKEN" | jq '.plugins | length'
echo ""

echo "=== 5. PROTECTED ENDPOINT - TOKEN OLMADAN ==="
echo "Token olmadan plugins endpoint'ine erişim..."
curl -s -w "\nHTTP Code: %{http_code}\n" "$BASE_URL/plugins" | tail -5
echo ""

echo "=== 6. RATE LIMITING - 10 HIZLI İSTEK ==="
echo "10 hızlı istek atıyoruz..."
for i in {1..10}; do
  curl -s "$BASE_URL/plugins" > /dev/null
done
echo "10 istek tamamlandı - rate limit var mı?"
echo ""

echo "=== 7. NETWORK DETECTION HEADERS ==="
echo "Network headers kontrol ediliyor..."
curl -v "$BASE_URL/" 2>&1 | grep -E "x-network-type|x-client-ip|x-correlation-id"
echo ""

echo "=== 8. SECURITY HEADERS ==="
echo "Security headers kontrol ediliyor..."
curl -v "$BASE_URL/health" 2>&1 | grep -E "x-content-type|x-frame|x-xss|strict-transport"
echo ""

echo "=== 9. REDIS CONNECTION ==="
echo "Redis bağlantısı test ediliyor..."
docker exec redis redis-cli ping
echo ""

echo "=== 10. POSTGRESQL CONNECTION ==="
echo "PostgreSQL bağlantısı test ediliyor..."
docker exec postgres psql -U postgres -d fundmind -c "SELECT version();" | head -3
echo ""

echo "=== 11. CHAT ENDPOINT TEST ==="
echo "Chat endpoint test ediliyor..."
if [ -n "$TOKEN" ]; then
  curl -s -X POST "$BASE_URL/chat" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"message":"test"}' | jq '.' | head -20
else
  echo "Token alınamadı, chat test atlanıyor..."
fi
echo ""

echo "=========================================="
echo "MANUEL TEST TAMAMLANDI"
echo "=========================================="
