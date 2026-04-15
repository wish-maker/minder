# Minder Plugin Store & Registry System

## Overview
Jellyfin tarzı plugin sistemi - plugin'ler ayrı repo'larda geliştirilsin, repolardan çekilsin.

## Architecture

### 1. Plugin Store Structure
```
minder-plugin-store/
├── plugins/                    # Plugin registry
│   ├── fund-analysis/
│   │   ├── .git/
│   │   ├── plugin.yml         # Plugin manifest
│   │   ├── fund_plugin.py
│   │   ├── README.md
│   │   └── requirements.txt
│   ├── crypto-tracker/
│   └── weather-integration/
├── index.json                 # Plugin index
└── api/                       # Plugin store API
```

### 2. Plugin Manifest (plugin.yml)
```yaml
name: fund-analysis
version: 1.0.0
description: Turkish mutual fund analysis with ML predictions
author: Your Name <email@example.com>
license: MIT
repository: https://github.com/username/minder-fund-analysis
branch: main

minder:
  min_version: "1.0.0"
  max_version: "2.0.0"

capabilities:
  - data_collection
  - return_calculation
  - volatility_analysis

requirements:
  - pandas>=2.0.0
  - numpy>=1.20.0
  - scikit-learn>=1.0.0

databases:
  - postgresql
  - influxdb

api:
  endpoints:
    - path: /api/funds/latest
      method: GET
      description: Get latest fund data

  webhooks:
    - event: data_collected
      url: /api/funds/on-data
```

### 3. Plugin Store API
```python
# plugins/store.py
from typing import List, Dict, Any
import requests
import subprocess
from pathlib import Path
import tempfile
import shutil

class PluginStore:
    """Plugin store - GitHub repolarından plugin yönetimi"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.store_path = Path(config.get('store_path', '/var/lib/minder/plugins'))
        self.index_url = config.get('index_url', 'https://raw.githubusercontent.com/minder-plugins/index/main/plugins.json')
        self.installed_plugins = {}

    async def fetch_index(self) -> List[Dict[str, Any]]:
        """Plugin index'i çek"""
        try:
            response = requests.get(self.index_url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch plugin index: {e}")
            return []

    async def search_plugins(self, query: str) -> List[Dict[str, Any]]:
        """Plugin ara"""
        index = await self.fetch_index()
        results = []

        for plugin in index:
            if (query.lower() in plugin['name'].lower() or
                query.lower() in plugin['description'].lower() or
                any(tag.lower() == query.lower() for tag in plugin.get('tags', []))):
                results.append(plugin)

        return results

    async def install_plugin(
        self,
        repo_url: str,
        branch: str = 'main',
        version: str = 'latest'
    ) -> Dict[str, Any]:
        """Plugin'i repodan kur"""

        # Repo'yu clone et
        plugin_name = repo_url.split('/')[-1].replace('.git', '')
        install_path = self.store_path / plugin_name

        try:
            subprocess.run(
                ['git', 'clone', '-b', branch, repo_url, str(install_path)],
                check=True,
                capture_output=True
            )

            # Plugin manifest'i oku
            manifest = await self._load_manifest(install_path)

            # Version kontrolü
            if version != 'latest' and manifest['version'] != version:
                await self._checkout_version(install_path, version)

            # Dependencies'i yükle
            await self._install_dependencies(install_path)

            # Plugin'i kaydet
            self.installed_plugins[plugin_name] = {
                'path': install_path,
                'manifest': manifest,
                'version': version,
                'installed_at': datetime.now().isoformat()
            }

            logger.info(f"✅ Plugin installed: {plugin_name}")
            return {
                'plugin': plugin_name,
                'version': manifest['version'],
                'status': 'installed'
            }

        except Exception as e:
            logger.error(f"Failed to install plugin {plugin_name}: {e}")
            # Hata durumda temizle
            if install_path.exists():
                shutil.rmtree(install_path)
            raise

    async def uninstall_plugin(self, plugin_name: str) -> bool:
        """Plugin'i kaldır"""

        if plugin_name not in self.installed_plugins:
            raise ValueError(f"Plugin not installed: {plugin_name}")

        install_path = self.installed_plugins[plugin_name]['path']

        try:
            # Plugin'i disable et
            # await self.registry.disable_plugin(plugin_name)

            # Dosyaları sil
            shutil.rmtree(install_path)

            # Kayıttan çıkar
            del self.installed_plugins[plugin_name]

            logger.info(f"✅ Plugin uninstalled: {plugin_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to uninstall plugin {plugin_name}: {e}")
            return False

    async def update_plugin(self, plugin_name: str) -> Dict[str, Any]:
        """Plugin'i güncelle"""

        if plugin_name not in self.installed_plugins:
            raise ValueError(f"Plugin not installed: {plugin_name}")

        current_info = self.installed_plugins[plugin_name]
        repo_url = current_info['manifest'].get('repository')

        # Mevcut kurulumu kaldır
        await self.uninstall_plugin(plugin_name)

        # Yeni versiyonunu kur
        return await self.install_plugin(repo_url)

    async def list_installed_plugins(self) -> List[Dict[str, Any]]:
        """Kurulu plugin'leri listele"""

        plugins = []

        for plugin_name, info in self.installed_plugins.items():
            plugins.append({
                'name': plugin_name,
                'version': info['version'],
                'description': info['manifest']['description'],
                'author': info['manifest']['author'],
                'installed_at': info['installed_at'],
                'path': str(info['path'])
            })

        return plugins

    async def _load_manifest(self, plugin_path: Path) -> Dict[str, Any]:
        """Plugin manifest'i yükle"""
        manifest_file = plugin_path / 'plugin.yml'

        if not manifest_file.exists():
            raise FileNotFoundError(f"Plugin manifest not found: {manifest_file}")

        import yaml
        with open(manifest_file) as f:
            return yaml.safe_load(f)

    async def _install_dependencies(self, plugin_path: Path):
        """Plugin dependencies'lerini yükle"""
        requirements_file = plugin_path / 'requirements.txt'

        if requirements_file.exists():
            subprocess.run(
                ['pip', 'install', '-r', str(requirements_file)],
                check=True
            )

    async def _checkout_version(self, plugin_path: Path, version: str):
        """Belirli bir versiyona checkout et"""
        subprocess.run(
            ['git', 'checkout', version],
            cwd=str(plugin_path),
            check=True
        )
```

### 4. API Endpoints
```python
# api/plugin_store.py
from fastapi import APIRouter, HTTPException
from typing import List, Optional

router = APIRouter(prefix="/plugins/store", tags=["Plugin Store"])

@router.get("/search")
async def search_plugins(q: str = ""):
    """Plugin ara"""
    store = app.state.plugin_store
    results = await store.search_plugins(q)
    return {"query": q, "results": results, "total": len(results)}

@router.get("/installed")
async def list_installed_plugins():
    """Kurulu plugin'leri listele"""
    store = app.state.plugin_store
    plugins = await store.list_installed_plugins()
    return {"plugins": plugins, "total": len(plugins)}

@router.post("/install")
async def install_plugin(repo_url: str, branch: str = "main", version: str = "latest"):
    """Plugin'i repodan kur"""
    store = app.state.plugin_store
    try:
        result = await store.install_plugin(repo_url, branch, version)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/uninstall/{plugin_name}")
async def uninstall_plugin(plugin_name: str):
    """Plugin'i kaldır"""
    store = app.state.plugin_store
    try:
        success = await store.uninstall_plugin(plugin_name)
        return {"plugin": plugin_name, "status": "uninstalled"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update/{plugin_name}")
async def update_plugin(plugin_name: str):
    """Plugin'i güncelle"""
    store = app.state.plugin_store
    try:
        result = await store.update_plugin(plugin_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/index")
async def get_plugin_index():
    """Plugin index'i al"""
    store = app.state.plugin_store
    index = await store.fetch_index()
    return {"plugins": index, "total": len(index)}
```

### 5. Plugin Store Index (plugins.json)
```json
{
  "plugins": [
    {
      "id": "fund-analysis",
      "name": "Fund Analysis",
      "description": "Turkish mutual fund analysis with ML predictions",
      "author": "FundMind AI",
      "version": "1.0.0",
      "license": "MIT",
      "repository": "https://github.com/minder-plugins/fund-analysis",
      "branch": "main",
      "tags": ["finance", "funds", "turkish", "ml"],
      "stars": 42,
      "downloads": 1234,
      "last_updated": "2026-04-12T00:00:00Z",
      "minder": {
        "min_version": "1.0.0",
        "max_version": "2.0.0"
      }
    },
    {
      "id": "crypto-tracker",
      "name": "Crypto Tracker",
      "description": "Cryptocurrency price tracking and analysis",
      "author": "CryptoDev",
      "version": "2.1.0",
      "license": "Apache-2.0",
      "repository": "https://github.com/minder-plugins/crypto-tracker",
      "tags": ["crypto", "bitcoin", "trading"],
      "stars": 128,
      "downloads": 5678,
      "last_updated": "2026-04-10T15:30:00Z"
    }
  ]
}
```

### 6. Kullanım Örnekleri

#### Plugin Arama
```bash
# Finance plugin'lerini ara
curl "http://localhost:8000/plugins/store/search?q=finance"

# Crypto plugin'lerini ara
curl "http://localhost:8000/plugins/store/search?q=crypto"
```

#### Plugin Kurma
```bash
# GitHub reposundan kur
curl -X POST "http://localhost:8000/plugins/store/install" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/username/minder-fund-analysis",
    "branch": "main",
    "version": "latest"
  }'
```

#### Plugin Listeleme
```bash
# Kurulu plugin'leri gör
curl http://localhost:8000/plugins/store/installed
```

#### Plugin Güncelleme
```bash
# Plugin'i güncelle
curl -X POST http://localhost:8000/plugins/store/update/fund-analysis
```

#### Plugin Kaldırma
```bash
# Plugin'i kaldır
curl -X POST http://localhost:8000/plugins/store/uninstall/fund-analysis
```

### 7. 3rd Party Plugin Geliştirme

#### Plugin Şablonu
```bash
# Plugin repo oluştur
mkdir minder-my-plugin
cd minder-my-plugin
git init

# Şablon dosyaları oluştur
cat > plugin.yml << 'EOF'
name: my-plugin
version: 1.0.0
description: My custom Minder plugin
author: Your Name <email@example.com>
license: MIT
repository: https://github.com/username/minder-my-plugin

minder:
  min_version: "1.0.0"

capabilities:
  - data_collection
  - analysis

requirements:
  - requests>=2.28.0
  - pandas>=2.0.0
EOF

# Plugin implementasyonu
cat > my_plugin.py << 'EOF'
from core.module_interface import BaseModule, ModuleMetadata

class MyPlugin(BaseModule):
    async def register(self) -> ModuleMetadata:
        return ModuleMetadata(
            name="my-plugin",
            version="1.0.0",
            description="My custom plugin",
            author="Your Name",
            capabilities=["data_collection", "analysis"]
        )

    async def collect_data(self, since=None):
        # Veri toplama logic
        return {"records_collected": 100}

    async def analyze(self):
        # Analiz logic
        return {"metrics": {}, "insights": []}
EOF
```

#### Plugin Yayınlama
```bash
# GitHub reposuna push et
git add .
git commit -m "Initial plugin release"
git push origin main

# Release oluştur
gh release create 1.0.0

# Minder plugin index'e ekle
# Pull request gönder: minder-plugins/index
```

### 8. Güvenlik

#### Plugin Validation
```python
async def validate_plugin(self, plugin_path: Path) -> Dict[str, Any]:
    """Plugin'i güvenlik kontrolünden geçir"""

    # 1. Manifest doğrulama
    manifest = await self._load_manifest(plugin_path)

    # 2. Minder version uyumluluğu
    if not self._check_version_compatibility(manifest):
        raise ValueError("Incompatible Minder version")

    # 3. Kod inceleme (basic)
    await self._scan_for_malicious_code(plugin_path)

    # 4. Signature kontrolü (opsiyonel)
    if not await self._verify_signature(plugin_path):
        logger.warning(f"Plugin signature not verified: {plugin_path}")

    # 5. Dependencies güvenlik kontrolü
    await self._check_dependencies_security(plugin_path)

    return {"valid": True, "warnings": []}
```

### 9. Config Güncellemesi
```yaml
# config.yaml
plugin_store:
  enabled: true
  store_path: /var/lib/minder/plugins
  index_url: https://raw.githubusercontent.com/minder-plugins/index/main/plugins.json

  # Güvenlik ayarları
  security:
    require_signature: false
    allow_unsigned: true
    scan_for_malware: true

  # Otomatik güncelleme
  auto_update: false
  update_interval: 86400  # Günlük
```

### 10. Plugin Store Frontend (Opsiyonel)
```
minder-web/
├── plugin-store/
│   ├── pages/
│   │   ├── index.tsx        # Plugin listesi
│   │   ├── plugin/[id].tsx # Plugin detayı
│   │   └── search.tsx      # Arama sayfası
│   └── components/
│       ├── PluginCard.tsx
│       └── PluginInstaller.tsx
```

---

## Implementation Roadmap

### Phase 1: Core Infrastructure
- [ ] PluginStore class
- [ ] Plugin manifest format (plugin.yml)
- [ ] GitHub repo integration
- [ ] Install/uninstall/update APIs
- [ ] Plugin index sistemi

### Phase 2: Security
- [ ] Plugin validation
- [ ] Signature verification
- [ ] Malware scanning
- [ ] Dependency security checks
- [ ] Sandbox execution (opsiyonel)

### Phase 3: Plugin Registry
- [ ] Public plugin index repo
- [ ] Plugin submission system
- [ ] Version control
- [ ] Automated testing
- [ ] Community ratings/reviews

### Phase 4: Developer Experience
- [ ] Plugin development template
- [ ] CLI tool for plugin development
- [ ] Testing framework
- [ ] Documentation generator
- [ ] Plugin publishing guide

### Phase 5: Frontend
- [ ] Plugin store UI
- [ ] One-click install
- [ ] Plugin management dashboard
- [ ] Update notifications
- [ ] Community features

---

## Kullanım Senaryoları

### Senaryo 1: Kullanıcı Yeni Plugin Kuruyor
```bash
# 1. Plugin ara
curl "http://localhost:8000/plugins/store/search?q=crypto"

# 2. Plugin detayını gör
curl http://localhost:8000/plugins/store/plugins/crypto-tracker

# 3. Plugin'i kur
curl -X POST http://localhost:8000/plugins/store/install \
  -d '{"repo_url": "https://github.com/minder-plugins/crypto-tracker"}'

# 4. Plugin'i aktif et
curl -X POST http://localhost:8000/plugins/crypto-tracker/enable

# 5. Plugin kullan
curl http://localhost:8000/plugins/crypto-tracker/data
```

### Senaryo 2: Geliştirici Plugin Yayınlıyor
```bash
# 1. Yeni plugin repo oluştur
git clone https://github.com/minder-plugins/template.git my-custom-plugin

# 2. Plugin'i geliştir
cd my-custom-plugin
# ... kodlama ...

# 3. Test et
minder-cli plugin test

# 4. Yayımla
git push origin main
gh release create 1.0.0

# 5. Plugin index'e ekle
# PR gönder: minder-plugins/index
```

---

## Bu sistemle neler olacak?

✅ **3rd Party Plugin Desteği**: Herkes plugin yazıp paylaşabilecek
✅ **Merkezi Plugin Store**: Tek yerden plugin bulma ve yükleme
✅ **Version Control**: Plugin versiyonlama ve güncelleme
✅ **Güvenlik**: Plugin validation ve signature verification
✅ **Kolay Geliştirme**: Template'ler ve CLI araçları
✅ **Community**: Plugin puanlama, yorumlama, paylaşım

**Bu, Minder'ı gerçekten eklenebilir bir platforma dönüştürür!** 🚀