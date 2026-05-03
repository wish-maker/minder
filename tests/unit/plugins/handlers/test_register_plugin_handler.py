from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest

from src.plugins.handlers.register_plugin_handler import RegisterPluginHandler
from src.shared.commands.command import Command, CommandMetadata


class TestRegisterPluginHandler:
    """Test RegisterPlugin command handler"""

    def test_handle_register_command(self):
        """Should handle RegisterPlugin command successfully"""
        # Setup
        event_store = Mock()
        outbox = Mock()
        handler = RegisterPluginHandler(event_store, outbox)

        # Mock that no events exist yet (new plugin)
        event_store.get_events.return_value = []

        command = Command(
            metadata=CommandMetadata(
                command_id=uuid4(),
                command_type="RegisterPlugin",
                timestamp=datetime.now(timezone.utc),
                user_id="user123",
            ),
            data={"plugin_id": "crypto", "version": "1.0.0", "name": "Crypto Plugin", "description": "Crypto plugin"},
        )

        # Execute
        result = handler.handle(command)

        # Verify
        assert result is not None
        assert result["plugin_id"] == "crypto"
        event_store.append.assert_called()
        outbox.save.assert_called()

    def test_handle_duplicate_plugin(self):
        """Should reject duplicate plugin registration"""
        # Setup
        event_store = Mock()
        outbox = Mock()
        handler = RegisterPluginHandler(event_store, outbox)

        # Mock existing plugin - return events to indicate plugin exists
        from src.shared.events.event import Event, EventMetadata

        event_store.get_events.return_value = [
            Event(
                metadata=EventMetadata(
                    event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
                ),
                data={"plugin_id": "crypto", "version": "1.0.0", "name": "Crypto"},
            )
        ]

        command = Command(
            metadata=CommandMetadata(
                command_id=uuid4(), command_type="RegisterPlugin", timestamp=datetime.now(timezone.utc)
            ),
            data={"plugin_id": "crypto", "version": "1.0.0", "name": "Crypto"},
        )

        # Execute & Verify
        with pytest.raises(ValueError, match="Plugin crypto already exists"):
            handler.handle(command)
