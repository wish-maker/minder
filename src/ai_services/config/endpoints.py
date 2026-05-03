"""
AI Endpoint Configuration with Hybrid Strategy Support (Pillar 2)

Provides dynamic endpoint routing for AI services with fallback mechanisms:
- Local Docker Ollama (http://minder-ollama:11434)
- LAN network Ollama (http://192.168.x.x:11434)
- Cloud/Remote API (vLLM/OpenAI compatible)
"""

import logging
from enum import Enum
from typing import Optional

import requests
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class EndpointStrategy(str, Enum):
    """AI Endpoint deployment strategies"""

    LOCAL = "local"
    LAN = "lan"
    CLOUD = "cloud"


class AIEndpointConfig(BaseSettings):
    """
    AI Endpoint configuration with hybrid strategy support (Pillar 2)

    Environment variables:
        AI_ENDPOINT_STRATEGY: Primary strategy selection (local, lan, cloud)
        AI_LOCAL_OLLAMA_URL: Local Docker Ollama endpoint
        AI_LAN_OLLAMA_URL: LAN network Ollama endpoint
        AI_CLOUD_API_URL: Cloud API endpoint
        AI_ENABLE_FALLBACK: Enable fallback to alternative endpoints
        AI_FALLBACK_TIMEOUT_MS: Timeout for endpoint health checks
        AI_DEFAULT_MODEL: Default model for inference
        AI_EMBEDDING_MODEL: Model for embedding generation
    """

    # Primary strategy selection
    endpoint_strategy: EndpointStrategy = EndpointStrategy.LOCAL

    # Endpoint URLs
    local_ollama_url: str = "http://minder-ollama:11434"
    lan_ollama_url: Optional[str] = None  # e.g., "http://192.168.1.100:11434"
    cloud_api_url: Optional[str] = None  # e.g., "https://api.openai.com/v1"

    # Fallback configuration
    enable_fallback: bool = True
    fallback_timeout_ms: int = 5000

    # Model configuration
    default_model: str = "llama3.2"
    embedding_model: str = "nomic-embed-text"

    model_config = ConfigDict(env_file=".env", env_prefix="AI_")


class AIEndpointResolver:
    """
    Resolve AI endpoint based on strategy and availability

    Implements Pillar 2 hybrid endpoint strategy with automatic fallback:
    1. Try primary endpoint based on strategy
    2. If unhealthy and fallback enabled, try alternatives
    3. Raise ConnectionError if all endpoints unavailable
    """

    def __init__(self, config: AIEndpointConfig):
        """
        Initialize endpoint resolver

        Args:
            config: AI endpoint configuration
        """
        self.config = config
        self._endpoint_health = {}  # Cache endpoint health status

    def get_endpoint(self) -> str:
        """
        Get active AI endpoint URL based on strategy and health

        Returns:
            Active endpoint URL

        Raises:
            ValueError: Unknown endpoint strategy
            ConnectionError: All endpoints unavailable
        """
        strategy = self.config.endpoint_strategy

        if strategy == EndpointStrategy.LOCAL:
            return self._get_with_fallback(
                self.config.local_ollama_url, self.config.lan_ollama_url, self.config.cloud_api_url
            )
        elif strategy == EndpointStrategy.LAN:
            if not self.config.lan_ollama_url:
                logger.warning("LAN strategy selected but AI_LAN_OLLAMA_URL not configured")
                # Fallback to local if LAN not configured
                return self._get_with_fallback(self.config.local_ollama_url, self.config.cloud_api_url)
            return self._get_with_fallback(
                self.config.lan_ollama_url, self.config.local_ollama_url, self.config.cloud_api_url
            )
        elif strategy == EndpointStrategy.CLOUD:
            if not self.config.cloud_api_url:
                raise ValueError("Cloud strategy selected but AI_CLOUD_API_URL not configured")
            return self.config.cloud_api_url

        raise ValueError(f"Unknown endpoint strategy: {strategy}")

    def _get_with_fallback(self, primary: str, *fallbacks) -> str:
        """
        Get endpoint with fallback support

        Args:
            primary: Primary endpoint to try
            *fallbacks: Alternative endpoints to try if primary fails

        Returns:
            First available endpoint URL

        Raises:
            ConnectionError: All endpoints unavailable
        """
        if not self.config.enable_fallback:
            logger.debug(f"Fallback disabled, using primary endpoint: {primary}")
            return primary

        # Try primary endpoint
        if self._check_endpoint_health(primary):
            logger.debug(f"Using primary endpoint: {primary}")
            return primary

        # Try fallbacks in order
        for fallback in fallbacks:
            if fallback and self._check_endpoint_health(fallback):
                logger.info(f"Falling back to alternative endpoint: {fallback}")
                return fallback

        raise ConnectionError(
            f"All AI endpoints are unavailable. " f"Tried: {primary}, {', '.join(str(f) for f in fallbacks if f)}"
        )

    def _check_endpoint_health(self, url: str) -> bool:
        """
        Check if endpoint is healthy

        Args:
            url: Endpoint URL to check

        Returns:
            True if endpoint is healthy, False otherwise
        """
        # Check cache first
        if url in self._endpoint_health:
            return self._endpoint_health[url]

        try:
            timeout_sec = self.config.fallback_timeout_ms / 1000
            # Try /health endpoint first
            response = requests.get(f"{url}/health", timeout=timeout_sec)
            is_healthy = response.status_code == 200
        except Exception:
            # If /health fails, try /api/tags (Ollama-specific)
            try:
                response = requests.get(f"{url}/api/tags", timeout=timeout_sec)
                is_healthy = response.status_code == 200
            except Exception as e:
                logger.debug(f"Endpoint health check failed for {url}: {e}")
                is_healthy = False

        # Cache result
        self._endpoint_health[url] = is_healthy
        return is_healthy

    def clear_health_cache(self) -> None:
        """Clear cached health status for all endpoints"""
        self._endpoint_health.clear()
        logger.debug("Endpoint health cache cleared")
