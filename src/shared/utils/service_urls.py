"""
Service URL configuration utilities
Central management of internal service URLs and endpoints
"""
import os
from typing import Optional
from urllib.parse import urljoin

# Ollama URL from environment or default to local
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://minder-ollama:11434")


class ServiceURLs:
    """
    Central management of service URLs
    All internal service communication should use these URLs
    """

    # ============================================================================
    # Core Services
    # ============================================================================

    API_GATEWAY: str = "http://minder-api-gateway:8000"
    MARKETPLACE: str = "http://minder-marketplace:8002"
    PLUGIN_REGISTRY: str = "http://minder-plugin-registry:8001"
    PLUGIN_STATE_MANAGER: str = "http://minder-plugin-state-manager:8003"
    RAG_PIPELINE: str = "http://minder-rag-pipeline:8004"
    TTS_STT_SERVICE: str = "http://minder-tts-service:8006"
    MODEL_MANAGEMENT: str = "http://minder-model-management:8005"
    GRAPH_RAG: str = "http://minder-graph-rag:8009"

    # ============================================================================
    # Infrastructure Services
    # ============================================================================

    POSTGRES: str = "postgres://minder:minder@postgres:5432"
    REDIS: str = "redis://redis:6379"
    QDRANT: str = "http://qdrant:6333"
    NEO4J: str = "bolt://neo4j:7687"
    MINIO: str = "http://minio:9000"
    RABBITMQ: str = "amqp://rabbitmq:5672"
    OLLAMA: str = _OLLAMA_BASE_URL

    # ============================================================================
    # Observability Services
    # ============================================================================

    GRAFANA: str = "http://grafana:3000"
    PROMETHEUS: str = "http://prometheus:9090"
    JAEGER: str = "http://jaeger:16686"
    INFLUXDB: str = "http://influxdb:8086"

    # ============================================================================
    # Security Services
    # ============================================================================

    AUTH_GATEWAY: str = "http://minder-authelia:9091"
    TRAEFIK: str = "http://traefik:8080"

    @classmethod
    def get_service_url(cls, service_name: str) -> Optional[str]:
        """
        Get URL for a service by name

        Args:
            service_name: Name of the service (e.g., "MARKETPLACE", "PLUGIN_REGISTRY")

        Returns:
            Service URL or None if not found

        Example:
            >>> url = ServiceURLs.get_service_url("MARKETPLACE")
            >>> print(url)  # "http://minder-marketplace:8002"
        """
        return getattr(cls, service_name.upper(), None)

    @classmethod
    def get_endpoint(cls, service_name: str, path: str) -> str:
        """
        Get full URL for a specific endpoint

        Args:
            service_name: Name of the service
            path: Endpoint path (e.g., "/health", "/plugins")

        Returns:
            Full URL to the endpoint

        Example:
            >>> url = ServiceURLs.get_endpoint("MARKETPLACE", "/health")
            >>> print(url)  # "http://minder-marketplace:8002/health"
        """
        base_url = cls.get_service_url(service_name)
        if not base_url:
            raise ValueError(f"Unknown service: {service_name}")

        return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))

    @classmethod
    def update_from_env(cls) -> None:
        """
        Update service URLs from environment variables
        Allows runtime configuration via environment

        Example:
            >>> import os
            >>> os.environ["MARKETPLACE_URL"] = "http://marketplace.local:8002"
            >>> ServiceURLs.update_from_env()
        """
        import os

        for key in dir(cls):
            if key.isupper() and not key.startswith("_"):
                env_key = f"{key}_URL"
                env_value = os.getenv(env_key)
                if env_value:
                    setattr(cls, key, env_value)


def get_service_url(service_name: str) -> str:
    """
    Convenience function to get service URL

    Args:
        service_name: Name of the service

    Returns:
        Service URL

    Example:
        >>> url = get_service_url("MARKETPLACE")
    """
    url = ServiceURLs.get_service_url(service_name)
    if not url:
        raise ValueError(f"Unknown service: {service_name}")
    return url


def get_endpoint(service_name: str, path: str) -> str:
    """
    Convenience function to get endpoint URL

    Args:
        service_name: Name of the service
        path: Endpoint path

    Returns:
        Full endpoint URL

    Example:
        >>> url = get_endpoint("MARKETPLACE", "/plugins")
    """
    return ServiceURLs.get_endpoint(service_name, path)
