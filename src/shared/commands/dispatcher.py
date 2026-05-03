from typing import Any, Callable, Dict

from src.shared.commands.command import Command


class CommandDispatcher:
    """
    Dispatcher for routing commands to appropriate handlers.

    Provides single entry point for all write operations in the CQRS
    architecture. Routes commands based on command_type to registered
    handlers.

    Attributes:
        _handlers: Dictionary mapping command_type to handler instance
    """

    def __init__(self):
        """Initialize command dispatcher"""
        self._handlers: Dict[str, Callable] = {}

    def register_handler(self, command_type: str, handler: Callable) -> None:
        """
        Register handler for command type.

        Args:
            command_type: Type of command (e.g., "RegisterPlugin")
            handler: Handler instance with handle() method
        """
        self._handlers[command_type] = handler

    def dispatch(self, command: Command) -> Dict[str, Any]:
        """
        Dispatch command to appropriate handler.

        Args:
            command: Command to dispatch

        Returns:
            Result from handler

        Raises:
            ValueError: If no handler registered for command type
        """
        handler = self._handlers.get(command.command_type)

        if not handler:
            raise ValueError(f"No handler registered for command type: {command.command_type}")

        return handler.handle(command)
