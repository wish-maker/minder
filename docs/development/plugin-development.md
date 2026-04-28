# Minder Plugin Development Guide

> **Last Updated:** 2026-04-29
> **Platform Version:** 2.1.0
> **Plugin Interface:** v2 (simplified)
> **Active Plugins:** 5 (crypto, network, news, tefas, weather)

---

## Table of Contents

1. [Introduction](#introduction)
2. [Plugin Architecture](#plugin-architecture)
3. [Quick Start](#quick-start)
4. [Plugin Interface](#plugin-interface)
5. [Plugin Types](#plugin-types)
6. [Development Workflow](#development-workflow)
7. [Configuration](#configuration)
8. [Testing](#testing)
9. [Packaging](#packaging)
10. [Examples](#examples)

---

## Introduction

Minder supports a flexible plugin system that allows extending functionality without modifying core services. Plugins can:

- Collect data from external sources (APIs, databases, files)
- Process and transform data
- Provide new capabilities to the platform

### Plugin Types

1. **Data Source Plugins:** Fetch data from external APIs
2. **Processor Plugins:** Transform or enrich data
3. **Storage Plugins:** Persist data to databases
4. **Action Plugins:** Execute actions based on data

---

## Plugin Architecture

### Directory Structure

```
minder/
├── src/
│   └── plugins/
│       ├── crypto/              # Example plugin
│       │   ├── __init__.py
│       │   ├── crypto_module.py
│       │   ├── crypto_validator.py
│       │   └── plugin.yml
│       ├── network/
│       └── weather/
├── services/
│   └── plugin-registry/   # Loads and manages plugins
```

### Plugin Lifecycle

1. **Discovery:** Scan `/app/plugins` directory
2. **Loading:** Import plugin module
3. **Registration:** Call `register()` method
4. **Validation:** Verify plugin meets requirements
5. **Initialization:** Inject dependencies (database, config)
6. **Health Monitoring:** Periodic health checks
7. **Shutdown:** Cleanup resources

---

## Quick Start

### Minimal Plugin Example

Create a new plugin in 3 files:

**1. plugin.yml (metadata)**
```yaml
name: "hello_world"
version: "1.0.0"
description: "A simple hello world plugin"
author: "Your Name <email@example.com>"
capabilities:
  - greeting
data_sources: []
databases: []
```

**2. __init__.py (package)**
```python
from .hello_module import HelloPlugin

__all__ = ["HelloPlugin"]
```

**3. hello_module.py (implementation)**
```python
from src.core.module_interface_v2 import BaseModule
import logging

logger = logging.getLogger(__name__)

class HelloPlugin(BaseModule):
    def register(self):
        """Called when plugin is loaded"""
        logger.info("Hello World plugin registered!")
        return {
            "name": "hello_world",
            "version": "1.0.0",
            "greeting": "Hello from Minder!"
        }
```

**Deploy:**

```bash
# Copy to plugins directory
cp -r hello_world /root/minder/src/plugins/

# Restart plugin registry
docker restart minder-plugin-registry

# Verify
curl http://localhost:8001/v1/plugins | jq '.plugins[] | select(.name=="hello_world")'
```

---

## Plugin Interface

### v2 Interface (Recommended)

Simplified interface with only one required method:

```python
from src.core.module_interface_v2 import BaseModule

class MyPlugin(BaseModule):
    def register(self):
        """
        REQUIRED - Called when plugin is loaded

        Returns:
            dict: Plugin metadata
                - name (str): Plugin identifier
                - version (str): Semantic version
                - description (str): What this plugin does
                - capabilities (list): What plugin can do
        """
        return {
            "name": "my_plugin",
            "version": "1.0.0",
            "description": "Does something useful",
            "capabilities": ["process", "analyze"]
        }
```

### Optional Methods

```python
class MyPlugin(BaseModule):
    def register(self):
        # ... required implementation

    def initialize(self, config):
        """
        OPTIONAL - Called after registration with configuration

        Args:
            config (dict): Configuration from plugin.yml or environment

        Returns:
            bool: True if initialization successful
        """
        self.config = config
        return True

    def execute(self, data):
        """
        OPTIONAL - Execute plugin's main function

        Args:
            data (dict): Input data for processing

        Returns:
            dict: Processed data
        """
        return {"processed": data}

    def health_check(self):
        """
        OPTIONAL - Health check for monitoring

        Returns:
            dict: Health status
            """
        return {
            "status": "healthy",
            "message": "All systems operational"
        }

    def shutdown(self):
        """
        OPTIONAL - Cleanup before unload

        Called when plugin is disabled or platform shuts down
        """
        logger.info(f"{self.__class__.__name__} shutting down")
```

---

## Plugin Types

### 1. Data Collection Plugins

Fetch data from external sources:

```python
from src.core.module_interface_v2 import BaseModule
import httpx
import asyncio

class WeatherPlugin(BaseModule):
    def register(self):
        return {
            "name": "weather",
            "version": "2.0.0",
            "description": "Weather data collection",
            "capabilities": ["fetch", "cache"],
            "data_sources": ["weather-api"],
            "databases": []
        }

    async def fetch_weather(self, location: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.weather.com/v1/current?q={location}"
            )
            return response.json()

    def execute(self, query: str):
        """Fetch weather data for location"""
        return asyncio.run(self.fetch_weather(query))
```

### 2. Data Processing Plugins

Transform and enrich data:

```python
from src.core.module_interface_v2 import BaseModule

class DataEnrichmentPlugin(BaseModule):
    def register(self):
        return {
            "name": "data_enricher",
            "version": "1.0.0",
            "description": "Enrich data with external context",
            "capabilities": ["enrich", "transform"],
            "data_sources": [],
            "databases": []
        }

    def execute(self, data: dict) -> dict:
        """Add enrichment to data"""
        enriched = data.copy()
        enriched["timestamp"] = datetime.now().isoformat()
        enriched["processed_by"] = "data_enricher"
        return enriched
```

### 3. Storage Plugins

Persist data to databases:

```python
from src.core.module_interface_v2 import BaseModule
import asyncpg

class DatabaseWriterPlugin(BaseModule):
    def register(self):
        return {
            "name": "db_writer",
            "version": "1.0.0",
            "description": "Write data to PostgreSQL",
            "capabilities": ["persist", "batch_write"],
            "data_sources": [],
            "databases": ["postgres"]
        }

    def initialize(self, config):
        self.db_config = config.get("databases", {})
        self.pool = None
        return True

    async def persist(self, data: dict):
        """Write data to database"""
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                host=self.db_config.get("host", "localhost"),
                port=self.db_config.get("port", 5432),
                user=self.db_config.get("user", "minder"),
                password=self.db_config.get("password"),
                database=self.db_config.get("database", "minder")
            )

        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO processed_data (data) VALUES ($1)",
                [json.dumps(data)]
            )

    def execute(self, data: dict):
        """Persist data"""
        return asyncio.run(self.persist(data))
```

---

## Development Workflow

### Step 1: Create Plugin Structure

```bash
# Create plugin directory
mkdir -p src/plugins/my_plugin

# Create required files
touch src/plugins/my_plugin/__init__.py
touch src/plugins/my_plugin/my_plugin_module.py
touch src/plugins/my_plugin/plugin.yml
```

### Step 2: Implement Plugin

**my_plugin_module.py:**

```python
from src.core.module_interface_v2 import BaseModule
import logging

logger = logging.getLogger(__name__)

class MyPlugin(BaseModule):
    def register(self):
        logger.info("Registering MyPlugin")
        return {
            "name": "my_plugin",
            "version": "1.0.0",
            "description": "My custom plugin",
            "capabilities": ["process", "analyze"],
            "data_sources": [],
            "databases": []
        }

    def execute(self, data: dict):
        logger.info(f"Processing data: {data}")
        # Your logic here
        result = {"processed": True, "data": data}
        return result
```

### Step 3: Add Metadata

**plugin.yml:**

```yaml
name: my_plugin
version: 1.0.0
description: My custom Minder plugin
author: Your Name <email@example.com>
capabilities:
  - process
  - analyze
data_sources: []
databases: []
```

### Step 4: Test Locally

```bash
# Test plugin import
cd /root/minder
python -c "
import sys
sys.path.insert(0, 'src')
from plugins.my_plugin import MyPlugin
plugin = MyPlugin()
result = plugin.register()
print(result)
"

# Load in plugin registry
docker restart minder-plugin-registry
curl http://localhost:8001/v1/plugins | jq '.plugins[] | select(.name=="my_plugin")'
```

### Step 5: Add Dependencies (if needed)

**requirements.txt (in plugin directory):**

```
# Plugin-specific dependencies
requests==2.31.0
beautifulsoup4==4.12.0
```

**Dockerfile (if plugin needs special dependencies):**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

---

## Configuration

### plugin.yml Structure

```yaml
# Required metadata
name: plugin_name
version: 1.0.0
description: Plugin description
author: Developer Name <email@example.com>

# Plugin capabilities
capabilities:
  - fetch      # Retrieve data
  - process    # Transform data
  - persist    # Store data
  - analyze    # Analyze data

# External data sources (if applicable)
data_sources:
  - source-name: "API endpoint or database"

# Database requirements (if applicable)
databases:
  - postgres  # Requires PostgreSQL connection
  - redis     # Requires Redis connection
```

### Environment Variables

**Access in plugin:**

```python
import os

class MyPlugin(BaseModule):
    def initialize(self, config):
        # From environment
        self.api_key = os.getenv("MY_PLUGIN_API_KEY")
        self.timeout = int(os.getenv("MY_PLUGIN_TIMEOUT", "30"))
        return True
```

**Set in docker-compose.yml:**

```yaml
services:
  plugin-registry:
    environment:
      - MY_PLUGIN_API_KEY=secret_key
      - MY_PLUGIN_TIMEOUT=60
```

---

## Testing

### Unit Tests

**tests/unit/test_my_plugin.py:**

```python
import pytest
from src.plugins.my_plugin import MyPlugin

def test_plugin_registration():
    plugin = MyPlugin()
    metadata = plugin.register()

    assert metadata["name"] == "my_plugin"
    assert metadata["version"] == "1.0.0"
    assert "process" in metadata["capabilities"]

def test_plugin_execute():
    plugin = MyPlugin()
    result = plugin.execute({"test": "data"})

    assert result["processed"] is True
    assert result["data"]["test"] == "data"
```

### Integration Tests

**tests/integration/test_plugin_loading.sh:**

```bash
#!/bin/bash

# Test plugin loads
PLUGIN_COUNT=$(curl -s http://localhost:8001/v1/plugins | jq '.count')
if [ "$PLUGIN_COUNT" -gt 0 ]; then
    echo "✓ Plugins loaded successfully"
else
    echo "✗ No plugins loaded"
    exit 1
fi

# Test specific plugin
MY_PLUGIN=$(curl -s http://localhost:8001/v1/plugins/my_plugin | jq '.')
if [ -n "$MY_PLUGIN" ]; then
    echo "✓ my_plugin loaded"
else
    echo "✗ my_plugin not found"
    exit 1
fi
```

### Run Tests

```bash
# Unit tests
pytest tests/unit/test_my_plugin.py

# Integration tests
bash tests/integration/test_plugin_loading.sh
```

---

## Packaging

### Single Plugin

```bash
# Create plugin package
cd src/plugins/my_plugin
tar czf my_plugin.tar.gz \
    __init__.py \
    my_plugin_module.py \
    plugin.yml \
    requirements.txt \
    README.md

# Install
mkdir -p /app/plugins/my_plugin
tar xzf my_plugin.tar.gz -C /app/plugins/my_plugin/
```

### Plugin Bundle

Multiple plugins in one package:

```bash
# Create bundle
tar czf my_plugins.tar.gz \
    plugin1/ \
    plugin2/ \
    plugin3/

# Extract all
tar xzf my_plugins.tar.gz -C /app/plugins/
```

---

## Examples

### Example 1: API Data Source Plugin

Fetch data from external API:

```python
# api_source_plugin.py
from src.core.module_interface_v2 import BaseModule
import httpx
import asyncio

class APIPlugin(BaseModule):
    def register(self):
        return {
            "name": "api_source",
            "version": "1.0.0",
            "description": "Fetch data from external API",
            "capabilities": ["fetch"],
            "data_sources": ["rest-api"],
            "databases": []
        }

    async def fetch_api(self, endpoint: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            return response.json()

    def execute(self, endpoint: str) -> dict:
        """Fetch data from API endpoint"""
        return asyncio.run(self.fetch_api(endpoint))
```

### Example 2: Data Transformation Plugin

Transform and normalize data:

```python
# transform_plugin.py
from src.core.module_interface_v2 import BaseModule
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class TransformPlugin(BaseModule):
    def register(self):
        return {
            "name": "transform",
            "version": "1.0.0",
            "description": "Transform and normalize data",
            "capabilities": ["transform", "normalize"],
            "data_sources": [],
            "databases": []
        }

    def execute(self, data: dict) -> dict:
        """Transform input data"""
        transformed = {
            "original": data,
            "normalized": self.normalize(data),
            "timestamp": datetime.now().isoformat()
        }
        return transformed

    def normalize(self, data: dict) -> dict:
        """Normalize data structure"""
        # Your normalization logic here
        return data
```

### Example 3: Database Storage Plugin

Store data in PostgreSQL:

```python
# storage_plugin.py
from src.core.module_interface_v2 import BaseModule
import asyncpg
import logging
import json

logger = logging.getLogger(__name__)

class StoragePlugin(BaseModule):
    def register(self):
        return {
            "name": "storage",
            "version": "1.0.0",
            "description": "Store data in PostgreSQL",
            "capabilities": ["persist"],
            "data_sources": [],
            "databases": ["postgres"]
        }

    def initialize(self, config):
        self.db_config = config.get("databases", {}).get("postgres", {})
        self.pool = None
        return True

    async def store(self, data: dict):
        """Store data in database"""
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                host=self.db_config.get("host", "localhost"),
                port=self.db_config.get("port", 5432),
                user=self.db_config.get("user", "minder"),
                password=self.db_config.get("password"),
                database=self.db_config.get("database", "minder")
            )

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO plugin_data (plugin_name, data_type, data)
                VALUES ($1, $2, $3)
                """,
                [self.__class__.__name__, "json", json.dumps(data)]
            )

    def execute(self, data: dict) -> dict:
        """Store data in database"""
        asyncio.run(self.store(data))
        return {"stored": True, "id": "generated_id"}
```

---

## Best Practices

### 1. Error Handling

```python
from src.core.module_interface_v2 import BaseModule
import logging

logger = logging.getLogger(__name__)

class RobustPlugin(BaseModule):
    def register(self):
        try:
            # Initialization code
            return {
                "name": "robust",
                "version": "1.0.0",
                "description": "Robust plugin with error handling"
            }
        except Exception as e:
            logger.error(f"Registration failed: {e}")
            raise

    def execute(self, data: dict):
        try:
            # Processing code
            result = self.process(data)
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "data": data
            }
```

### 2. Logging

```python
import logging

logger = logging.getLogger(__name__)

class LoggingPlugin(BaseModule):
    def register(self):
        logger.info("Registering plugin")
        logger.debug("Plugin configuration: %s", self.config)
        return self.metadata

    def execute(self, data: dict):
        logger.info(f"Processing data with {len(data)} fields")
        logger.debug(f"Input data: {data}")
        # Process data
        logger.debug("Processing complete")
        return result
```

### 3. Configuration Management

```python
class ConfigurablePlugin(BaseModule):
    def initialize(self, config):
        # Store configuration
        self.timeout = config.get("timeout", 30)
        self.retry_count = config.get("retry_count", 3)
        self.debug_mode = config.get("debug", False)

        # Log configuration
        logger.info(f"Configured with timeout={self.timeout}, retries={self.retry_count}")
        return True

    def execute(self, data: dict):
        # Use configuration
        if self.debug_mode:
            logger.debug(f"Debug mode: {data}")
        return self.process_with_retry(data)
```

### 4. Testing

```python
# Always write tests
def test_my_plugin():
    plugin = MyPlugin()

    # Test registration
    metadata = plugin.register()
    assert metadata is not None
    assert "name" in metadata

    # Test execution
    result = plugin.execute({"test": "data"})
    assert result is not None
```

### 5. Documentation

```python
class DocumentedPlugin(BaseModule):
    """
    A well-documented plugin that does X, Y, and Z.

    Usage:
        plugin = DocumentedPlugin()
        result = plugin.execute(data)

    Example:
        >>> plugin = DocumentedPlugin()
        >>> result = plugin.execute({"input": "value"})
        >>> result["output"] == "expected"
    """

    def register(self):
        """Register plugin with platform"""
        return self.metadata
```

---

## Advanced Topics

### Database Access

**PostgreSQL Access:**

```python
class DBPlugin(BaseModule):
    def initialize(self, config):
        # Database config is injected by Plugin Registry
        self.db_config = config.get("databases", {}).get("postgres", {})
        self.pool = None
        return True

    async def get_connection(self):
        """Get database connection"""
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                host=self.db_config.get("host", "localhost"),
                port=self.db_config.get("port", 5432),
                user=self.db_config.get("user", "minder"),
                password=self.db_config.get("password"),
                database=self.db_config.get("database", "minder")
            )
        return self.pool
```

**Redis Access:**

```python
class RedisPlugin(BaseModule):
    def initialize(self, config):
        self.redis_config = config.get("databases", {}).get("redis", {})
        self.client = None
        return True

    def get_client(self):
        """Get Redis client"""
        if not self.client:
            import redis
            self.client = redis.Redis(
                host=self.redis_config.get("host", "localhost"),
                port=self.redis_config.get("port", 6379),
                password=self.redis_config.get("password"),
                decode_responses=True
            )
        return self.client
```

### Async Operations

```python
class AsyncPlugin(BaseModule):
    async def execute_async(self, data: dict):
        """Async version of execute"""
        # Perform async operations
        result = await self.async_operation(data)
        return result

    def execute(self, data: dict):
        """Sync wrapper for async operations"""
        import asyncio
        return asyncio.run(self.execute_async(data))
```

### Plugin Communication

**Call Other Plugins:**

```python
class OrchestratorPlugin(BaseModule):
    def initialize(self, config):
        # Get references to other plugins
        self.plugin_registry_url = config.get("plugin_registry_url")
        return True

    def call_plugin(self, plugin_name: str, method: str, data: dict):
        """Call another plugin's method"""
        import httpx

        response = httpx.post(
            f"{self.plugin_registry_url}/v1/plugins/{plugin_name}/execute",
            json=data,
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
```

---

## Troubleshooting

### Plugin Not Loading

**Check:**
1. File structure correct?
   - `__init__.py` exists
   - Module file exists
   - `plugin.yml` valid YAML

2. Python path correct?
   - Module in `/app/plugins/` or `/root/minder/src/plugins/`
   - `__init__.py` exports plugin class

3. Dependencies installed?
   - Check `requirements.txt` if plugin has dependencies
   - Rebuild container if needed

**Debug Commands:**

```bash
# Check plugin directory
ls -la /root/minder/src/plugins/my_plugin/

# Test import
cd /root/minder
python -c "
import sys
sys.path.insert(0, 'src')
from plugins.my_plugin import MyPlugin
print('Plugin loads successfully')
"

# Check plugin registry logs
docker logs minder-plugin-registry --tail 50
```

### Database Connection Issues

**Check:**
1. Database credentials correct?
2. Database accessible from container?
3. Correct database name?

**Debug:**

```bash
# Test connection from within container
docker exec -it minder-plugin-registry bash
python3 -c "
import psycopg2
conn = psycopg2.connect('host=postgres port=5432 user=minder password=...')
print('Connection successful')
"
```

### Performance Issues

**Common causes:**
1. Blocking operations in `execute()`
2. Large data transfers
3. Inefficient algorithms

**Solutions:**
- Use async operations
- Implement pagination
- Add caching
- Limit result sets

---

## Plugin Registry API

### Register Plugin

```bash
curl -X POST http://localhost:8001/v1/plugins/install \
  -H "Content-Type: application/json" \
  -d '{
    "git_url": "https://github.com/user/plugin.git",
    "branch": "main"
  }'
```

### Enable/Disable Plugin

```bash
# Enable
curl -X POST http://localhost:8001/v1/plugins/my_plugin/enable

# Disable
curl -X POST http://localhost:8001/v1/plugins/my_plugin/disable
```

### Plugin Health

```bash
curl http://localhost:8001/v1/plugins/my_plugin/health
```

---

## Contributing Plugins

### Submit to Plugin Registry

1. Fork Minder repository
2. Create plugin in `src/plugins/your_plugin/`
3. Add tests in `tests/unit/test_your_plugin.py`
4. Add documentation
5. Submit pull request

### Third-Party Plugins

Host plugins in your own repository and install via git URL:

```bash
curl -X POST http://localhost:8001/v1/plugins/install \
  -H "Content-Type: application/json" \
  -d '{
    "git_url": "https://github.com/yourname/third-party-plugin.git",
    "branch": "main"
  }'
```

---

## Appendix

### Plugin Interface v1 vs v2

**v1 (Legacy):**
- More methods required
- Stricter interface
- Better for complex plugins

**v2 (Current - Recommended):**
- Only `register()` required
- Simpler interface
- Faster development

**Migration Guide:**

```python
# v1
class OldPlugin(BaseModule):
    def register(self): pass
    def initialize(self, config): pass
    def execute(self, data): pass
    def health_check(self): pass
    def shutdown(self): pass

# v2 (equivalent)
class NewPlugin(BaseModule):
    def register(self): pass
    # initialize, execute, health_check, shutdown are optional
```

### Useful Utilities

**In src/core/:**
- `module_interface_v2.py` - BaseModule class
- `plugin_loader.py` - Plugin loading logic
- `registry.py` - Plugin registry

**Examples in src/plugins/:**
- `crypto/` - Configuration handling
- `network/` - Network operations
- `weather/` - API integration
- `tefas/` - Complex data processing

---

**Last Updated:** 2026-04-22
**Platform Version:** 2.0.0
