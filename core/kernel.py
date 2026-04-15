"""
Minder Microkernel
Core engine that manages modules and orchestrates operations
"""
from typing import Dict, List, Any, Optional
import asyncio
import logging
from datetime import datetime

from .registry import PluginRegistry
from .correlation_engine import CorrelationEngine
from .event_bus import EventBus, EventType, Event
from .knowledge_graph import KnowledgeGraph
from .plugin_loader import PluginLoader
from .module_interface import BaseModule, ModuleStatus
from plugins.store import PluginStore

logger = logging.getLogger(__name__)

class MinderKernel:
    """
    Minder Microkernel - Core orchestration engine

    Responsibilities:
    - Plugin lifecycle management
    - Plugin store integration (GitHub repos)
    - Cross-plugin communication
    - Correlation discovery
    - Task scheduling and execution
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.registry = PluginRegistry(config)
        self.correlation_engine = CorrelationEngine(self.registry, config)
        self.event_bus = EventBus(config)
        self.knowledge_graph = KnowledgeGraph(config)
        self.plugin_loader = PluginLoader(config)
        self.plugin_store = None  # Will be initialized later
        self.running = False
        self.startup_time: Optional[datetime] = None

        asyncio.create_task(self._subscribe_to_events())

    async def _subscribe_to_events(self):
        """Subscribe to event bus"""
        await self.event_bus.subscribe(EventType.ANOMALY_DETECTED, self._handle_anomaly)
        await self.event_bus.subscribe(EventType.CORRELATION_FOUND, self._handle_correlation)
        await self.event_bus.subscribe(EventType.MODULE_ERROR, self._handle_module_error)

    async def _handle_anomaly(self, event: Event):
        """Handle anomaly detection event"""
        logger.warning(f"⚠️  Anomaly detected: {event.data}")

    async def _handle_correlation(self, event: Event):
        """Handle correlation discovery event"""
        logger.info(f"🔗 Correlation found: {event.data}")

    async def _handle_module_error(self, event: Event):
        """Handle module error event"""
        logger.error(f"❌ Module error: {event.source} - {event.data}")

    async def start(self):
        """Start the Minder kernel"""
        logger.info("🚀 Starting Enhanced Minder Kernel...")
        self.running = True
        self.startup_time = datetime.now()

        await self.event_bus.publish(Event(
            type=EventType.MODULE_READY,
            source="kernel",
            data={'action': 'startup'}
        ))

        # Initialize Plugin Store (if enabled)
        if self.config.get('plugin_store', {}).get('enabled', False):
            logger.info("🏪 Initializing Plugin Store...")
            self.plugin_store = PluginStore(self.config.get('plugin_store', {}))
            await self.plugin_store.initialize()
        else:
            self.plugin_store = None

        # Load local plugins (not from GitHub)
        plugins = await self.plugin_loader.load_all_plugins()

        for name, plugin in plugins.items():
            await self.registry.register_plugin(plugin)

        init_results = await self.registry.initialize_all()

        success_count = sum(1 for v in init_results.values() if v)
        total_count = len(init_results)

        logger.info(f"✅ Enhanced kernel started: {success_count}/{total_count} plugins ready")

    async def stop(self):
        """Stop the Minder kernel"""
        logger.info("🛑 Stopping Enhanced Minder Kernel...")

        await self.event_bus.publish(Event(
            type=EventType.SYSTEM_SHUTDOWN,
            source="kernel",
            data={'uptime': (datetime.now() - self.startup_time).total_seconds() if self.startup_time else 0}
        ))

        self.running = False
        await self.registry.shutdown_all()

        logger.info("✅ Enhanced kernel stopped")

    async def run_plugin_pipeline(
        self,
        plugin_name: str,
        pipeline: List[str] = None
    ) -> Dict[str, Any]:

        if pipeline is None:
            pipeline = ['collect', 'analyze', 'train', 'index']

        plugin = await self.registry.get_plugin(plugin_name)
        if not plugin:
            raise ValueError(f"Plugin not found: {plugin_name}")

        results = {}

        for operation in pipeline:
            try:
                logger.info(f"🔄 {plugin_name}: Running {operation}...")

                await self.event_bus.publish(Event(
                    type=EventType.DATA_COLLECTED if operation == 'collect' else EventType.ANALYSIS_COMPLETE,
                    source=plugin_name,
                    data={'operation': operation, 'status': 'started'}
                ))

                if operation == 'collect':
                    result = await plugin.collect_data()
                elif operation == 'analyze':
                    result = await plugin.analyze()
                elif operation == 'train':
                    result = await plugin.train_ai()
                elif operation == 'index':
                    result = await plugin.index_knowledge()
                else:
                    raise ValueError(f"Unknown operation: {operation}")

                results[operation] = result

                await self.event_bus.publish(Event(
                    type=EventType.ANALYSIS_COMPLETE,
                    source=plugin_name,
                    data={'operation': operation, 'status': 'completed', 'result': result}
                ))

                logger.info(f"✅ {plugin_name}: {operation} completed")

            except Exception as e:
                logger.error(f"❌ {plugin_name}: {operation} failed - {e}")

                await self.event_bus.publish(Event(
                    type=EventType.MODULE_ERROR,
                    source=module_name,
                    data={'operation': operation, 'error': str(e)}
                ))

                results[operation] = {'error': str(e)}
                break

        return results

    async def discover_all_correlations(self) -> Dict[str, List[Dict]]:
        """Discover correlations between all plugin pairs"""
        plugins = await self.registry.list_plugins(status='ready')
        plugin_names = [p['name'] for p in plugins]

        all_correlations = {}

        for i, plugin_a in enumerate(plugin_names):
            for plugin_b in plugin_names[i+1:]:
                pair_key = f"{plugin_a}:{plugin_b}"
                correlations = await self.correlation_engine.discover_correlations(
                    plugin_a, plugin_b
                )
                all_correlations[pair_key] = correlations

        return all_correlations

    async def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        plugins = await self.registry.list_plugins()
        correlations = await self.correlation_engine.get_all_correlations()

        uptime = (datetime.now() - self.startup_time).total_seconds() if self.startup_time else 0

        return {
            'status': 'running' if self.running else 'stopped',
            'uptime_seconds': uptime,
            'plugins': {
                'total': len(plugins),
                'ready': sum(1 for p in plugins if p['status'] == 'ready'),
                'error': sum(1 for p in plugins if p['status'] == 'error'),
                'details': plugins
            },
            'correlations': {
                'total_pairs': len(correlations),
                'total_correlations': sum(len(c) for c in correlations.values())
            },
            'knowledge_graph': self.knowledge_graph.get_statistics(),
            'event_bus': self.event_bus.get_statistics()
        }

    async def query_plugins(
        self,
        query: str,
        plugins: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:

        if plugins is None:
            plugin_list = await self.registry.list_plugins(status='ready')
            plugins = [p['name'] for p in plugin_list]

        results = []

        for plugin_name in plugins:
            plugin = await self.registry.get_plugin(plugin_name)
            if plugin and hasattr(plugin, 'query'):
                try:
                    result = await plugin.query(query)
                    results.append({
                        'plugin': plugin_name,
                        'result': result
                    })
                except Exception as e:
                    logger.error(f"Query failed for {plugin_name}: {e}")

        return results
