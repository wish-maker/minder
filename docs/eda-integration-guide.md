# Event-Driven Architecture Integration Guide

## Overview

This guide explains how to use the Event-Driven Architecture (EDA) components implemented in the Minder platform.

## Architecture Components

### Write Side (Commands)
1. **Command Dispatcher** (`src/shared/commands/dispatcher.py`)
   - Single entry point for all commands
   - Routes to appropriate handlers

2. **Command Handlers** (`src/plugins/handlers/`)
   - Execute business logic on aggregates
   - Generate events

3. **Aggregates** (`src/plugins/domain/`)
   - Maintain consistency boundaries
   - Generate events for state changes

### Event Storage
4. **Event Store** (`src/shared/events/event_store.py`)
   - Append-only event log
   - Supports event replay

5. **Outbox** (`src/shared/events/outbox.py`)
   - Reliable event publishing
   - Prevents event loss

### Read Side (Projections)
6. **Projections** (`src/plugins/projections/`)
   - Build denormalized read models
   - Subscribe to events

## Usage Example

### Registering a Plugin

```python
from src.shared.commands.command import Command, CommandMetadata
from src.shared.commands.dispatcher import CommandDispatcher
from src.plugins.handlers.register_plugin_handler import RegisterPluginHandler
from src.shared.events.event_store import EventStore
from src.shared.events.outbox import OutboxRepository

# Setup
event_store = EventStore(db_session)
outbox = OutboxRepository(db_session)
dispatcher = CommandDispatcher()

# Register handler
handler = RegisterPluginHandler(event_store, outbox)
dispatcher.register_handler("RegisterPlugin", handler)

# Create command
command = Command(
    metadata=CommandMetadata(
        command_id=uuid4(),
        command_type="RegisterPlugin",
        timestamp=datetime.now(timezone.utc),
        user_id="user123"
    ),
    data={
        "plugin_id": "crypto",
        "version": "1.0.0",
        "name": "Crypto Plugin",
        "description": "Cryptocurrency plugin"
    }
)

# Execute
result = dispatcher.dispatch(command)
# Result: {"plugin_id": "crypto", "version": "1.0.0"}
```

### Building Projections

```python
from src.plugins.projections.plugin_projection import PluginProjection
from src.shared.events.event_store import EventStore

# Create projection
projection = PluginProjection(id=plugin_id)

# Load events and build projection
event_store = EventStore(db_session)
events = event_store.get_events("Plugin", plugin_id)

for event in events:
    projection.handle(event)

# Query projection
print(f"Plugin: {projection.name}, State: {projection.state}")
```

## Component Integration

### 1. Event Publishing Flow
```
Command → Handler → Aggregate → Events → Event Store → Outbox → Message Broker
```

### 2. Event Consumption Flow
```
Message Broker → Event Handler → Projection.apply() → Read Model Updated
```

## Testing

Run integration tests:
```bash
# Test Event Store
pytest tests/integration/test_event_store.py -v

# Test projections
pytest tests/unit/plugins/projections/ -v

# Test handlers
pytest tests/unit/plugins/handlers/ -v
```

## Migration Guide

Existing HTTP endpoints can gradually migrate:
1. Keep existing endpoints working
2. Add new command dispatcher endpoint
3. Background process polls outbox and publishes events
4. Read projections instead of direct database queries
