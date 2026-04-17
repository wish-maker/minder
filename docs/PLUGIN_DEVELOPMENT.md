# Minder Plugin Development Guide

## Table of Contents
1. [Overview](#overview)
2. [Plugin Architecture](#plugin-architecture)
3. [Creating a Plugin](#creating-a-plugin)
4. [Plugin Lifecycle](#plugin-lifecycle)
5. [Data Collection](#data-collection)
6. [Testing Plugins](#testing-plugins)
7. [Best Practices](#best-practices)
8. [Examples](#examples)

---

## Overview

### What is a Minder Plugin?

A Minder plugin is a modular data collector that integrates external data sources into the Minder platform. Plugins enable:

- **Hot-swappable data sources**: Add/remove without kernel restart
- **Automatic discovery**: Dynamic plugin registration
- **Unified interface**: Consistent API across all plugins
- **Independent deployment**: Each plugin runs in isolation

### Plugin Capabilities

- **Data Collection**: Fetch data from external APIs, databases, or files
- **Data Processing**: Transform, filter, and enrich data
- **Event Emission**: Publish events to the system event bus
- **Health Monitoring**: Report plugin status and errors
- **Configuration**: Runtime configuration without restart

---

## Plugin Architecture

### Core Components

```
minder/
├── core/
│   ├── module_interface.py    # BaseModule interface
│   ├── kernel.py               # Plugin loader and manager
│   └── event_bus.py            # Event system
├── plugins/
│   ├── news/                   # News plugin
│   ├── crypto/                 # Crypto plugin
│   ├── weather/                # Weather plugin
│   └── tefas/                  # TEFAS plugin
```

### Module Interface

All plugins extend the `BaseModule` abstract class:

```python
from core.module_interface import BaseModule, ModuleMetadata, ModuleCapabilities

class MyPlugin(BaseModule):
    """Custom plugin implementation"""
    
    async def register(self) -> ModuleMetadata:
        """Register plugin metadata"""
        return ModuleMetadata(
            name="my_plugin",
            version="1.0.0",
            description="My awesome data collector",
            author="Your Name",
            capabilities=ModuleCapabilities(
                can_collect_data=True,
                can_process_events=False,
                can_store_data=True
            )
        )
    
    async def collect_data(self, since=None):
        """Collect data from external source"""
        # Implementation here
        pass
```

---

## Creating a Plugin

### Step 1: Create Plugin Directory

```bash
cd /root/minder/plugins
mkdir my_plugin
cd my_plugin
```

### Step 2: Create Plugin Structure

```
my_plugin/
├── __init__.py           # Plugin initialization
├── my_plugin_module.py   # Main plugin logic
├── config.yaml          # Plugin configuration
└── README.md            # Plugin documentation
```

### Step 3: Implement Plugin Module

**File: `my_plugin_module.py`**

```python
"""
My Plugin for Minder
Custom data collection implementation
"""

import asyncio
import aiohttp
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from core.module_interface import BaseModule, ModuleMetadata, ModuleCapabilities


class MyPluginModule(BaseModule):
    """Custom plugin implementation"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.logger = logging.getLogger(__name__)
        
        # Plugin configuration
        self.api_endpoint = config.get("api_endpoint", "https://api.example.com")
        self.api_key = config.get("api_key", "")
        self.collection_interval = config.get("collection_interval", 300)
        
        # State management
        self.last_collection = None
        self.is_collecting = False
    
    async def register(self) -> ModuleMetadata:
        """
        Register plugin metadata
        
        Returns:
            ModuleMetadata: Plugin information and capabilities
        """
        return ModuleMetadata(
            name="my_plugin",
            version="1.0.0",
            description="Collects data from Example API",
            author="Your Name <your.email@example.com>",
            capabilities=ModuleCapabilities(
                can_collect_data=True,
                can_process_events=False,
                can_store_data=True,
                can_generate_embeddings=True
            )
        )
    
    async def start(self):
        """
        Plugin startup logic
        
        Initialize connections, validate configuration,
        and schedule periodic data collection
        """
        self.logger.info(f"Starting {self.name} plugin...")
        
        # Validate configuration
        if not self.api_endpoint:
            raise ValueError("api_endpoint is required in configuration")
        
        # Test API connectivity
        if not await self._test_api_connectivity():
            raise ConnectionError("Cannot connect to API endpoint")
        
        # Schedule periodic collection
        asyncio.create_task(self._periodic_collection())
        
        self.logger.info(f"✅ {self.name} plugin started successfully")
    
    async def stop(self):
        """
        Plugin cleanup logic
        
        Close connections, cancel tasks, release resources
        """
        self.logger.info(f"Stopping {self.name} plugin...")
        
        # Cancel any running tasks
        if self.is_collecting:
            self.is_collecting = False
        
        self.logger.info(f"✅ {self.name} plugin stopped")
    
    async def collect_data(self, since: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Collect data from external API
        
        Args:
            since: Only collect data after this timestamp
            
        Returns:
            Dict with collection results:
                - records_collected: Number of records collected
                - records_updated: Number of records updated
                - errors: Number of errors encountered
                - error_details: Error message if failed
        """
        if self.is_collecting:
            self.logger.warning("Collection already in progress, skipping")
            return {
                'records_collected': 0,
                'records_updated': 0,
                'errors': 0,
                'error_details': 'Collection already in progress'
            }
        
        self.is_collecting = True
        records_collected = 0
        records_updated = 0
        errors = 0
        
        try:
            self.logger.info("Starting data collection...")
            
            # Fetch data from API
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                
                async with session.get(
                    self.api_endpoint,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_msg = f"API returned status {response.status}"
                        self.logger.error(error_msg)
                        return {
                            'records_collected': 0,
                            'records_updated': 0,
                            'errors': 1,
                            'error_details': error_msg
                        }
                    
                    data = await response.json()
            
            # Process data
            for record in data.get('items', []):
                try:
                    # Store record in database
                    await self._store_record(record)
                    records_collected += 1
                    
                except Exception as e:
                    self.logger.error(f"Error storing record: {e}")
                    errors += 1
            
            self.last_collection = datetime.now()
            self.logger.info(f"Collection completed: {records_collected} records")
            
            return {
                'records_collected': records_collected,
                'records_updated': records_updated,
                'errors': errors,
                'last_collection': self.last_collection.isoformat()
            }
            
        except Exception as e:
            error_msg = f"Collection failed: {str(e)}"
            self.logger.error(error_msg)
            return {
                'records_collected': records_collected,
                'records_updated': records_updated,
                'errors': errors + 1,
                'error_details': error_msg
            }
        finally:
            self.is_collecting = False
    
    async def _test_api_connectivity(self) -> bool:
        """Test API connectivity before starting"""
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                async with session.get(self.api_endpoint) as response:
                    if response.status == 200:
                        self.logger.info("✅ API connectivity confirmed")
                        return True
                    else:
                        self.logger.warning(
                            f"⚠️ API returned status {response.status}"
                        )
                        return False
        except Exception as e:
            self.logger.error(f"❌ API connectivity failed: {e}")
            return False
    
    async def _store_record(self, record: Dict[str, Any]):
        """Store record in database"""
        # Implement database storage logic
        # This would typically use the database connector
        pass
    
    async def _periodic_collection(self):
        """Schedule periodic data collection"""
        while True:
            try:
                await asyncio.sleep(self.collection_interval)
                await self.collect_data()
            except Exception as e:
                self.logger.error(f"Error in periodic collection: {e}")
```

### Step 4: Create Plugin Configuration

**File: `config.yaml`**

```yaml
# My Plugin Configuration

# API Settings
api_endpoint: "https://api.example.com/v1/data"
api_key: "${MY_PLUGIN_API_KEY}"  # Use environment variable

# Collection Settings
collection_interval: 300  # 5 minutes
batch_size: 100
timeout: 30

# Data Processing
enabled: true
priority: "medium"  # high, medium, low

# Health Check
health_check_interval: 60
failure_threshold: 3
auto_restart: true

# Storage
database:
  table: "my_plugin_data"
  create_table: true
  indexes:
    - field: "timestamp"
      type: "btree"
    - field: "id"
      type: "hash"
```

### Step 5: Register Plugin

**File: `__init__.py`**

```python
"""
My Plugin Package Export
"""

from .my_plugin_module import MyPluginModule

__all__ = ['MyPluginModule']

# Plugin factory function
def create_plugin(config):
    """Factory function to create plugin instance"""
    return MyPluginModule(config)
```

---

## Plugin Lifecycle

### 1. Registration Phase

```python
async def register(self) -> ModuleMetadata:
    """Called during plugin discovery"""
    return ModuleMetadata(
        name="my_plugin",
        version="1.0.0",
        # ... metadata
    )
```

**Purpose**: Declare plugin capabilities and metadata

### 2. Initialization Phase

```python
async def start(self):
    """Called when plugin is enabled"""
    # Validate config
    # Initialize connections
    # Schedule tasks
```

**Purpose**: Prepare plugin for data collection

### 3. Collection Phase

```python
async def collect_data(self, since=None):
    """Called periodically or manually"""
    # Fetch data
    # Process records
    # Store in database
    # Return results
```

**Purpose**: Collect and store data from external source

### 4. Shutdown Phase

```python
async def stop(self):
    """Called when plugin is disabled"""
    # Cancel tasks
    # Close connections
    # Release resources
```

**Purpose**: Clean shutdown and resource cleanup

---

## Data Collection

### Collection Patterns

#### 1. API Polling

```python
async def collect_data(self, since=None):
    async with aiohttp.ClientSession() as session:
        params = {}
        if since:
            params['since'] = since.isoformat()
        
        async with session.get(self.api_url, params=params) as response:
            data = await response.json()
            return await self._process_data(data)
```

#### 2. Webhook Reception

```python
async def handle_webhook(self, payload: Dict[str, Any]):
    """Handle incoming webhook data"""
    # Validate payload
    # Process data
    # Store in database
    pass
```

#### 3. File Processing

```python
async def collect_data(self, since=None):
    """Process files from directory"""
    for file_path in Path(self.input_dir).glob("*.json"):
        with open(file_path) as f:
            data = json.load(f)
            await self._process_data(data)
```

### Error Handling

```python
async def collect_data(self, since=None):
    try:
        data = await self._fetch_data()
        return await self._process_data(data)
    except aiohttp.ClientError as e:
        self.logger.error(f"Network error: {e}")
        return {'records_collected': 0, 'errors': 1}
    except ValueError as e:
        self.logger.error(f"Data validation error: {e}")
        return {'records_collected': 0, 'errors': 1}
    except Exception as e:
        self.logger.error(f"Unexpected error: {e}")
        return {'records_collected': 0, 'errors': 1}
```

---

## Testing Plugins

### Unit Tests

**File: `tests/test_my_plugin.py`**

```python
import pytest
from plugins.my_plugin.my_plugin_module import MyPluginModule

@pytest.fixture
async def plugin():
    """Create plugin instance for testing"""
    config = {
        "api_endpoint": "https://api.example.com",
        "api_key": "test_key",
        "collection_interval": 60
    }
    plugin = MyPluginModule(config)
    await plugin.start()
    yield plugin
    await plugin.stop()

@pytest.mark.asyncio
async def test_plugin_registration(plugin):
    """Test plugin registers correctly"""
    metadata = await plugin.register()
    assert metadata.name == "my_plugin"
    assert metadata.version == "1.0.0"

@pytest.mark.asyncio
async def test_api_connectivity(plugin):
    """Test API connectivity check"""
    result = await plugin._test_api_connectivity()
    assert isinstance(result, bool)

@pytest.mark.asyncio
async def test_data_collection(plugin):
    """Test data collection"""
    result = await plugin.collect_data()
    assert 'records_collected' in result
    assert 'errors' in result
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_full_collection_cycle():
    """Test complete collection cycle"""
    # Start plugin
    plugin = MyPluginModule(test_config)
    await plugin.start()
    
    # Collect data
    result = await plugin.collect_data()
    
    # Verify results
    assert result['records_collected'] > 0
    assert result['errors'] == 0
    
    # Cleanup
    await plugin.stop()
```

### Manual Testing

```bash
# Test plugin loading
docker exec minder-api python -c "
from plugins.my_plugin import MyPluginModule
plugin = MyPluginModule({'api_endpoint': 'https://api.example.com'})
print(plugin.register())
"

# Test data collection
curl -X POST http://localhost:8000/plugins/my_plugin/collect \
  -H "Authorization: Bearer <token>"

# View plugin logs
docker logs minder-api | grep my_plugin
```

---

## Best Practices

### 1. Error Handling

- Always implement comprehensive error handling
- Log errors with context
- Return structured error responses
- Implement retry logic for transient failures

### 2. Configuration

- Use environment variables for sensitive data
- Provide sensible defaults
- Validate configuration on startup
- Document all configuration options

### 3. Logging

- Use appropriate log levels (DEBUG, INFO, WARNING, ERROR)
- Include context in log messages
- Log both success and failure cases
- Avoid logging sensitive data

### 4. Performance

- Implement connection pooling
- Use async I/O operations
- Cache expensive operations
- Implement rate limiting for APIs

### 5. Testing

- Write unit tests for all methods
- Mock external dependencies
- Test error conditions
- Add integration tests

### 6. Documentation

- Document plugin purpose and usage
- Provide configuration examples
- Include troubleshooting section
- Keep README up to date

---

## Examples

### Example 1: Simple API Plugin

```python
class SimpleAPIPlugin(BaseModule):
    """Simple API data collector"""
    
    async def collect_data(self, since=None):
        async with aiohttp.ClientSession() as session:
            async with session.get(self.api_url) as response:
                data = await response.json()
                
                for item in data['items']:
                    await self.db.insert(item)
                
                return {'records_collected': len(data['items'])}
```

### Example 2: Database Query Plugin

```python
class DatabaseQueryPlugin(BaseModule):
    """Query external database"""
    
    async def collect_data(self, since=None):
        query = "SELECT * FROM data WHERE created_at > %s"
        async with self.db.acquire() as conn:
            results = await conn.fetch(query, since)
            
            for row in results:
                await self.process_row(row)
            
            return {'records_collected': len(results)}
```

### Example 3: File Processing Plugin

```python
class FileProcessingPlugin(BaseModule):
    """Process incoming files"""
    
    async def collect_data(self, since=None):
        files = list(Path(self.watch_dir).glob("*.json"))
        
        for file_path in files:
            with open(file_path) as f:
                data = json.load(f)
                await self.process_data(data)
            
            # Archive processed file
            file_path.rename(self.archive_dir / file_path.name)
        
        return {'records_collected': len(files)}
```

---

## Plugin Distribution

### GitHub Plugin Distribution

1. **Create Plugin Repository**
   - Fork or create new repository
   - Add plugin to `plugins/` directory
   - Include README and documentation

2. **Register Plugin**
   - Submit to plugin index: https://github.com/minder-plugins/plugin-index
   - Add plugin metadata to `plugins.json`

3. **Installation**
   ```bash
   # Install from GitHub
   curl -X POST http://localhost:8000/plugins/install \
     -H "Authorization: Bearer <token>" \
     -d '{
       "repository": "https://github.com/user/my-plugin",
       "branch": "main"
     }'
   ```

---

## Troubleshooting

### Plugin Not Loading

```bash
# Check plugin directory exists
ls -la /root/minder/plugins/my_plugin/

# Check for syntax errors
docker exec minder-api python -m py_compile plugins/my_plugin/*.py

# Check plugin logs
docker logs minder-api | grep my_plugin
```

### Collection Failing

```bash
# Test API connectivity
docker exec minder-api curl -I https://api.example.com

# Check plugin configuration
cat /root/minder/plugins/my_plugin/config.yaml

# View detailed logs
docker logs minder-api --tail 100 | grep -A 10 -B 10 my_plugin
```

### Database Issues

```bash
# Check database connection
docker exec postgres psql -U postgres -l

# Check plugin tables
docker exec postgres psql -U postgres -c "\dt my_plugin_*"

# Test database write
docker exec minder-api python -c "
from core.database import Database
db = Database({'host': 'postgres'})
print(db.test_connection())
"
```

---

## Version: 2.0.0
Last Updated: 2026-04-16
