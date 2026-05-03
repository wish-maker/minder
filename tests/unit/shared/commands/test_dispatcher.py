from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest

from src.shared.commands.command import Command, CommandMetadata
from src.shared.commands.dispatcher import CommandDispatcher


class TestCommandDispatcher:
    """Test CommandDispatcher routing"""

    def test_dispatch_command(self):
        """Should dispatch command to correct handler"""
        dispatcher = CommandDispatcher()

        # Register handler
        handler = Mock()
        handler.handle.return_value = {"plugin_id": "crypto"}
        dispatcher.register_handler("RegisterPlugin", handler)

        # Create command
        command = Command(
            metadata=CommandMetadata(
                command_id=uuid4(), command_type="RegisterPlugin", timestamp=datetime.now(timezone.utc)
            ),
            data={"plugin_id": "crypto", "version": "1.0.0"},
        )

        # Dispatch
        result = dispatcher.dispatch(command)

        # Verify
        assert result["plugin_id"] == "crypto"
        handler.handle.assert_called_once_with(command)

    def test_dispatch_unknown_command(self):
        """Should raise error for unknown command type"""
        dispatcher = CommandDispatcher()

        command = Command(
            metadata=CommandMetadata(
                command_id=uuid4(), command_type="UnknownCommand", timestamp=datetime.now(timezone.utc)
            ),
            data={},
        )

        # Should raise ValueError
        with pytest.raises(ValueError, match="No handler registered"):
            dispatcher.dispatch(command)

    def test_dispatch_multiple_commands(self):
        """Should handle multiple command types"""
        dispatcher = CommandDispatcher()

        # Register handlers
        handler1 = Mock()
        handler1.handle.return_value = {"result": "handler1"}
        handler2 = Mock()
        handler2.handle.return_value = {"result": "handler2"}

        dispatcher.register_handler("Command1", handler1)
        dispatcher.register_handler("Command2", handler2)

        # Create commands
        command1 = Command(
            metadata=CommandMetadata(command_id=uuid4(), command_type="Command1", timestamp=datetime.now(timezone.utc)),
            data={},
        )

        command2 = Command(
            metadata=CommandMetadata(command_id=uuid4(), command_type="Command2", timestamp=datetime.now(timezone.utc)),
            data={},
        )

        # Dispatch
        result1 = dispatcher.dispatch(command1)
        result2 = dispatcher.dispatch(command2)

        # Verify
        assert result1["result"] == "handler1"
        assert result2["result"] == "handler2"
