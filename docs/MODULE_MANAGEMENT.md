# Module Management System - Plugin Architecture

## Overview
Minder modülleri artık plugin gibi dinamik olarak enable/disable edilebiliyor!

## Features

### ✅ Dynamic Module Management
- **Runtime enable/disable**: Modülleri çalışma anında açıp kapatın
- **Config-based control**: `config.yaml` ile kalıcı ayarlar
- **Auto-discovery**: `modules/` dizininden otomatik keşif
- **Graceful degradation**: İsteğe bağlı bağımlılıklar

### Configuration

```yaml
# config.yaml
modules:
  fund:
    enabled: true              # Enable/disable
    database:
      host: postgres
      port: 5432

  weather:
    enabled: false             # Disabled at startup
    api_key: "..."

  tefas:
    enabled: true              # New TEFAS module
    database:
      host: postgres
    influxdb:
      host: influxdb
    qdrant:
      host: qdrant
```

## API Endpoints

### List All Modules
```bash
GET /modules
```

**Response:**
```json
{
  "modules": [
    {
      "name": "tefas",
      "enabled": true,
      "status": "ready",
      "metadata": {
        "version": "1.0.0",
        "description": "TEFAS Türkiye yatırım fonları analizi",
        "capabilities": ["real_time_data", "historical_analysis", ...]
      }
    },
    {
      "name": "weather",
      "enabled": false,
      "status": "disabled"
    }
  ],
  "total": 6,
  "enabled": 5,
  "disabled": 1
}
```

### Enable Module (Runtime)
```bash
POST /modules/{module_name}/enable
```

**Response:**
```json
{
  "module": "weather",
  "status": "enabled",
  "message": "Module weather will be enabled on next restart"
}
```

### Disable Module (Runtime)
```bash
POST /modules/{module_name}/disable
```

**Response:**
```json
{
  "module": "weather",
  "status": "disabled",
  "message": "Module weather has been disabled and unloaded"
}
```

## Usage Examples

### CLI with curl
```bash
# List modules
curl http://localhost:8000/modules | jq

# Disable weather module
curl -X POST http://localhost:8000/modules/weather/disable

# Enable weather module
curl -X POST http://localhost:8000/modules/weather/enable

# Check specific module status
curl http://localhost:8000/modules | jq '.modules[] | select(.name == "tefas")'
```

### Python
```python
import requests

BASE_URL = "http://localhost:8000"

# List modules
response = requests.get(f"{BASE_URL}/modules")
modules = response.json()
print(f"Enabled: {modules['enabled']}/{modules['total']}")

# Disable module
requests.post(f"{BASE_URL}/modules/weather/disable")

# Enable module
requests.post(f"{BASE_URL}/modules/weather/enable")
```

## Module Lifecycle

### Startup
1. **Discovery**: `modules/` dizinini tara
2. **Config Check**: `enabled: true` kontrolü
3. **Load**: Sadece enabled modülleri yükle
4. **Register**: Registry'ye kaydet
5. **Initialize**: Başlat

### Runtime
1. **Disable**: Modülü durdur ve bellekten boşalt
2. **Enable**: Config'i güncelle (restart gerekir)
3. **Reload**: Modülü yeniden yükle

## Adding New Modules

### 1. Create Module Directory
```bash
mkdir -p modules/my_module
```

### 2. Implement Module
```python
# modules/my_module/my_module.py
from core.module_interface import BaseModule, ModuleMetadata

class MyModule(BaseModule):
    async def register(self) -> ModuleMetadata:
        return ModuleMetadata(
            name="my_module",
            version="1.0.0",
            description="My custom module"
        )
```

### 3. Add to Config
```yaml
# config.yaml
modules:
  my_module:
    enabled: true
    # module-specific config
```

### 4. Restart
```bash
docker restart minder-api
```

That's it! Module will be auto-discovered and loaded.

## Test Results

### Module Management Test
```
📋 Testing module listing...
✅ Total modules: 6
   - Enabled: 6
   - Disabled: 0

   Module Status:
      ✅ news: True
      ✅ crypto: True
      ✅ network: True
      ✅ fund: True
      ✅ weather: True
      ✅ tefas: True

🔴 Disabling module: weather
✅ Module weather has been disabled and unloaded

🔛 Enabling module: weather
✅ Module weather will be enabled on next restart

📋 Testing module listing...
✅ Total modules: 6
   - Enabled: 5
   - Disabled: 1
```

## Benefits

### For Developers
- **Pluggable architecture**: Modülleri bağımsız geliştir
- **Easy testing**: Modülleri açıp kapat
- **Isolation**: Modüller birbirini etkilemez
- **Hot-reload**: Geliştirme hızlandırır

### For Operators
- **Dynamic control**: Maintenance için modülleri kapat
- **Resource management**: Gereksiz modülleri disable et
- **A/B testing**: Farklı modül kombinasyonlarını dene
- **Graceful degradation**: Hatalı modülleri devre dışı bırak

### For Users
- **Customization**: İhtiyaç duyduğun modülleri aç
- **Performance**: Sadece gerekli modüller
- **Stability**: Sorunlu modülleri kapat

## Current Modules

| Module | Status | Description |
|--------|--------|-------------|
| **fund** | ✅ Enabled | Turkish mutual fund analysis |
| **tefas** | ✅ Enabled | TEFAS investment fund tracking |
| **crypto** | ✅ Enabled | Cryptocurrency market analysis |
| **news** | ✅ Enabled | News aggregation & sentiment |
| **network** | ✅ Enabled | Network monitoring & security |
| **weather** | ✅ Enabled | Weather data & correlation |

## Next Steps

### Enhanced Features
1. **Hot-reload**: Restart olmadan enable
2. **Dependency management**: Bağımlılıkları otomatik çöz
3. **Version management**: Aynı modülün birden fazla versiyonu
4. **Module marketplace**: Modül paylaşım platformu
5. **Web UI**: Admin paneli

### Monitoring
1. **Module metrics**: CPU, memory usage
2. **Performance tracking**: Response times
3. **Error tracking**: Module-specific logs
4. **Health checks**: Liveness probes

## Conclusion

Minder artık tam plug-and-play! Modüller:
✅ Dinamik enable/disable
✅ Config tabanlı kontrol
✅ API ile yönetim
✅ Otomatik keşif
✅ Production ready

Yeni bir modül eklemek için `modules/` dizinine oluşturmak ve config'e eklemek yeterli!
