from abc import ABC, abstractmethod
from typing import List
from uuid import UUID

from src.shared.events.event import Event


class Aggregate(ABC):
    """
    Base class for all aggregates in Event Sourcing architecture.

    Aggregates are consistency boundaries that process commands
    and generate events. State is rebuilt by replaying events.

    Attributes:
        id: Unique identifier for the aggregate instance
        version: Optimistic locking version number
        _uncommitted_events: Events not yet persisted
    """

    def __init__(self, id: UUID):
        """
        Initialize aggregate.

        Args:
            id: Unique identifier for this aggregate instance
        """
        self.id = id
        self.version = 0
        self._uncommitted_events: List[Event] = []

    def _apply_event(self, event: Event, version: int) -> None:
        """
        Apply event to aggregate state.

        This method is called internally when applying events.
        Subclasses should override _apply() to handle specific event types.

        Args:
            event: Event to apply
            version: New version number after applying event
        """
        self._apply(event)
        self.version = version
        self._uncommitted_events.append(event)

    @abstractmethod
    def _apply(self, event: Event) -> None:
        """
        Apply event to aggregate state (abstract method).

        Subclasses must implement this to handle specific event types
        and update aggregate state accordingly.

        Args:
            event: Event to apply
        """
        pass

    def load_from_history(self, events: List[Event]) -> None:
        """
        Rebuild aggregate state from event history.

        Used when loading aggregate from event store. Replays
        all events in order to rebuild current state.

        Args:
            events: List of historical events in version order
        """
        for event in events:
            self.version += 1
            self._apply(event)

    def get_uncommitted_events(self) -> List[Event]:
        """
        Get events not yet persisted to event store.

        Returns:
            List of uncommitted events
        """
        return self._uncommitted_events.copy()

    def mark_events_as_committed(self) -> None:
        """
        Clear uncommitted events after successful persistence.

        Called after events are successfully saved to event store.
        """
        self._uncommitted_events.clear()
