"""
Plugin Domain Module

This module contains the domain layer for the Plugin bounded context,
including aggregates, domain events, and domain logic.
"""

from src.plugins.domain.plugin_aggregate import PluginAggregate

__all__ = ["PluginAggregate"]
