# Minder Plugin Interface v2.0
# Simplified, Flexible, Production-Ready

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class ModuleStatus(Enum):
    """Module lifecycle status"""

    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    INITIALIZING = "initializing"
    READY = "ready"
    COLLECTING = "collecting"
    ANALYZING = "analyzing"
    ERROR = "error"
    STOPPED = "stopped"


class ModuleMetadata:
    """Module metadata and capabilities"""

    def __init__(
        self,
        name: str,
        version: str,
        description: str,
        author: str,
        dependencies: List[str] = None,
        capabilities: List[str] = None,
        data_sources: List[str] = None,
        databases: List[str] = None,
    ):
        self.name = name
        self.version = version
        self.description = description
        self.author = author
        self.dependencies = dependencies or []
        self.capabilities = capabilities or []
        self.data_sources = data_sources or []
        self.databases = databases or []
        self.registered_at = datetime.now()


class BaseModule(ABC):
    """
    Abstract base class for all Minder plugins

    v2.0 Changes:
    - Only register() and health_check() are REQUIRED
    - All other methods are OPTIONAL with base implementations
    - Simplified for easier plugin development
    - Helper methods provided for common tasks
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.status = ModuleStatus.UNREGISTERED
        self.metadata: Optional[ModuleMetadata] = None
        self.state: Dict[str, Any] = {}

    # ========================================================================
    # REQUIRED METHODS (All plugins must implement)
    # ========================================================================

    @abstractmethod
    async def register(self) -> ModuleMetadata:
        """
        Register plugin with Minder kernel

        This is the ONLY required method for all plugins.
        Returns plugin metadata including name, version, capabilities.

        Returns:
            ModuleMetadata object with plugin information
        """
        pass

    # ========================================================================
    # OPTIONAL METHODS (Provide base implementations)
    # ========================================================================

    async def collect_data(self, since: Optional[datetime] = None) -> Dict[str, int]:
        """
        Collect data from sources (OPTIONAL)

        Base implementation returns success with no data.
        Override this method if your plugin collects data.

        Returns:
            Dict with records_collected, records_updated, errors
        """
        return {
            "records_collected": 0,
            "records_updated": 0,
            "errors": 0,
            "message": "Data collection not implemented",
        }

    async def analyze(self) -> Dict[str, Any]:
        """
        Analyze collected data (OPTIONAL)

        Base implementation returns empty analysis.
        Override this method if your plugin provides analysis.

        Returns:
            Dict with metrics, patterns, insights
        """
        return {"metrics": {}, "patterns": [], "insights": ["Analysis not implemented"]}

    async def train_ai(self, model_type: str = "default") -> Dict[str, Any]:
        """
        Train AI model on plugin data (OPTIONAL)

        Base implementation returns empty model info.
        Override this method if your plugin uses AI/ML.

        Returns:
            Dict with model_id, accuracy, training_samples
        """
        return {
            "model_id": f"{self.metadata.name}_model",
            "accuracy": 0.0,
            "training_samples": 0,
            "message": "AI training not implemented",
        }

    async def index_knowledge(self, force: bool = False) -> Dict[str, int]:
        """
        Create vector embeddings for RAG (OPTIONAL)

        Base implementation returns empty index info.
        Override this method if your plugin provides knowledge indexing.

        Returns:
            Dict with vectors_created, vectors_updated, collections
        """
        return {
            "vectors_created": 0,
            "vectors_updated": 0,
            "collections": 0,
            "message": "Knowledge indexing not implemented",
        }

    async def get_correlations(self, other_module: str, correlation_type: str = "auto") -> List[Dict[str, Any]]:
        """
        Provide correlation hints with another module (OPTIONAL)

        Base implementation returns no correlations.
        Override this method if your plugin provides correlation analysis.

        Returns:
            List of correlation hints
        """
        return []

    async def get_anomalies(self, severity: str = "medium", limit: int = 100) -> List[Dict[str, Any]]:
        """
        Return detected anomalies (OPTIONAL)

        Base implementation returns no anomalies.
        Override this method if your plugin detects anomalies.

        Returns:
            List of detected anomalies
        """
        return []

    async def query(self, query: str) -> Dict[str, Any]:
        """
        Query plugin data (OPTIONAL)

        Base implementation returns empty results.
        Override this method if your plugin supports querying.

        Args:
            query: Query string

        Returns:
            Dict with query results
        """
        return {"query": query, "results": [], "message": "Query not implemented"}

    # ========================================================================
    # LIFECYCLE METHODS (Called automatically)
    # ========================================================================

    async def initialize(self):
        """
        Initialize plugin (called after registration)

        Override this method to perform one-time setup.
        """
        self.status = ModuleStatus.READY

        # Initialize agent capability if available
        try:
            from src.core.agent_framework import agent_manager

            self.agent_capability = agent_manager.register_plugin(self.metadata.name)
            self.log("Agent capability enabled")
        except ImportError:
            self.agent_capability = None
            self.log("Agent framework not available")

    async def health_check(self) -> Dict[str, Any]:
        """
        Return plugin health status (called automatically)

        Returns:
            Dict with health information
        """
        return {
            "name": self.metadata.name if self.metadata else "unknown",
            "status": self.status.value,
            "healthy": self.status == ModuleStatus.READY,
            "uptime_seconds": ((datetime.now() - self.metadata.registered_at).total_seconds() if self.metadata else 0),
            "state": self.state,
            "agent_enabled": hasattr(self, "agent_capability") and self.agent_capability is not None,
        }

    async def shutdown(self):
        """
        Cleanup before plugin shutdown (called automatically)

        Override this method to perform cleanup.
        """
        self.status = ModuleStatus.STOPPED

    # ========================================================================
    # HELPER METHODS (Utility functions for plugins)
    # ========================================================================

    def log(self, message: str, level: str = "info"):
        """
        Log message with plugin context

        Args:
            message: Message to log
            level: Log level (debug, info, warning, error)
        """
        import logging

        logger = logging.getLogger(f"minder.plugin.{self.metadata.name if self.metadata else 'unknown'}")
        log_func = getattr(logger, level, logger.info)
        log_func(message)

    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value

        Args:
            key: Configuration key (supports nested keys with ".")
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self.config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

        return value if value is not None else default

    async def safe_execute(self, func: Callable, timeout: int = 300, **kwargs) -> Any:
        """
        Safely execute function with timeout and error handling

        Args:
            func: Function to execute
            timeout: Timeout in seconds
            **kwargs: Keyword arguments for function

        Returns:
            Function result or None if failed
        """
        import asyncio

        try:
            result = await asyncio.wait_for(func(**kwargs), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self.log(f"Function execution timed out after {timeout}s", "warning")
            return None
        except Exception as e:
            self.log(f"Function execution failed: {e}", "error")
            return None
