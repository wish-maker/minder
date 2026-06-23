"""
Service Registry with Circuit Breaker

Manages service discovery, health checks, and circuit breaker pattern.
Prevents cascading failures by tracking service health and breaking circuits when failures occur.
"""

import logging
import time

import httpx

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """
    Dynamic service registry with health tracking and circuit breaking

    Implements circuit breaker pattern to prevent cascading failures
    and provides automatic service discovery with health monitoring.

    Attributes:
        services: Dictionary mapping service names to their URLs
        health_status: Track current health status of each service
        circuit_breakers: Track circuit breaker states for each service
        last_check: Timestamp of last health check for each service
    """

    def __init__(self) -> None:
        """Initialize service registry with default service endpoints"""
        from config import settings

        self.services = {
            "plugin_registry": settings.PLUGIN_REGISTRY_URL,
            "rag_pipeline": settings.RAG_PIPELINE_URL,
            "model_management": settings.MODEL_MANAGEMENT_URL,
        }
        self.health_status = {}  # Track service health
        self.circuit_breakers = {}  # Track circuit breaker states
        self.last_check = {}  # Track last health check time

    def get_service_url(self, service_name: str) -> str:
        """
        Get service URL with circuit breaker check

        Args:
            service_name: Name of the service to get URL for

        Returns:
            Service URL if available and circuit breaker allows

        Raises:
            ValueError: If service name is unknown
            HTTPException: If circuit breaker is open for the service
        """
        if service_name not in self.services:
            raise ValueError(f"Unknown service: {service_name}")

        # Check circuit breaker
        circuit_state = self.circuit_breakers.get(
            service_name, {"failures": 0, "last_failure": 0, "state": "closed"}
        )

        # If circuit is open, check if it should be reset
        if circuit_state["state"] == "open":
            time_since_failure = time.time() - circuit_state["last_failure"]
            if time_since_failure > 60:  # 60 second timeout
                # Try to close circuit
                circuit_state["state"] = "half_open"
                self.circuit_breakers[service_name] = circuit_state
                logger.info(f"🔄 Circuit breaker half-open for {service_name}")
            else:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=503,
                    detail=f"Service {service_name} is temporarily unavailable (circuit breaker open)",
                )

        return self.services[service_name]

    def record_service_call(self, service_name: str, success: bool):
        """Record service call result for circuit breaker"""
        if service_name not in self.circuit_breakers:
            self.circuit_breakers[service_name] = {
                "failures": 0,
                "last_failure": 0,
                "state": "closed",
            }

        circuit_state = self.circuit_breakers[service_name]

        if success:
            # Reset failures on success
            if circuit_state["state"] == "half_open":
                circuit_state["state"] = "closed"
                circuit_state["failures"] = 0
                logger.info(f"✅ Circuit breaker closed for {service_name}")
            else:
                circuit_state["failures"] = max(0, circuit_state["failures"] - 1)
        else:
            # Increment failures
            circuit_state["failures"] += 1
            circuit_state["last_failure"] = time.time()

            # Open circuit after 3 consecutive failures
            if circuit_state["failures"] >= 3:
                circuit_state["state"] = "open"
                logger.error(
                    f"⚠️ Circuit breaker opened for {service_name} after {circuit_state['failures']} failures"
                )

        self.circuit_breakers[service_name] = circuit_state

    async def check_service_health(
        self, service_name: str, http_client: httpx.AsyncClient
    ) -> bool:
        """Check health of a specific service"""
        try:
            service_url = self.services.get(service_name)
            if not service_url:
                return False

            health_url = f"{service_url}/health"
            response = await http_client.get(health_url, timeout=5.0)
            is_healthy = response.status_code == 200

            self.health_status[service_name] = is_healthy
            self.last_check[service_name] = time.time()
            return is_healthy

        except Exception as e:
            logger.warning(f"Health check failed for {service_name}: {e}")
            self.health_status[service_name] = False
            self.last_check[service_name] = time.time()
            return False
