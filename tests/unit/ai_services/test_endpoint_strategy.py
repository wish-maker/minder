"""
Tests for AI Endpoint Strategy (Pillar 2)

Tests hybrid endpoint configuration, resolution, and fallback mechanisms.
"""

from unittest.mock import Mock, patch

import pytest
from requests.exceptions import ConnectionError as RequestConnectionError

from src.ai_services.config.endpoints import AIEndpointConfig, AIEndpointResolver, EndpointStrategy


class TestAIEndpointConfig:
    """Test AI endpoint configuration"""

    def test_default_config(self):
        """Test default configuration values"""
        config = AIEndpointConfig()

        assert config.endpoint_strategy == EndpointStrategy.LOCAL
        assert config.local_ollama_url == "http://minder-ollama:11434"
        assert config.lan_ollama_url is None
        assert config.cloud_api_url is None
        assert config.enable_fallback is True
        assert config.fallback_timeout_ms == 5000
        assert config.default_model == "llama3.2"
        assert config.embedding_model == "nomic-embed-text"

    def test_custom_config(self):
        """Test custom configuration values"""
        config = AIEndpointConfig(
            endpoint_strategy="lan",
            local_ollama_url="http://local:11434",
            lan_ollama_url="http://192.168.1.100:11434",
            cloud_api_url="https://api.openai.com/v1",
            enable_fallback=False,
            fallback_timeout_ms=3000,
            default_model="mistral",
            embedding_model="mxbai-embed-large",
        )

        assert config.endpoint_strategy == EndpointStrategy.LAN
        assert config.local_ollama_url == "http://local:11434"
        assert config.lan_ollama_url == "http://192.168.1.100:11434"
        assert config.cloud_api_url == "https://api.openai.com/v1"
        assert config.enable_fallback is False
        assert config.fallback_timeout_ms == 3000
        assert config.default_model == "mistral"
        assert config.embedding_model == "mxbai-embed-large"


class TestAIEndpointResolver:
    """Test AI endpoint resolver"""

    def test_local_strategy_no_fallback(self):
        """Test local endpoint strategy without fallback"""
        config = AIEndpointConfig(endpoint_strategy="local", enable_fallback=False)
        resolver = AIEndpointResolver(config)

        endpoint = resolver.get_endpoint()
        assert endpoint == "http://minder-ollama:11434"

    @patch("src.ai_services.config.endpoints.requests.get")
    def test_local_strategy_with_fallback_success(self, mock_get):
        """Test local endpoint strategy with healthy primary"""
        mock_get.return_value = Mock(status_code=200)

        config = AIEndpointConfig(endpoint_strategy="local", enable_fallback=True)
        resolver = AIEndpointResolver(config)

        endpoint = resolver.get_endpoint()
        assert endpoint == "http://minder-ollama:11434"

    @patch("src.ai_services.config.endpoints.requests.get")
    def test_local_strategy_fallback_to_lan(self, mock_get):
        """Test fallback from local to LAN endpoint"""

        # Local endpoint fails, LAN succeeds
        def mock_get_with_url(url, timeout=None):
            if "minder-ollama" in url:
                raise RequestConnectionError("Local unavailable")
            elif "192.168" in url:
                return Mock(status_code=200)
            return Mock(status_code=503)

        mock_get.side_effect = mock_get_with_url

        config = AIEndpointConfig(
            endpoint_strategy="local", lan_ollama_url="http://192.168.1.100:11434", enable_fallback=True
        )
        resolver = AIEndpointResolver(config)

        endpoint = resolver.get_endpoint()
        assert endpoint == "http://192.168.1.100:11434"

    @patch("src.ai_services.config.endpoints.requests.get")
    def test_local_strategy_fallback_to_cloud(self, mock_get):
        """Test fallback from local to cloud endpoint"""

        # Local and LAN fail, cloud succeeds
        def mock_get_with_url(url, timeout=None):
            if "minder-ollama" in url:
                raise RequestConnectionError("Local unavailable")
            elif "192.168" in url:
                raise RequestConnectionError("LAN unavailable")
            elif "api.openai.com" in url:
                return Mock(status_code=200)
            return Mock(status_code=503)

        mock_get.side_effect = mock_get_with_url

        config = AIEndpointConfig(
            endpoint_strategy="local",
            lan_ollama_url="http://192.168.1.100:11434",
            cloud_api_url="https://api.openai.com/v1",
            enable_fallback=True,
        )
        resolver = AIEndpointResolver(config)

        endpoint = resolver.get_endpoint()
        assert endpoint == "https://api.openai.com/v1"

    @patch("src.ai_services.config.endpoints.requests.get")
    def test_lan_strategy_with_lan_unconfigured(self, mock_get):
        """Test LAN strategy falls back to local when LAN not configured"""
        mock_get.return_value = Mock(status_code=200)

        config = AIEndpointConfig(
            endpoint_strategy="lan", lan_ollama_url=None, enable_fallback=True  # LAN not configured
        )
        resolver = AIEndpointResolver(config)

        endpoint = resolver.get_endpoint()
        # Should use local as fallback
        assert endpoint == "http://minder-ollama:11434"

    def test_lan_strategy_without_lan_config(self):
        """Test LAN strategy without LAN URL configured"""
        config = AIEndpointConfig(endpoint_strategy="lan", lan_ollama_url=None, enable_fallback=False)
        resolver = AIEndpointResolver(config)

        # Should still use local when LAN not configured
        endpoint = resolver.get_endpoint()
        assert endpoint == "http://minder-ollama:11434"

    def test_cloud_strategy_without_cloud_config(self):
        """Test cloud strategy without cloud URL configured raises error"""
        config = AIEndpointConfig(endpoint_strategy="cloud", cloud_api_url=None)
        resolver = AIEndpointResolver(config)

        with pytest.raises(ValueError, match="Cloud strategy selected but AI_CLOUD_API_URL not configured"):
            resolver.get_endpoint()

    def test_cloud_strategy_with_cloud_config(self):
        """Test cloud strategy with cloud URL configured"""
        config = AIEndpointConfig(endpoint_strategy="cloud", cloud_api_url="https://api.openai.com/v1")
        resolver = AIEndpointResolver(config)

        endpoint = resolver.get_endpoint()
        assert endpoint == "https://api.openai.com/v1"

    @patch("src.ai_services.config.endpoints.requests.get")
    def test_all_endpoints_unavailable(self, mock_get):
        """Test error when all endpoints are unavailable"""
        mock_get.side_effect = RequestConnectionError("All unavailable")

        config = AIEndpointConfig(
            endpoint_strategy="local",
            lan_ollama_url="http://192.168.1.100:11434",
            cloud_api_url="https://api.openai.com/v1",
            enable_fallback=True,
        )
        resolver = AIEndpointResolver(config)

        with pytest.raises(ConnectionError, match="All AI endpoints are unavailable"):
            resolver.get_endpoint()

    @patch("src.ai_services.config.endpoints.requests.get")
    def test_health_check_caching(self, mock_get):
        """Test that health checks are cached"""
        mock_get.return_value = Mock(status_code=200)

        config = AIEndpointConfig(endpoint_strategy="local", enable_fallback=True)
        resolver = AIEndpointResolver(config)

        # First call - should check health
        resolver.get_endpoint()
        assert mock_get.call_count == 1

        # Second call - should use cached health
        resolver.get_endpoint()
        assert mock_get.call_count == 1  # No additional call

    @patch("src.ai_services.config.endpoints.requests.get")
    def test_clear_health_cache(self, mock_get):
        """Test clearing health cache"""
        mock_get.return_value = Mock(status_code=200)

        config = AIEndpointConfig(endpoint_strategy="local", enable_fallback=True)
        resolver = AIEndpointResolver(config)

        # First call
        resolver.get_endpoint()
        assert mock_get.call_count == 1

        # Clear cache
        resolver.clear_health_cache()

        # Second call - should check health again
        resolver.get_endpoint()
        assert mock_get.call_count == 2

    @patch("src.ai_services.config.endpoints.requests.get")
    def test_health_check_fallback_to_ollama_tags(self, mock_get):
        """Test health check falls back to /api/tags for Ollama"""
        # /health fails, /api/tags succeeds
        mock_get.side_effect = [RequestConnectionError("No /health endpoint"), Mock(status_code=200)]

        config = AIEndpointConfig(endpoint_strategy="local", enable_fallback=True)
        resolver = AIEndpointResolver(config)

        # Should succeed using /api/tags
        endpoint = resolver.get_endpoint()
        assert endpoint == "http://minder-ollama:11434"
        assert mock_get.call_count == 2

    def test_unknown_strategy(self):
        """Test error on unknown endpoint strategy"""
        config = AIEndpointConfig()
        config.endpoint_strategy = "unknown"

        resolver = AIEndpointResolver(config)

        with pytest.raises(ValueError, match="Unknown endpoint strategy"):
            resolver.get_endpoint()


class TestEndpointStrategyEnum:
    """Test EndpointStrategy enum"""

    def test_strategy_values(self):
        """Test enum values"""
        assert EndpointStrategy.LOCAL == "local"
        assert EndpointStrategy.LAN == "lan"
        assert EndpointStrategy.CLOUD == "cloud"

    def test_strategy_comparison(self):
        """Test enum comparison"""
        strategy = EndpointStrategy.LOCAL
        assert strategy == "local"
        assert strategy != EndpointStrategy.LAN
        assert strategy in EndpointStrategy
