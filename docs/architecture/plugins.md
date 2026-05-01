# Minder Plugin Architecture

## Overview
Minder is now a fully **plugin-based** system! Consistent "plugins" terminology everywhere.

## Architecture

### Directory Structure
```
minder/
├── plugins/                    # Plugin directory (formerly modules/)
│   ├── fund/                   # Fund analysis plugin
│   │   ├── fund_module.py      # Plugin implementation
│   │   └── __init__.py
│   ├── tefas/                  # TEFAS plugin
│   │   ├── tefas_module.py
│   │   └── __init__.py
│   ├── crypto/                 # Crypto plugin
│   ├── news/                   # News plugin
│   ├── network/                # Network plugin
│   └── weather/                # Weather plugin
├── core/
│   ├── plugin_loader.py        # Plugin discovery & loading
│   ├── registry.py             # PluginRegistry (formerly ModuleRegistry)
│   └── kernel.py               # MinderKernel
├── api/
│   └── main.py                 # REST API endpoints
└── config.yaml                 # Plugin configuration
```

### Configuration
```yaml
# config.yaml
plugins:
  fund:
    enabled: true
    database:
      host: postgres
      port: 5432

  tefas:
    enabled: true
    database:
      host: postgres

  weather:
    enabled: false
```

## API Endpoints

### List All Plugins
```bash
GET /plugins
```

**Response:**
```json
{
  "plugins": [
    {
      "name": "tefas",
      "enabled": true,
      "status": "ready",
      "metadata": {
        "version": "1.0.0",
        "description": "TEFAS Turkey investment fund analysis",
        "capabilities": ["real_time_data", "historical_analysis"]
      }
    }
  ],
  "total": 6,
  "enabled": 6,
  "disabled": 0
}
```

### Enable Plugin
```bash
POST /plugins/{plugin_name}/enable
```

### Disable Plugin
```bash
POST /plugins/{plugin_name}/disable
```

### Run Pipeline
```bash
POST /plugins/{plugin_name}/pipeline
```

## Core Components

### PluginRegistry
```python
from core.registry import PluginRegistry

registry = PluginRegistry(config)
await registry.register_plugin(plugin)
plugins = await registry.list_plugins()
```

### PluginLoader
```python
from core.plugin_loader import PluginLoader

loader = PluginLoader(config)
plugins = await loader.load_all_plugins()
```

### MinderKernel
```python
from core.kernel import MinderKernel

kernel = MinderKernel(config)
await kernel.start()

# Query plugins
results = await kernel.query_plugins(query)

# Run pipeline
results = await kernel.run_plugin_pipeline(plugin_name)
```

## Terminology Mapping

| Old (Inconsistent) | New (Consistent) |
|-------------------|------------------|
| `modules/` directory | `plugins/` directory |
| `modules:` in config | `plugins:` in config |
| `ModuleRegistry` | `PluginRegistry` |
| `load_all_modules()` | `load_all_plugins()` |
| `register_module()` | `register_plugin()` |
| `list_modules()` | `list_plugins()` |
| `/modules` endpoint | `/plugins` endpoint |
| `query_modules()` | `query_plugins()` |
| `run_module_pipeline()` | `run_plugin_pipeline()` |

## File Naming

Plugin files support two extensions:
- `{plugin_name}_plugin.py` (preferred)
- `{plugin_name}_module.py` (backward compatibility)

Example:
- `plugins/fund/fund_plugin.py` ✅
- `plugins/fund/fund_module.py` ✅
- `plugins/tefas/tefas_plugin.py` ✅
- `plugins/tefas/tefas_module.py` ✅

## Benefits

### 1. **Consistency**
- Same term everywhere: "plugins"
- Directory name → Config → API → Code (all consistent)
- No confusion

### 2. **Clarity**
- "Plugin" = pluggable, modular component
- More descriptive and standard
- Industry standard (WordPress, VS Code, Chrome)

### 3. **Backward Compatibility**
- Both `_plugin.py` and `_module.py` extensions supported
- Old plugins continue to work
- Gradual migration possible

### 4. **Better UX**
- API endpoints more understandable: `/plugins` vs `/modules`
- Log messages clearer: "Loading plugin" vs "Loading module"
- Consistent documentation

## Current Plugins

| Plugin | Status | Description |
|--------|--------|-------------|
| **fund** | ✅ Enabled | Turkish mutual fund analysis |
| **tefas** | ✅ Enabled | TEFAS investment fund tracking |
| **crypto** | ✅ Enabled | Cryptocurrency market analysis |
| **news** | ✅ Enabled | News aggregation & sentiment |
| **network** | ✅ Enabled | Network monitoring & security |
| **weather** | ✅ Enabled | Weather data & correlation |

## Usage Examples

### CLI
```bash
# List plugins
curl http://localhost:8000/plugins | jq

# Disable weather
curl -X POST http://localhost:8000/plugins/weather/disable

# Enable weather
curl -X POST http://localhost:8000/plugins/weather/enable

# Check status
curl http://localhost:8000/plugins | jq '.plugins[] | select(.name == "tefas")'
```

### Python
```python
import requests

# List plugins
response = requests.get("http://localhost:8000/plugins")
plugins = response.json()

# Disable plugin
requests.post("http://localhost:8000/plugins/weather/disable")

# Enable plugin
requests.post("http://localhost:8000/plugins/weather/enable")
```

## Migration from "modules"

### What Changed
1. **Directory**: `modules/` → `plugins/`
2. **Config key**: `modules:` → `plugins:`
3. **API endpoints**: `/modules/*` → `/plugins/*`
4. **Class names**: `ModuleRegistry` → `PluginRegistry`
5. **Method names**: `*_module_*()` → `*_plugin_*()`

### What Stayed the Same
1. **BaseModule interface**: Same
2. **Plugin structure**: Same
3. **Capabilities**: Same
4. **Functionality**: Same

### Migration Checklist
- [x] Rename `modules/` → `plugins/`
- [x] Update config: `modules:` → `plugins:`
- [x] Update core classes: `ModuleRegistry` → `PluginRegistry`
- [x] Update API endpoints: `/modules` → `/plugins`
- [x] Update method names throughout codebase
- [x] Support both `_plugin.py` and `_module.py` extensions
- [x] Update all documentation

## Conclusion

Minder now has a **fully consistent plugin system**!

✅ Directory: `plugins/`
✅ Config: `plugins:`
✅ API: `/plugins`
✅ Code: `PluginRegistry`, `load_all_plugins()`
✅ Terminology: "plugins" everywhere

Clearer, more standard, more understandable! 🚀
