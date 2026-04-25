#!/usr/bin/env python3
"""
Test Core Plugin Interface
Unit tests for BaseModule and related classes
"""

from datetime import datetime

import pytest

from src.core.interface import BaseModule, ModuleMetadata, ModuleStatus


class TestModuleStatus:
    """Test ModuleStatus enum"""

    def test_status_values(self):
        """Test that all status values are accessible"""
        assert ModuleStatus.UNREGISTERED.value == "unregistered"
        assert ModuleStatus.REGISTERED.value == "registered"
        assert ModuleStatus.READY.value == "ready"
        assert ModuleStatus.STOPPED.value == "stopped"
        assert ModuleStatus.ERROR.value == "error"
        assert ModuleStatus.COLLECTING.value == "collecting"
        assert ModuleStatus.ANALYZING.value == "analyzing"


class TestModuleMetadata:
    """Test ModuleMetadata class"""

    def test_create_metadata(self):
        """Test creating module metadata"""
        metadata = ModuleMetadata(
            name="test_plugin",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
        )

        assert metadata.name == "test_plugin"
        assert metadata.version == "1.0.0"
        assert metadata.description == "Test plugin for unit testing"
        assert metadata.author == "Test Author"
        assert metadata.capabilities == []
        assert metadata.dependencies == []

    def test_metadata_with_lists(self):
        """Test creating metadata with capabilities and dependencies"""
        metadata = ModuleMetadata(
            name="test_plugin",
            version="1.0.0",
            description="Test plugin",
            author="Test",
            capabilities=["data_collection", "analysis"],
            dependencies=["redis", "postgres"],
            data_sources=["api"],
            databases=["postgres"],
        )

        assert len(metadata.capabilities) == 2
        assert "data_collection" in metadata.capabilities
        assert len(metadata.dependencies) == 2
        assert "redis" in metadata.dependencies


class TestBaseModule:
    """Test BaseModule abstract class"""

    def test_base_module_cannot_be_instantiated(self):
        """Test that BaseModule cannot be instantiated directly"""
        with pytest.raises(TypeError):
            BaseModule(config={})

    def test_concrete_module_implementation(self):
        """Test creating a concrete plugin implementation"""

        class TestPlugin(BaseModule):
            """Test plugin implementation"""

            async def register(self):
                self.metadata = ModuleMetadata(
                    name="test_plugin",
                    version="1.0.0",
                    description="Test plugin",
                    author="Test",
                )
                return self.metadata

        # Create and test concrete implementation
        plugin = TestPlugin(config={})

        assert plugin.status == ModuleStatus.UNREGISTERED
        assert plugin.config == {}
        assert plugin.metadata is None

        # Test registration
        import asyncio

        metadata = asyncio.run(plugin.register())
        assert metadata.name == "test_plugin"
        assert metadata.version == "1.0.0"
        assert plugin.metadata == metadata

        # Test initialization (sets status to READY)
        asyncio.run(plugin.initialize())
        assert plugin.status == ModuleStatus.READY

        # Test health check
        health = asyncio.run(plugin.health_check())
        assert health["status"] == "ready"
        assert health["healthy"] is True

        # Test optional methods (base implementations)
        data_result = asyncio.run(plugin.collect_data())
        assert data_result["records_collected"] == 0
        assert "not implemented" in data_result["message"]

        analysis_result = asyncio.run(plugin.analyze())
        assert analysis_result["metrics"] == {}

        # Test helper methods
        plugin.log("Test message")
        assert plugin.get_config("nonexistent", "default") == "default"

        # Test config with nested keys
        plugin.config = {"database": {"host": "localhost", "port": 5432}}
        assert plugin.get_config("database.host") == "localhost"
        assert plugin.get_config("database.port") == 5432


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
