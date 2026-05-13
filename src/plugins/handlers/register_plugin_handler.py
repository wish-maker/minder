from typing import Any, Dict

from plugins.domain.plugin_aggregate import PluginAggregate
from src.shared.commands.command import Command


class RegisterPluginHandler:
    """
    Command handler for RegisterPlugin command.

    Coordinates plugin registration by:
    1. Loading aggregate from Event Store
    2. Executing register command on aggregate
    3. Saving generated events to Event Store
    4. Publishing events to Outbox

    Attributes:
        event_store: Event Store repository
        outbox: Outbox repository for event publishing
    """

    def __init__(self, event_store, outbox):
        """
        Initialize handler.

        Args:
            event_store: Event Store repository
            outbox: Outbox repository
        """
        self.event_store = event_store
        self.outbox = outbox

    def handle(self, command: Command) -> Dict[str, Any]:
        """
        Handle RegisterPlugin command.

        Args:
            command: RegisterPlugin command

        Returns:
            Result dictionary with plugin_id

        Raises:
            ValueError: If plugin already exists
        """
        # Generate a UUID for the aggregate based on plugin_id
        # In a real system, you might use a deterministic UUID or a separate mapping
        from uuid import NAMESPACE_DNS, uuid5

        aggregate_id = uuid5(NAMESPACE_DNS, f"plugin.{command.data['plugin_id']}")

        # Check if plugin already exists by loading events
        events = self.event_store.get_events(aggregate_type="Plugin", aggregate_id=aggregate_id)

        if events:
            # Plugin already exists
            raise ValueError(f"Plugin {command.data['plugin_id']} already exists")

        # Create new aggregate
        aggregate = PluginAggregate(aggregate_id)

        # Execute command
        aggregate.register(command.data)

        # Get events
        events = aggregate.get_uncommitted_events()

        # Save to Event Store
        for event in events:
            self.event_store.append(
                event=event, aggregate_type="Plugin", aggregate_id=aggregate_id, version=aggregate.version
            )

        # Publish to Outbox
        for event in events:
            from src.shared.events.outbox import OutboxMessage

            message = OutboxMessage.from_event(event=event, aggregate_type="Plugin", aggregate_id=aggregate_id)
            self.outbox.save(message)

        # Mark as committed
        aggregate.mark_events_as_committed()

        return {"plugin_id": command.data["plugin_id"], "version": command.data["version"]}
