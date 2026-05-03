# src/api_gateway/domain/aggregates/gateway_aggregate.py

from datetime import datetime, timezone
from typing import Dict
from uuid import UUID

from src.shared.domain.aggregate import Aggregate
from src.shared.events.event import Event, EventMetadata


class GatewayAggregate(Aggregate):
    """
    API Gateway business logic.

    Manages routing rules and request tracking. All state changes
    are recorded as events in the Event Store for audit and
    observability (Pillar 4).

    Attributes:
        id: Aggregate unique identifier
        active_rules: Current routing rules
    """

    def __init__(self, id: UUID):
        """
        Initialize gateway aggregate.

        Args:
            id: Unique identifier for this gateway aggregate
        """
        super().__init__(id)
        self.active_rules: Dict[str, Dict] = {}

    def route_request(
        self,
        request_id: UUID,
        service_name: str,
        endpoint: str,
        response_status: int,
        latency_ms: int,
    ) -> None:
        """
        Record routing event.

        Args:
            request_id: Unique request identifier
            service_name: Target service name
            endpoint: API endpoint path
            response_status: HTTP response status
            latency_ms: Request latency in milliseconds
        """
        event = Event(
            metadata=EventMetadata(
                event_id=self._next_event_id(),
                event_type="RequestRouted",
                timestamp=datetime.now(timezone.utc),
            ),
            data={
                "request_id": str(request_id),
                "service_name": service_name,
                "endpoint": endpoint,
                "response_status": response_status,
                "latency_ms": latency_ms,
                "routed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        self._apply_event(event, version=self.version + 1)

    def update_routing_rule(
        self,
        rule_id: UUID,
        path_pattern: str,
        target_service: str,
        priority: int,
    ) -> None:
        """
        Update routing rule.

        Args:
            rule_id: Unique rule identifier
            path_pattern: URL path pattern
            target_service: Target service name
            priority: Rule priority (higher = more important)
        """
        event = Event(
            metadata=EventMetadata(
                event_id=self._next_event_id(),
                event_type="RoutingRuleUpdated",
                timestamp=datetime.now(timezone.utc),
            ),
            data={
                "rule_id": str(rule_id),
                "path_pattern": path_pattern,
                "target_service": target_service,
                "priority": priority,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        self._apply_event(event, version=self.version + 1)

    def _apply(self, event: Event) -> None:
        """
        Apply event to aggregate state.

        Args:
            event: Event to apply
        """
        if event.event_type == "RequestRouted":
            self._apply_request_routed(event)
        elif event.event_type == "RoutingRuleUpdated":
            self._apply_routing_rule_updated(event)

    def _apply_request_routed(self, event: Event) -> None:
        """
        Apply RequestRouted event to aggregate state.

        Note: Metrics tracking is handled in projection, not here.
        """
        # Request routing events don't change aggregate state
        # They're recorded for observability and metrics (Pillar 4)
        pass

    def _apply_routing_rule_updated(self, event: Event) -> None:
        """
        Apply RoutingRuleUpdated event to aggregate state.
        """
        self.active_rules[event.data["path_pattern"]] = {
            "target_service": event.data["target_service"],
            "priority": event.data["priority"],
        }

    def _next_event_id(self) -> UUID:
        """Generate next event ID for this aggregate"""
        from uuid import uuid4

        return uuid4()
