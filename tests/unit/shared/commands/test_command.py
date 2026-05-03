from datetime import datetime, timezone
from uuid import uuid4

from src.shared.commands.command import Command, CommandMetadata


class TestCommandMetadata:
    """Test CommandMetadata creation and validation"""

    def test_create_minimal_metadata(self):
        """Should create metadata with only required fields"""
        metadata = CommandMetadata(
            command_id=uuid4(), command_type="RegisterPlugin", timestamp=datetime.now(timezone.utc)
        )
        assert metadata.command_id is not None
        assert metadata.command_type == "RegisterPlugin"
        assert metadata.timestamp is not None
        assert metadata.user_id is None
        assert metadata.correlation_id is None

    def test_create_full_metadata(self):
        """Should create metadata with all fields"""
        command_id = uuid4()
        correlation_id = uuid4()
        user_id = "user123"
        timestamp = datetime.now(timezone.utc)

        metadata = CommandMetadata(
            command_id=command_id,
            command_type="RegisterPlugin",
            timestamp=timestamp,
            user_id=user_id,
            correlation_id=correlation_id,
        )
        assert metadata.command_id == command_id
        assert metadata.command_type == "RegisterPlugin"
        assert metadata.timestamp == timestamp
        assert metadata.user_id == user_id
        assert metadata.correlation_id == correlation_id

    def test_metadata_to_dict(self):
        """Should serialize metadata to dictionary"""
        command_id = uuid4()
        timestamp = datetime.now(timezone.utc)

        metadata = CommandMetadata(
            command_id=command_id, command_type="RegisterPlugin", timestamp=timestamp, user_id="user123"
        )

        data = metadata.to_dict()
        assert data["command_id"] == str(command_id)
        assert data["command_type"] == "RegisterPlugin"
        assert "timestamp" in data
        assert data["user_id"] == "user123"

    def test_metadata_from_dict(self):
        """Should deserialize metadata from dictionary"""
        command_id = uuid4()
        timestamp = datetime.now(timezone.utc)

        data = {
            "command_id": str(command_id),
            "command_type": "RegisterPlugin",
            "timestamp": timestamp.isoformat(),
            "user_id": "user123",
            "correlation_id": None,
        }

        metadata = CommandMetadata.from_dict(data)
        assert metadata.command_id == command_id
        assert metadata.command_type == "RegisterPlugin"
        assert metadata.user_id == "user123"


class TestCommand:
    """Test base Command class"""

    def test_create_command(self):
        """Should create command with metadata and data"""
        metadata = CommandMetadata(
            command_id=uuid4(), command_type="RegisterPlugin", timestamp=datetime.now(timezone.utc)
        )

        command = Command(metadata=metadata, data={"plugin_id": "crypto", "version": "1.0.0"})

        assert command.metadata == metadata
        assert command.data == {"plugin_id": "crypto", "version": "1.0.0"}

    def test_command_to_dict(self):
        """Should serialize command to dictionary"""
        metadata = CommandMetadata(
            command_id=uuid4(), command_type="RegisterPlugin", timestamp=datetime.now(timezone.utc)
        )

        command = Command(metadata=metadata, data={"plugin_id": "crypto"})

        data = command.to_dict()
        assert "metadata" in data
        assert "data" in data
        assert data["data"]["plugin_id"] == "crypto"

    def test_command_from_dict(self):
        """Should deserialize command from dictionary"""
        command_id = uuid4()
        timestamp = datetime.now(timezone.utc)

        data = {
            "metadata": {
                "command_id": str(command_id),
                "command_type": "RegisterPlugin",
                "timestamp": timestamp.isoformat(),
                "user_id": "user123",
                "correlation_id": None,
            },
            "data": {"plugin_id": "crypto"},
        }

        command = Command.from_dict(data)
        assert command.metadata.command_id == command_id
        assert command.data["plugin_id"] == "crypto"

    def test_command_type_property(self):
        """Should expose command type from metadata"""
        metadata = CommandMetadata(
            command_id=uuid4(), command_type="ChangePluginState", timestamp=datetime.now(timezone.utc)
        )

        command = Command(metadata=metadata, data={})
        assert command.command_type == "ChangePluginState"
