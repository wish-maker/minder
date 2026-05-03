from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from src.shared.events.event import Event


class Projection(ABC):
    """
    Base class for all projections in CQRS read side.

    Projections build denormalized read models from events.
    They are optimized for querying and contain no business logic.

    Attributes:
        name: Projection name for identification
        version: Event version up to which projection is updated
        id: Optional unique identifier for projection instance
    """

    def __init__(self, id: Optional[UUID] = None):
        """
        Initialize projection.

        Args:
            id: Optional unique identifier for this projection
        """
        self.id = id
        self.version = 0
        self.name = self.__class__.__name__

    def handle(self, event: Event) -> None:
        """
        Handle event and update projection state.

        Routes event to appropriate _apply method based on
        event type. Ignores unknown event types.

        Args:
            event: Event to handle
        """
        try:
            self._apply(event)
            self.version += 1
        except Exception:  # nosec B110
            # Ignore events that can't be applied
            # (e.g., unknown event types for this projection)
            pass

    @abstractmethod
    def _apply(self, event: Event) -> None:
        """
        Apply event to projection state (abstract method).

        Subclasses must implement this to handle specific
        event types and update their read model state.

        Args:
            event: Event to apply
        """
        pass
