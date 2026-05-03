# src/api_gateway/domain/events/gateway_events.py

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from src.shared.events.event import DomainEvent


@dataclass
class RequestRouted(DomainEvent):
    """Emitted when request is routed to service"""

    request_id: UUID = field(default_factory=uuid4)
    service_name: str = ""
    endpoint: str = ""
    response_status: int = 0
    latency_ms: int = 0
    routed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RoutingRuleUpdated(DomainEvent):
    """Emitted when routing rules are updated"""

    rule_id: UUID = field(default_factory=uuid4)
    path_pattern: str = ""
    target_service: str = ""
    priority: int = 0
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
