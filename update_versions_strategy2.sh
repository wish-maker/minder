#!/bin/bash

# Strateji 2: Ayrı Versiyonlama
# Ana uygulama ve bileşenlerin farklı versiyonları

cd "$(dirname "$0")"

echo "=== ANA UYGULAMA VERSİYONLARINI GÜNCELLEME ==="

# 1. Ana Uygulama versiyonunu vMAJOR.MINOR.PATCH formatına çevir
echo "1. Ana Uygulama: v2.1.0"
find services/ -name "main.py" -o -name "__init__.py" | xargs sed -i 's/__version__ = "2\.1\.0"/__version__ = "v2.1.0"/g; s/API_VERSION = "v2\.1\.0"/API_VERSION = "v2.1.0"/g; s/version = "2\.1\.0"/version = "v2.1.0"/g'

# 2. Plugin Registry versiyonunu güncelle
echo "2. Plugin Registry: v1.0.0"
sed -i 's/API_VERSION = "v2\.1\.0"/API_VERSION = "v1.0.0"/g' services/plugin-registry/main.py
sed -i 's/version = "v2\.1\.0"/version = "v1.0.0"/g' services/plugin-registry/main.py

# 3. Bileşenleri vMAJOR.MINOR.PATCH formatına çevir
echo "3. Bileşenler: v2.1.0 (API), v1.0.0 (Plugin)"
find services/ai-services-unified/services/ services/rag-pipeline/ services/tts-stt-service/ -name "main.py" | xargs sed -i 's/__version__ = "v2\.1\.0"/__version__ = "v2.1.0"/g; s/version = "v2\.1\.0"/version = "v2.1.0"/g'

echo ""
echo "=== DOĞRULAMA ==="

# Ana uygulama versiyonu
API_VER=$(grep -o 'API_VERSION.*"[^"]*"' services/api-gateway/main.py | head -1)
CORE_VER=$(grep -o '__version__.*"[^"]*"' services/api-gateway/main.py | head -1)
PLUGIN_VER=$(grep -o 'API_VERSION.*"[^"]*"' services/plugin-registry/main.py | head -1)

echo "Ana Uygulama API Version: $API_VER"
echo "Ana Uygulama Core Version: $CORE_VER"
echo "Plugin Registry API Version: $PLUGIN_VER"
echo ""

echo "=== VERSİYON MATRİSİ ==="
echo "Ana Uygulama: v2.1.0"
echo "Plugin Registry: v1.0.0"
echo "Bileşenler: v2.1.0"
echo ""
echo "Versiyonlar ayrıldı:"
echo "- Ana Uygulama: v2.1.0"
echo "- Plugin Registry: v1.0.0"
echo "- Bileşenler: v2.1.0"

echo ""
echo "=== BAŞARILI ==="
echo "Strateji 2 uygulandı: Ayrı versiyonlama"
