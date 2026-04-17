"""
Minder Core Module
Microkernel architecture for modular RAG platform
"""

__version__ = "1.0.0"
__author__ = "FundMind AI"

from .correlation_engine import CorrelationEngine
from .event_bus import Event, EventBus, EventType
from .kernel import MinderKernel
from .knowledge_graph import Entity, EntityType, KnowledgeGraph, Relation, RelationType
from .module_interface import BaseModule, ModuleMetadata, ModuleStatus
from .plugin_loader import PluginLoader
from .registry import PluginRegistry

__all__ = [
    "BaseModule",
    "ModuleMetadata",
    "ModuleStatus",
    "PluginRegistry",
    "MinderKernel",
    "EventBus",
    "EventType",
    "Event",
    "KnowledgeGraph",
    "Entity",
    "Relation",
    "EntityType",
    "RelationType",
    "PluginLoader",
    "CorrelationEngine",
]
