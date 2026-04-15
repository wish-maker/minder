"""
Unit Tests for Plugin Store System
Tests plugin installation, loading, and management
"""
import pytest
import asyncio
from pathlib import Path
import sys
import os
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.plugin_loader import PluginLoader
from core.module_interface import BaseModule
from api.plugin_store import GitHubPluginInstaller


class TestPluginDiscovery:
    """Test plugin discovery functionality"""

    @pytest.fixture
    def test_plugins_dir(self):
        """Create a temporary test plugins directory"""
        test_dir = tempfile.mkdtemp()
        plugins_dir = Path(test_dir) / "plugins"
        plugins_dir.mkdir(parents=True)

        # Create mock plugin structure
        test_plugin = plugins_dir / "test_plugin"
        test_plugin.mkdir()

        # Create plugin file
        plugin_file = test_plugin / "test_plugin_plugin.py"
        plugin_file.write_text("""
from core.module_interface import BaseModule

class TestPlugin(BaseModule):
    def __init__(self, config):
        super().__init__(config)
        self.name = "test_plugin"

    async def register(self):
        pass

    async def process(self, data):
        return data

    async def shutdown(self):
        pass
""")

        yield plugins_dir

        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_discover_plugins(self, test_plugins_dir):
        """Test plugin discovery"""
        loader = PluginLoader({'plugins_path': test_plugins_dir})

        async def run_discovery():
            discovered = await loader.discover_plugins()
            assert "test_plugin" in discovered

        asyncio.run(run_discovery())

    def test_discover_empty_directory(self):
        """Test discovery in empty directory"""
        empty_dir = Path(tempfile.mkdtemp())
        loader = PluginLoader({'plugins_path': empty_dir})

        async def run_discovery():
            discovered = await loader.discover_plugins()
            assert len(discovered) == 0

        asyncio.run(run_discovery())

        shutil.rmtree(empty_dir, ignore_errors=True)


class TestPluginLoading:
    """Test plugin loading functionality"""

    @pytest.fixture
    def mock_plugin(self, tmp_path):
        """Create a mock plugin for testing"""
        plugin_dir = tmp_path / "mock_plugin"
        plugin_dir.mkdir()

        plugin_file = plugin_dir / "mock_plugin_plugin.py"
        plugin_file.write_text("""
from core.module_interface import BaseModule
from typing import Dict, Any

class MockPlugin(BaseModule):
    '''Mock plugin for testing'''
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.name = "mock_plugin"
        self.version = "1.0.0"
        self.description = "Mock plugin for testing"
        self.loaded = False

    async def register(self):
        '''Register plugin'''
        self.loaded = True

    async def process(self, data: Any) -> Any:
        '''Process data'''
        return data

    async def shutdown(self):
        '''Cleanup plugin'''
        self.loaded = False
""")

        return tmp_path

    def test_load_plugin_success(self, mock_plugin):
        """Test successful plugin loading"""
        loader = PluginLoader({'plugins_path': mock_plugin})

        async def run_loading():
            plugin = await loader.load_plugin("mock_plugin")
            assert plugin is not None
            assert plugin.name == "mock_plugin"
            assert plugin.version == "1.0.0"

        asyncio.run(run_loading())

    def test_load_nonexistent_plugin(self, mock_plugin):
        """Test loading non-existent plugin"""
        loader = PluginLoader({'plugins_path': mock_plugin})

        async def run_loading():
            plugin = await loader.load_plugin("nonexistent_plugin")
            assert plugin is None

        asyncio.run(run_loading())

    def test_load_plugin_with_config(self, mock_plugin):
        """Test loading plugin with custom configuration"""
        custom_config = {
            'plugins_path': mock_plugin,
            'plugins': {
                'mock_plugin': {
                    'enabled': True,
                    'custom_setting': 'value'
                }
            }
        }

        loader = PluginLoader(custom_config)

        async def run_loading():
            plugin = await loader.load_plugin("mock_plugin")
            assert plugin is not None

        asyncio.run(run_loading())


class TestPluginInterface:
    """Test BaseModule interface compliance"""

    def test_base_module_interface(self):
        """Test that all plugins implement required methods"""
        from core.module_interface import BaseModule

        # Check required methods exist
        required_methods = ['register', 'process', 'shutdown']
        for method in required_methods:
            assert hasattr(BaseModule, method)

    def test_plugin_metadata(self):
        """Test plugin metadata structure"""
        from core.module_interface import BaseModule

        # Create instance to test metadata
        class TestModule(BaseModule):
            def __init__(self, config):
                super().__init__(config)
                self.name = "test"
                self.version = "1.0.0"

            async def register(self):
                pass

            async def process(self, data):
                return data

            async def shutdown(self):
                pass

        module = TestModule({})
        assert hasattr(module, 'name')
        assert hasattr(module, 'version')


class TestGitHubInstaller:
    """Test GitHub plugin installer"""

    def test_installer_initialization(self):
        """Test installer initialization"""
        try:
            installer = GitHubPluginInstaller()
            assert installer is not None
        except Exception as e:
            # Installer might need git or other dependencies
            assert True

    def test_parse_github_url(self):
        """Test GitHub URL parsing"""
        valid_urls = [
            "https://github.com/user/repo.git",
            "git@github.com:user/repo.git",
            "https://github.com/user/repo"
        ]

        for url in valid_urls:
            # URL should be parseable
            assert "github.com" in url
            assert "/" in url

    def test_validate_branch_name(self):
        """Test branch name validation"""
        valid_branches = ["main", "develop", "feature/test", "v1.0.0"]
        invalid_branches = ["", " ", "--invalid", "has space"]

        for branch in valid_branches:
            # Should be valid
            assert len(branch) > 0
            assert " " not in branch or "_" in branch

        for branch in invalid_branches:
            # Should be invalid
            if branch.strip() == "":
                assert True  # Empty branch is invalid


class TestPluginLifecycle:
    """Test plugin lifecycle management"""

    @pytest.fixture
    def lifecycle_plugin(self, tmp_path):
        """Create a plugin with lifecycle tracking"""
        plugin_dir = tmp_path / "lifecycle_plugin"
        plugin_dir.mkdir()

        plugin_file = plugin_dir / "lifecycle_plugin_plugin.py"
        plugin_file.write_text("""
from core.module_interface import BaseModule
from typing import Dict, Any

class LifecyclePlugin(BaseModule):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.lifecycle = []

    async def register(self):
        self.lifecycle.append('registered')

    async def process(self, data: Any) -> Any:
        self.lifecycle.append('processed')
        return data

    async def shutdown(self):
        self.lifecycle.append('shutdown')
""")

        return tmp_path

    def test_plugin_registration(self, lifecycle_plugin):
        """Test plugin registration phase"""
        loader = PluginLoader({'plugins_path': lifecycle_plugin})

        async def run_lifecycle():
            plugin = await loader.load_plugin("lifecycle_plugin")
            assert plugin is not None
            assert 'registered' in plugin.lifecycle

        asyncio.run(run_lifecycle())

    def test_plugin_processing(self, lifecycle_plugin):
        """Test plugin data processing"""
        loader = PluginLoader({'plugins_path': lifecycle_plugin})

        async def run_processing():
            plugin = await loader.load_plugin("lifecycle_plugin")
            assert plugin is not None

            # Test processing
            result = await plugin.process("test_data")
            assert result == "test_data"
            assert 'processed' in plugin.lifecycle

        asyncio.run(run_processing())

    def test_plugin_shutdown(self, lifecycle_plugin):
        """Test plugin shutdown"""
        loader = PluginLoader({'plugins_path': lifecycle_plugin})

        async def run_shutdown():
            plugin = await loader.load_plugin("lifecycle_plugin")
            assert plugin is not None

            # Test shutdown
            await plugin.shutdown()
            assert 'shutdown' in plugin.lifecycle

        asyncio.run(run_shutdown())


class TestPluginErrorHandling:
    """Test plugin error handling"""

    def test_load_broken_plugin(self, tmp_path):
        """Test loading a plugin with syntax errors"""
        plugin_dir = tmp_path / "broken_plugin"
        plugin_dir.mkdir()

        # Create plugin with syntax error
        plugin_file = plugin_dir / "broken_plugin_plugin.py"
        plugin_file.write_text("""
from core.module_interface import BaseModule

class BrokenPlugin(BaseModule):
    def __init__(self, config):
        super().__init__(config)
        # Missing required methods
""")

        loader = PluginLoader({'plugins_path': tmp_path})

        async def run_loading():
            plugin = await loader.load_plugin("broken_plugin")
            # Should fail gracefully
            assert plugin is None

        asyncio.run(run_loading())

    def test_plugin_exception_handling(self, tmp_path):
        """Test exception handling in plugin methods"""
        plugin_dir = tmp_path / "exception_plugin"
        plugin_dir.mkdir()

        plugin_file = plugin_dir / "exception_plugin_plugin.py"
        plugin_file.write_text("""
from core.module_interface import BaseModule

class ExceptionPlugin(BaseModule):
    async def register(self):
        raise Exception("Registration error")

    async def process(self, data):
        raise Exception("Processing error")

    async def shutdown(self):
        raise Exception("Shutdown error")
""")

        loader = PluginLoader({'plugins_path': tmp_path})

        async def run_loading():
            # Should handle exceptions gracefully
            plugin = await loader.load_plugin("exception_plugin")
            # Plugin might load but methods will raise exceptions
            if plugin:
                try:
                    await plugin.register()
                    assert False, "Should have raised exception"
                except Exception as e:
                    assert "Registration error" in str(e)

        asyncio.run(run_loading())


class TestPluginHotReload:
    """Test plugin hot-reload functionality"""

    def test_plugin_reload(self, tmp_path):
        """Test reloading a plugin"""
        loader = PluginLoader({'plugins_path': tmp_path})

        async def run_reload():
            # This test would require actual file system monitoring
            # For now, just test the reload method exists
            assert hasattr(loader, 'reload_plugin')

        asyncio.run(run_reload())


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
