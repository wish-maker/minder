"""
Minder Module Interface Standard
All modules must implement this interface for compatibility
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime
from enum import Enum


class ModuleStatus(Enum):
    """Module lifecycle status"""

    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    INITIALIZING = "initializing"
    READY = "ready"
    COLLECTING = "collecting"
    ANALYZING = "analyzing"
    TRAINING = "training"
    INDEXING = "indexing"
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
    Abstract base class for all Minder modules

    Every module must implement these methods:
    - register(): Register module with kernel
    - collect_data(): Fetch/ingest data from sources
    - analyze(): Process and analyze collected data
    - train_ai(): Train ML models on module data
    - index_knowledge(): Create vector embeddings for RAG
    - get_correlations(): Provide cross-database correlation hints
    - get_anomalies(): Return detected anomalies
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.status = ModuleStatus.UNREGISTERED
        self.metadata: Optional[ModuleMetadata] = None
        self.state: Dict[str, Any] = {}

    @abstractmethod
    async def register(self) -> ModuleMetadata:
        """Register module with Minder kernel"""
        pass

    @abstractmethod
    async def collect_data(self, since: Optional[datetime] = None) -> Dict[str, int]:
        """
        Collect data from sources

        Returns: {
            'records_collected': int,
            'records_updated': int,
            'errors': int
        }
        """
        pass

    @abstractmethod
    async def analyze(self) -> Dict[str, Any]:
        """
        Analyze collected data

        Returns: {
            'metrics': Dict[str, float],
            'patterns': List[Dict],
            'insights': List[str]
        }
        """
        pass

    @abstractmethod
    async def train_ai(self, model_type: str = "default") -> Dict[str, Any]:
        """
        Train AI model on module data

        Returns: {
            'model_id': str,
            'accuracy': float,
            'training_samples': int,
            'metrics': Dict[str, float]
        }
        """
        pass

    @abstractmethod
    async def index_knowledge(self, force: bool = False) -> Dict[str, int]:
        """
        Create vector embeddings for RAG

        Returns: {
            'vectors_created': int,
            'vectors_updated': int,
            'collections': int
        }
        """
        pass

    @abstractmethod
    async def get_correlations(self, other_module: str, correlation_type: str = "auto") -> List[Dict[str, Any]]:
        """
        Provide correlation hints with another module

        Returns: [
            {
                'field': str,
                'other_field': str,
                'correlation_type': str,  # temporal, causal, semantic
                'strength': float,  # 0-1
                'description': str
            }
        ]
        """
        pass

    @abstractmethod
    async def get_anomalies(self, severity: str = "medium", limit: int = 100) -> List[Dict[str, Any]]:
        """
        Return detected anomalies

        Returns: [
            {
                'type': str,
                'severity': str,
                'description': str,
                'data': Dict,
                'detected_at': datetime
            }
        ]
        """
        pass

    async def health_check(self) -> Dict[str, Any]:
        """Return module health status"""
        return {
            "name": self.metadata.name if self.metadata else "unknown",
            "status": self.status.value,
            "uptime_seconds": ((datetime.now() - self.metadata.registered_at).total_seconds() if self.metadata else 0),
            "state": self.state,
        }

    async def shutdown(self):
        """Cleanup before module shutdown"""
        self.status = ModuleStatus.STOPPED
