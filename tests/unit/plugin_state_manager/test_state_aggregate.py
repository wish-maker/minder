# tests/unit/plugin_state_manager/test_state_aggregate.py

from uuid import uuid4

import pytest

from src.plugin_state_manager.domain.aggregates.state_aggregate import PluginState, PluginStateAggregate


def test_state_transition():
    """Test plugin state transition from installed to running"""
    aggregate = PluginStateAggregate(uuid4())
    assert aggregate.state == PluginState.INSTALLED

    aggregate.update_state("running", reason="Starting plugin")
    assert aggregate.state == PluginState.RUNNING
    assert aggregate.last_activity is not None
    assert len(aggregate.get_uncommitted_events()) == 1


def test_state_transition_to_stopped():
    """Test plugin state transition from running to stopped"""
    aggregate = PluginStateAggregate(uuid4())
    aggregate.update_state("running")
    aggregate.mark_events_as_committed()

    aggregate.update_state("stopped", reason="Stopping plugin")
    assert aggregate.state == PluginState.STOPPED
    assert len(aggregate.get_uncommitted_events()) == 1


def test_state_transition_to_error():
    """Test plugin state transition to error state"""
    aggregate = PluginStateAggregate(uuid4())
    aggregate.update_state("running")
    aggregate.mark_events_as_committed()

    aggregate.update_state("error", reason="Plugin crashed")
    assert aggregate.state == PluginState.ERROR
    assert len(aggregate.get_uncommitted_events()) == 1


def test_invalid_state_transition():
    """Test that invalid state transitions raise ValueError"""
    aggregate = PluginStateAggregate(uuid4())

    with pytest.raises(ValueError, match="Invalid state"):
        aggregate.update_state("invalid_state")


def test_tool_execution_when_running():
    """Test tool execution succeeds when plugin is running"""
    aggregate = PluginStateAggregate(uuid4())
    aggregate.update_state("running")
    aggregate.mark_events_as_committed()

    parameters = {"param1": "value1", "param2": "value2"}
    aggregate.execute_tool("test_tool", parameters)

    assert aggregate.tool_execution_count == 1
    assert aggregate.last_activity is not None
    assert len(aggregate.get_uncommitted_events()) == 1


def test_tool_execution_fails_when_not_running():
    """Test that tool execution fails when plugin is not running"""
    aggregate = PluginStateAggregate(uuid4())
    assert aggregate.state != PluginState.RUNNING

    with pytest.raises(ValueError, match="Cannot execute tool"):
        aggregate.execute_tool("test_tool", {})


def test_multiple_tool_executions():
    """Test multiple tool executions increment counter"""
    aggregate = PluginStateAggregate(uuid4())
    aggregate.update_state("running")
    aggregate.mark_events_as_committed()

    aggregate.execute_tool("tool1", {})
    aggregate.mark_events_as_committed()

    aggregate.execute_tool("tool2", {"param": "value"})
    aggregate.mark_events_as_committed()

    assert aggregate.tool_execution_count == 2


def test_event_rebuild_from_history():
    """Test rebuilding aggregate state from event history"""
    aggregate_id = uuid4()

    # Create aggregate and apply some events
    aggregate = PluginStateAggregate(aggregate_id)
    aggregate.update_state("running", reason="Starting")
    events1 = aggregate.get_uncommitted_events()
    aggregate.mark_events_as_committed()

    aggregate.update_state("stopped", reason="Stopping")
    events2 = aggregate.get_uncommitted_events()
    aggregate.mark_events_as_committed()

    # Create new aggregate and rebuild from history
    new_aggregate = PluginStateAggregate(aggregate_id)
    all_events = events1 + events2
    new_aggregate.load_from_history(all_events)

    assert new_aggregate.state == PluginState.STOPPED
    assert new_aggregate.version == 2


def test_state_transition_with_reason():
    """Test that state transition reason is captured"""
    aggregate = PluginStateAggregate(uuid4())
    reason = "User requested stop"

    aggregate.update_state("stopped", reason=reason)

    events = aggregate.get_uncommitted_events()
    assert len(events) == 1
    assert events[0].data["reason"] == reason


def test_plugin_id_set_on_state_update():
    """Test that plugin_id is set when state is updated"""
    plugin_id = uuid4()
    aggregate = PluginStateAggregate(plugin_id)

    aggregate.update_state("running")

    assert aggregate.plugin_id == plugin_id
