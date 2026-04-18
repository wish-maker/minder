# Minder Plugin Template
# Copy this directory to create your own plugin

# ============================================================================
# 1. PLUGIN MANIFEST (REQUIRED)
# ============================================================================

# File: plugin.yml
name: "my_plugin"
version: "1.0.0"
description: "Brief description of what this plugin does"
author: "Your Name"
license: "MIT"

minder:
  min_version: "1.0.0"

python:
  min_version: "3.11"

dependencies:
  python:
    - "requests>=2.31.0"

permissions:
  filesystem:
    read: []
    write: []
    execute: []
  network:
    allowed_hosts: ["api.example.com"]
    allowed_ports: [443]
  database:
    databases: []
    tables: []
    operations: []
  resources:
    max_memory_mb: 256
    max_cpu_percent: 30
    max_execution_time: 120

capabilities:
  - "data_collection"
  - "analysis"

# ============================================================================
# 2. PLUGIN CODE (REQUIRED)
# ============================================================================

# File: my_plugin_plugin.py
"""
My Minder Plugin
Description of what this plugin does
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

# Use the v2.0 interface for simpler plugin development
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.module_interface_v2 import BaseModule, ModuleMetadata


class MyPluginModule(BaseModule):
    """
    My Plugin - Brief description

    Example plugin showing the v2.0 simplified interface.
    """

    async def register(self) -> ModuleMetadata:
        """
        Register plugin - ONLY REQUIRED METHOD

        Returns plugin metadata to the kernel.
        """
        self.metadata = ModuleMetadata(
            name="my_plugin",
            version="1.0.0",
            description="My awesome plugin that does X, Y, Z",
            author="Your Name",
            dependencies=["requests>=2.31.0"],
            capabilities=["data_collection", "analysis"],
            data_sources=["Example API"],
            databases=[],  # No database access needed
        )

        self.log("✅ My Plugin registered successfully!")
        return self.metadata

    # ========================================================================
    # OPTIONAL: Override only what you need
    # ========================================================================

    async def collect_data(self, since: Optional[datetime] = None) -> Dict[str, int]:
        """
        Collect data from external source (OPTIONAL)

        Only implement this if your plugin collects data.
        """
        self.log("Collecting data...")

        # Your data collection logic here
        records_collected = 0
        errors = 0

        return {
            "records_collected": records_collected,
            "records_updated": 0,
            "errors": errors,
        }

    async def analyze(self) -> Dict[str, Any]:
        """
        Analyze collected data (OPTIONAL)

        Only implement this if your plugin provides analysis.
        """
        self.log("Analyzing data...")

        return {
            "metrics": {
                "total_records": 100,
            },
            "patterns": [],
            "insights": [
                "Analysis complete"
            ],
        }

    # If you don't need AI/ML, leave these default implementations
    # async def train_ai(self, model_type: str = "default") -> Dict[str, Any]:
    #     """Not implemented - uses base implementation"""
    #     pass
    #
    # async def index_knowledge(self, force: bool = False) -> Dict[str, int]:
    #     """Not implemented - uses base implementation"""
    #     pass

# ============================================================================
# 3. PLUGIN INIT (REQUIRED)
# ============================================================================

# File: __init__.py
"""
My Plugin - Brief description
"""

from .my_plugin_module import MyPluginModule

__all__ = ["MyPluginModule"]
__version__ = "1.0.0"

# ============================================================================
# 4. DOCUMENTATION (REQUIRED)
# ============================================================================

# File: README.md
# My Plugin for Minder

## Overview
Brief description of what this plugin does.

## Installation
```bash
# Via Plugin Store API
curl -X POST http://localhost:8000/plugins/store/install \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/username/my-plugin",
    "branch": "main"
  }'
```

## Configuration
No configuration required.

## Usage
```python
# Collect data
await plugin.collect_data()

# Analyze data
await plugin.analyze()

# Query data
await plugin.query("my query")
```

## Permissions
This plugin requires:
- Network access to api.example.com:443
- 256MB memory limit
- 30% CPU limit

## License
MIT

# ============================================================================
# 5. TESTS (RECOMMENDED)
# ============================================================================

# File: tests/test_my_plugin.py
import pytest
from core.module_interface_v2 import BaseModule


def test_plugin_registration():
    """Test plugin can be registered"""
    # Your test code here
    pass


# ============================================================================
# 6. EXAMPLES (OPTIONAL)
# ============================================================================

# File: examples/basic_usage.py
"""
Basic usage example for My Plugin
"""

async def example_usage():
    """Example of how to use this plugin"""
    from core.plugin_loader import PluginLoader

    # Load plugin
    loader = PluginLoader({"plugins_path": "/path/to/plugins"})
    plugin = await loader.load_plugin("my_plugin")

    # Collect data
    result = await plugin.collect_data()
    print(f"Collected {result['records_collected']} records")

    # Analyze data
    analysis = await plugin.analyze()
    print(f"Metrics: {analysis['metrics']}")
