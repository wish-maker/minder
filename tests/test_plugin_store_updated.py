"""
Updated Unit Tests for Plugin Store System
Tests plugin installation, loading, and management with correct BaseModule interface
"""
import pytest
import asyncio
from datetime import datetime
from pathlib import Path
import sys
import os
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.plugin_loader import PluginLoader
from core.module_interface import BaseModule, ModuleMetadata
from typing import Dict, Any, Optional


class MockPlugin(BaseModule):
    """Mock plugin for testing that implements all required methods"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.name = "mock_plugin"
        self.version = "1.0.0"
        self.description = "Mock plugin for testing"
        self.author = "Test Author"

    async def register(self) -> ModuleMetadata:
        """Register plugin"""
        self.metadata = ModuleMetadata(
            name=self.name,
            version=self.version,
            description=self.description,
            author=self.author,
            capabilities=["test_capability"]
        )
        return self.metadata

    async def collect_data(self, since: Optional[datetime] = None) -> Dict[str, int]:
        """Collect data"""
        return {"records_collected": 0}

    async def analyze(self) -> Dict[str, Any]:
        """Analyze data"""
        return {"analysis_complete": True}

    async def train_ai(self, model_type: str = "default") -> Dict[str, Any]:
        """Train AI model"""
        return {"model_trained": True}

    async def index_knowledge(self, force: bool = False) -> Dict[str, int]:
        """Index knowledge"""
        return {"documents_indexed": 0}

    async def get_correlations(
        self,
        correlation_type: str = "all",
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get correlations"""
        return {"correlations": []}

    async def get_anomalies(self, limit: int = 10) -> Dict[str, Any]:
        """Get anomalies"""
        return {"anomalies": []}

    async def health_check(self) -> Dict[str, Any]:
        """Health check"""
        return {"status": "healthy", "plugin": self.name}

    async def shutdown(self):
        """Shutdown plugin"""
        pass


class TestPluginInterface:
    """Test BaseModule interface compliance"""

    def test_base_module_abstract_methods(self):
        """Test that BaseModule has all required abstract methods"""
        from core.module_interface import BaseModule

        # Check required methods exist
        required_methods = [
            'register',
            'collect_data',
            'analyze',
            'train_ai',
            'index_knowledge',
            'get_correlations',
            'get_anomalies',
            'shutdown'
        ]

        for method in required_methods:
            assert hasattr(BaseModule, method)

    def test_plugin_can_implement_interface(self):
        """Test that a plugin can implement the interface"""
        config = {}
        plugin = MockPlugin(config)

        # Should have all attributes
        assert hasattr(plugin, 'name')
        assert hasattr(plugin, 'version')
        assert hasattr(plugin, 'config')
        assert plugin.name == "mock_plugin"


class TestPluginLoading:
    """Test plugin loading functionality"""

    @pytest.fixture
    def mock_plugin_dir(self, tmp_path):
        """Create a mock plugin directory"""
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()

        # Create proper plugin file
        plugin_file = plugin_dir / "test_plugin_plugin.py"
        plugin_file.write_text("""
from core.module_interface import BaseModule, ModuleMetadata
from typing import Dict, Any, Optional
from datetime import datetime

class TestPlugin(BaseModule):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.name = "test_plugin"
        self.version = "1.0.0"

    async def register(self) -> ModuleMetadata:
        self.metadata = ModuleMetadata(
            name=self.name,
            version=self.version,
            description="Test plugin",
            author="Test"
        )
        return self.metadata

    async def collect_data(self, since: Optional[datetime] = None) -> Dict[str, int]:
        return {"count": 0}

    async def analyze(self) -> Dict[str, Any]:
        return {}

    async def train_ai(self, model_type: str = "default") -> Dict[str, Any]:
        return {}

    async def index_knowledge(self, force: bool = False) -> Dict[str, int]:
        return {}

    async def get_correlations(self, correlation_type: str = "all", limit: int = 10) -> Dict[str, Any]:
        return {}

    async def get_anomalies(self, limit: int = 10) -> Dict[str, Any]:
        return {}

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "healthy"}

    async def shutdown(self):
        pass
""")

        return tmp_path

    def test_load_plugin_success(self, mock_plugin_dir):
        """Test successful plugin loading"""
        loader = PluginLoader({'plugins_path': mock_plugin_dir})

        async def run_loading():
            plugin = await loader.load_plugin("test_plugin")
            assert plugin is not None
            assert plugin.name == "test_plugin"

        asyncio.run(run_loading())

    def test_load_nonexistent_plugin(self, mock_plugin_dir):
        """Test loading non-existent plugin"""
        loader = PluginLoader({'plugins_path': mock_plugin_dir})

        async def run_loading():
            plugin = await loader.load_plugin("nonexistent")
            assert plugin is None

        asyncio.run(run_loading())


class TestPluginDiscovery:
    """Test plugin discovery functionality"""

    @pytest.fixture
    def test_plugins_dir(self):
        """Create test plugins directory"""
        test_dir = tempfile.mkdtemp()
        plugins_dir = Path(test_dir) / "plugins"
        plugins_dir.mkdir(parents=True)

        # Create mock plugin
        test_plugin = plugins_dir / "test_plugin"
        test_plugin.mkdir()

        plugin_file = test_plugin / "test_plugin_plugin.py"
        plugin_file.write_text("""
from core.module_interface import BaseModule, ModuleMetadata
from typing import Dict, Any, Optional
from datetime import datetime

class TestPlugin(BaseModule):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

    async def register(self) -> ModuleMetadata:
        return ModuleMetadata(
            name="test_plugin",
            version="1.0.0",
            description="Test",
            author="Test"
        )

    async def collect_data(self, since: Optional[datetime] = None) -> Dict[str, int]:
        return {}

    async def analyze(self) -> Dict[str, Any]:
        return {}

    async def train_ai(self, model_type: str = "default") -> Dict[str, Any]:
        return {}

    async def index_knowledge(self, force: bool = False) -> Dict[str, int]:
        return {}

    async def get_correlations(self, correlation_type: str = "all", limit: int = 10) -> Dict[str, Any]:
        return {}

    async def get_anomalies(self, limit: int = 10) -> Dict[str, Any]:
        return {}

    async def health_check(self) -> Dict[str, Any]:
        return {}

    async def shutdown(self):
        pass
""")

        yield plugins_dir
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_discover_plugins(self, test_plugins_dir):
        """Test plugin discovery"""
        loader = PluginLoader({'plugins_path': test_plugins_dir})

        async def run_discovery():
            discovered = await loader.discover_plugins()
            assert "test_plugin" in discovered

        asyncio.run(run_discovery())


class TestPluginLifecycle:
    """Test plugin lifecycle management"""

    def test_plugin_lifecycle(self, tmp_path):
        """Test complete plugin lifecycle"""
        loader = PluginLoader({'plugins_path': tmp_path})

        # Create mock plugin
        plugin_dir = tmp_path / "lifecycle_plugin"
        plugin_dir.mkdir()

        plugin_file = plugin_dir / "lifecycle_plugin_plugin.py"
        plugin_file.write_text("""
from core.module_interface import BaseModule, ModuleMetadata
from typing import Dict, Any, Optional
from datetime import datetime

class LifecyclePlugin(BaseModule):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.lifecycle = []

    async def register(self) -> ModuleMetadata:
        self.lifecycle.append('registered')
        return ModuleMetadata(
            name="lifecycle",
            version="1.0.0",
            description="Lifecycle test",
            author="Test"
        )

    async def collect_data(self, since: Optional[datetime] = None) -> Dict[str, int]:
        self.lifecycle.append('collect_data')
        return {}

    async def analyze(self) -> Dict[str, Any]:
        self.lifecycle.append('analyze')
        return {}

    async def train_ai(self, model_type: str = "default") -> Dict[str, Any]:
        return {}

    async def index_knowledge(self, force: bool = False) -> Dict[str, int]:
        return {}

    async def get_correlations(self, correlation_type: str = "all", limit: int = 10) -> Dict[str, Any]:
        return {}

    async def get_anomalies(self, limit: int = 10) -> Dict[str, Any]:
        return {}

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "healthy", "lifecycle": self.lifecycle}

    async def shutdown(self):
        self.lifecycle.append('shutdown')
""")

        async def run_lifecycle():
            plugin = await loader.load_plugin("lifecycle_plugin")
            assert plugin is not None
            assert 'registered' in plugin.lifecycle

            # Test health check
            health = await plugin.health_check()
            assert health["status"] == "healthy"
            assert 'lifecycle' in health

            # Test shutdown
            await plugin.shutdown()
            assert 'shutdown' in plugin.lifecycle

        asyncio.run(run_lifecycle())


class TestRealPlugins:
    """Test with real plugins in the system"""

    def test_discover_real_plugins(self):
        """Test discovery of actual plugins"""
        loader = PluginLoader({'plugins_path': Path('/app/plugins')})

        async def test():
            discovered = await loader.discover_plugins()
            # Should find at least the 4 enabled plugins
            assert len(discovered) >= 4
            # Should contain known plugins
            assert 'crypto' in discovered or 'news' in discovered

        asyncio.run(test())

    def test_load_real_plugin(self):
        """Test loading a real plugin"""
        loader = PluginLoader({'plugins_path': Path('/app/plugins')})

        async def test():
            # Try loading crypto plugin
            plugin = await loader.load_plugin('crypto')
            assert plugin is not None
            assert hasattr(plugin, 'name')

            # Test it has required methods
            methods = ['register', 'collect_data', 'analyze', 'shutdown']
            for method in methods:
                assert hasattr(plugin, method)

        asyncio.run(test())


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
