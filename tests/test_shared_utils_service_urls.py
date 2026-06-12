"""
Unit tests for Service URL utilities
"""
import pytest
from services.shared.utils.service_urls import (
    ServiceURLs,
    get_service_url,
    get_endpoint,
)


class TestServiceURLs:
    """Test ServiceURLs class"""

    def test_get_service_url_valid(self):
        """Test getting valid service URL"""
        url = ServiceURLs.get_service_url("MARKETPLACE")
        assert url == "http://minder-marketplace:8002"

    def test_get_service_url_invalid(self):
        """Test getting invalid service URL"""
        url = ServiceURLs.get_service_url("INVALID_SERVICE")
        assert url is None

    def test_get_endpoint(self):
        """Test getting full endpoint URL"""
        url = ServiceURLs.get_endpoint("MARKETPLACE", "/health")
        assert url == "http://minder-marketplace:8002/health"

    def test_get_endpoint_with_nested_path(self):
        """Test getting endpoint with nested path"""
        url = ServiceURLs.get_endpoint("MARKETPLACE", "/v1/plugins/123")
        assert url == "http://minder-marketplace:8002/v1/plugins/123"

    def test_get_endpoint_invalid_service(self):
        """Test getting endpoint for invalid service"""
        with pytest.raises(ValueError, match="Unknown service"):
            ServiceURLs.get_endpoint("INVALID_SERVICE", "/health")

    def test_get_endpoint_path_normalization(self):
        """Test path normalization in endpoint URLs"""
        # Leading slash should be handled
        url1 = ServiceURLs.get_endpoint("MARKETPLACE", "/health")
        url2 = ServiceURLs.get_endpoint("MARKETPLACE", "health")
        assert url1 == url2

    def test_all_core_services_available(self):
        """Test that all core services have URLs"""
        core_services = [
            "API_GATEWAY",
            "MARKETPLACE",
            "PLUGIN_REGISTRY",
            "PLUGIN_STATE_MANAGER",
            "RAG_PIPELINE",
        ]

        for service in core_services:
            url = ServiceURLs.get_service_url(service)
            assert url is not None
            assert isinstance(url, str)
            assert url.startswith("http://")

    def test_all_infrastructure_services_available(self):
        """Test that all infrastructure services have URLs"""
        infra_services = [
            "POSTGRES",
            "REDIS",
            "QDRANT",
            "NEO4J",
            "MINIO",
            "OLLAMA",
        ]

        for service in infra_services:
            url = ServiceURLs.get_service_url(service)
            assert url is not None

    def test_update_from_env(self, monkeypatch):
        """Test updating URLs from environment variables"""
        import os

        # Set environment variable
        monkeypatch.setenv("MARKETPLACE_URL", "http://custom-marketplace:9000")

        # Update from environment
        ServiceURLs.update_from_env()

        # Check that URL was updated
        url = ServiceURLs.get_service_url("MARKETPLACE")
        assert url == "http://custom-marketplace:9000"


class TestGetServiceURL:
    """Test get_service_url convenience function"""

    def test_get_service_url_valid(self):
        """Test getting valid service URL"""
        url = get_service_url("MARKETPLACE")
        assert url == "http://minder-marketplace:8002"

    def test_get_service_url_invalid(self):
        """Test getting invalid service URL raises error"""
        with pytest.raises(ValueError, match="Unknown service"):
            get_service_url("INVALID_SERVICE")


class TestGetEndpoint:
    """Test get_endpoint convenience function"""

    def test_get_endpoint(self):
        """Test getting endpoint URL"""
        url = get_endpoint("MARKETPLACE", "/plugins")
        assert url == "http://minder-marketplace:8002/plugins"

    def test_get_endpoint_invalid_service(self):
        """Test getting endpoint for invalid service raises error"""
        with pytest.raises(ValueError, match="Unknown service"):
            get_endpoint("INVALID_SERVICE", "/test")
