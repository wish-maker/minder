"""
Minder Core Module
Microkernel architecture for modular RAG platform
"""

__version__ = "1.0.0"
__author__ = "FundMind AI"

from .module_interface import BaseModule, ModuleMetadata, ModuleStatus
from .registry import PluginRegistry
from .kernel import MinderKernel
from .event_bus import EventBus, EventType, Event
from .knowledge_graph import KnowledgeGraph, Entity, Relation, EntityType, RelationType
from .plugin_loader import PluginLoader
from .correlation_engine import CorrelationEngine

__all__ = [
    'BaseModule',
    'ModuleMetadata',
    'ModuleStatus',
    'PluginRegistry',
    'MinderKernel',
    'EventBus',
    'EventType',
    'Event',
    'KnowledgeGraph',
    'Entity',
    'Relation',
    'EntityType',
    'RelationType',
    'PluginLoader',
    'CorrelationEngine'
]
