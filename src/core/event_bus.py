import asyncio

"""
Minder Event Bus
Pub/Sub messaging for inter-module communication
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Standard event types"""

    MODULE_REGISTERED = "module_registered"
    MODULE_READY = "module_ready"
    MODULE_ERROR = "module_error"
    DATA_COLLECTED = "data_collected"
    ANALYSIS_COMPLETE = "analysis_complete"
    MODEL_TRAINED = "model_trained"
    KNOWLEDGE_INDEXED = "knowledge_indexed"
    ANOMALY_DETECTED = "anomaly_detected"
    CORRELATION_FOUND = "correlation_found"
    USER_QUERY = "user_query"
    SYSTEM_SHUTDOWN = "system_shutdown"


@dataclass
class Event:
    """Event message"""

    type: EventType
    source: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "source": self.source,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
        }


class EventBus:
    """
    Asynchronous event bus for module communication

    Features:
    - Pub/Sub messaging
    - Event filtering and routing
    - Dead letter queue for failed events
    - Event replay for debugging
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._event_history: List[Event] = []
        self._dead_letter_queue: List[Event] = []
        self._max_history = config.get("max_event_history", 10000)
        self._lock = asyncio.Lock()

    async def publish(self, event: Event) -> bool:
        """Publish event to all subscribers"""
        try:
            # Store in history
            await self._store_event(event)

            # Get subscribers for this event type
            subscribers = await self._get_subscribers(event.type)

            if not subscribers:
                logger.debug(f"No subscribers for event: {event.type.value}")
                return True

            # Publish to all subscribers concurrently
            tasks = [self._notify_subscriber(subscriber, event) for subscriber in subscribers]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check for failures
            failed = sum(1 for r in results if isinstance(r, Exception))
            if failed > 0:
                logger.warning(
                    f"{failed}/{len(results)} subscribers failed for event: {event.type.value}"
                )

            return failed == 0

        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
            await self._dead_letter(event)
            return False

    async def subscribe(self, event_type: EventType, handler: Callable[[Event], Any]) -> str:
        """Subscribe to event type"""
        async with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []

            self._subscribers[event_type].append(handler)

            subscription_id = f"{event_type.value}_{id(handler)}"
            logger.info(f"✅ New subscription: {subscription_id}")

            return subscription_id

    async def unsubscribe(self, subscription_id: str):
        """Unsubscribe from event"""
        async with self._lock:
            for event_type, handlers in self._subscribers.items():
                self._subscribers[event_type] = [
                    h for h in handlers if f"{event_type.value}_{id(h)}" != subscription_id
                ]

    async def _get_subscribers(self, event_type: EventType) -> List[Callable]:
        """Get all subscribers for event type"""
        async with self._lock:
            return self._subscribers.get(event_type, []).copy()

    async def _notify_subscriber(self, subscriber: Callable[[Event], Any], event: Event):
        """Notify single subscriber"""
        try:
            if asyncio.iscoroutinefunction(subscriber):
                await subscriber(event)
            else:
                subscriber(event)
        except Exception as e:
            logger.error(f"Subscriber failed: {e}")
            raise

    async def _store_event(self, event: Event):
        """Store event in history"""
        async with self._lock:
            self._event_history.append(event)

            # Trim history if needed
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history :]

    async def _dead_letter(self, event: Event):
        """Add event to dead letter queue"""
        self._dead_letter_queue.append(event)
        logger.error(f"Event added to dead letter queue: {event.type.value}")

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        """Get event history with optional filters"""
        events = self._event_history

        if event_type:
            events = [e for e in events if e.type == event_type]

        if source:
            events = [e for e in events if e.source == source]

        return events[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """Get event bus statistics"""
        return {
            "total_subscribers": sum(len(handlers) for handlers in self._subscribers.values()),
            "event_types": len(self._subscribers),
            "events_published": len(self._event_history),
            "dead_letter_count": len(self._dead_letter_queue),
            "subscribers_by_type": {
                event_type.value: len(handlers)
                for event_type, handlers in self._subscribers.items()
            },
        }
