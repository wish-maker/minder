# src/api_gateway/projections/routing_projection_handler.py

import json
import logging
from typing import Any, Dict

import psycopg2
import redis

logger = logging.getLogger(__name__)


class RoutingProjectionHandler:
    """
    Gateway projection - Redis-first for ultra-fast routing (Pillar 4: Observability).

    Implements Redis-first caching strategy with PostgreSQL as audit trail.
    Redis TTL: 1 second (ultra-fast routing with cache invalidation)
    PostgreSQL: Audit trail (for compliance and debugging)

    This supports Pillar 2 (Hybrid AI Endpoints) by providing fast routing decisions
    and Pillar 3 (RabbitMQ) through event-driven architecture.
    """

    def __init__(self, pg_url: str, redis_url: str, rabbitmq_url: str):
        """
        Initialize projection handler.

        Args:
            pg_url: PostgreSQL connection URL
            redis_url: Redis connection URL
            rabbitmq_url: RabbitMQ connection URL (for future use)
        """
        self.pg_url = pg_url
        self.redis_url = redis_url
        self.rabbitmq_url = rabbitmq_url
        self._pg_conn = None
        self._redis_client = None

    def connect(self):
        """Connect to databases"""
        if self._pg_conn is None or self._pg_conn.closed:
            self._pg_conn = psycopg2.connect(self.pg_url)

        if self._redis_client is None:
            self._redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2,
            )

    def close(self):
        """Close database connections"""
        if self._pg_conn and not self._pg_conn.closed:
            self._pg_conn.close()
            self._pg_conn = None

        if self._redis_client:
            self._redis_client.close()
            self._redis_client = None

    def handle_event(self, event_type: str, event_data: Dict[str, Any], is_replay: bool = False) -> None:
        """
        Handle incoming events and update projections.

        Args:
            event_type: Type of event (e.g., "RequestRouted", "RoutingRuleUpdated")
            event_data: Event payload
            is_replay: Whether this is a replay event
        """
        if event_type == "RoutingRuleUpdated":
            self._handle_routingruleupdated(event_data, is_replay)
        elif event_type == "RequestRouted":
            self._handle_requestrouted(event_data, is_replay)
        else:
            logger.warning(f"Unknown event type: {event_type}")

    def _handle_routingruleupdated(self, event_data: Dict[str, Any], is_replay: bool) -> None:
        """
        Handle routing rule updates - Redis-first strategy.

        Redis TTL: 1 second (ultra-fast routing with cache invalidation)
        PostgreSQL: Audit trail (for compliance and debugging)

        Args:
            event_data: Event payload containing routing rule update
            is_replay: Whether this is a replay event
        """
        self.connect()

        try:
            # Update Redis cache (TTL: 1s for ultra-fast routing)
            redis_key = f"routing:rule:{event_data['path_pattern']}"
            routing_data = {
                "path": event_data["path_pattern"],
                "service": event_data["target_service"],
                "priority": event_data["priority"],
                "updated_at": event_data["updated_at"],
            }

            self._redis_client.setex(
                redis_key,
                1,  # 1 second TTL - balances speed with consistency
                json.dumps(routing_data),
            )

            # Update PostgreSQL for audit trail
            with self._pg_conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO gateway_routing_audit (
                        rule_id, path_pattern, target_service,
                        priority, updated_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (rule_id) DO UPDATE SET
                        target_service = EXCLUDED.target_service,
                        priority = EXCLUDED.priority,
                        updated_at = EXCLUDED.updated_at
                """,
                    (
                        str(event_data["rule_id"]),
                        event_data["path_pattern"],
                        event_data["target_service"],
                        event_data["priority"],
                        event_data["updated_at"],
                    ),
                )

            self._pg_conn.commit()

            logger.info(f"Routing rule updated: {event_data['path_pattern']} -> {event_data['target_service']}")

        except Exception as e:
            if self._pg_conn:
                self._pg_conn.rollback()
            logger.error(f"Error handling RoutingRuleUpdated: {e}")
            raise

    def _handle_requestrouted(self, event_data: Dict[str, Any], is_replay: bool) -> None:
        """
        Handle request routing events for metrics collection.

        Args:
            event_data: Event payload containing routing information
            is_replay: Whether this is a replay event
        """
        self.connect()

        try:
            # Store metrics in Redis with 5-minute TTL
            metrics_key = f"routing:metrics:{event_data['service_name']}"
            metrics_data = {
                "request_id": event_data["request_id"],
                "endpoint": event_data["endpoint"],
                "status": event_data["response_status"],
                "latency_ms": event_data["latency_ms"],
                "timestamp": event_data["routed_at"],
            }

            # Use Redis list for recent requests (max 1000)
            self._redis_client.lpush(metrics_key, json.dumps(metrics_data))
            self._redis_client.ltrim(metrics_key, 0, 999)
            self._redis_client.expire(metrics_key, 300)  # 5 minutes TTL

            logger.debug(
                f"Request routed: {event_data['service_name']} - Status: {event_data['response_status']}, Latency: {event_data['latency_ms']}ms"
            )

        except Exception as e:
            logger.error(f"Error handling RequestRouted: {e}")
            # Don't raise - metrics failures shouldn't block routing

    def get_routing_rule(self, path_pattern: str) -> Dict[str, Any]:
        """
        Retrieve routing rule from Redis cache.

        Args:
            path_pattern: URL path pattern

        Returns:
            Routing rule data or None if not found
        """
        self.connect()

        try:
            redis_key = f"routing:rule:{path_pattern}"
            data = self._redis_client.get(redis_key)

            if data:
                return json.loads(data)

            return None

        except Exception as e:
            logger.error(f"Error retrieving routing rule: {e}")
            return None

    def get_service_metrics(self, service_name: str) -> list:
        """
        Retrieve recent metrics for a service.

        Args:
            service_name: Service name

        Returns:
            List of recent routing metrics
        """
        self.connect()

        try:
            metrics_key = f"routing:metrics:{service_name}"
            data = self._redis_client.lrange(metrics_key, 0, 99)

            return [json.loads(item) for item in data]

        except Exception as e:
            logger.error(f"Error retrieving service metrics: {e}")
            return []
