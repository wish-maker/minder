# src/plugin_state_manager/domain/aggregates/__init__.py

from src.plugin_state_manager.domain.aggregates.state_aggregate import PluginState, PluginStateAggregate

__all__ = [
    "PluginStateAggregate",
    "PluginState",
]
