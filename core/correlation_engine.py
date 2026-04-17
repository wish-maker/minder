"""
Minder Cross-Database Correlation Engine
Discovers relationships between different module data sources
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CorrelationType:
    TEMPORAL = "temporal"
    CAUSAL = "causal"
    SEMANTIC = "semantic"
    STATISTICAL = "statistical"
    SPATIAL = "spatial"


class CorrelationEngine:
    """
    Discovers and manages correlations between modules

    Example use cases:
    - Fund returns ↔ Network latency (trading performance)
    - Fund flows ↔ Weather patterns (seasonal behavior)
    - Network errors ↔ Fund volatility (infrastructure impact)
    """

    def __init__(self, registry, config: Dict[str, Any]):
        self.registry = registry
        self.config = config
        self.correlations: Dict[str, List[Dict]] = {}
        self.cache_ttl = timedelta(hours=1)
        self._cache: Dict[str[datetime, Any]] = {}

    async def discover_correlations(
        self, module_a: str, module_b: str, force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """Discover correlations between two modules"""
        cache_key = f"{module_a}:{module_b}"

        if not force_refresh and cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if datetime.now() - cached_time < self.cache_ttl:
                return cached_data

        logger.info(f"🔍 Discovering correlations: {module_a} ↔ {module_b}")

        mod_a = await self.registry.get_module(module_a)
        mod_b = await self.registry.get_module(module_b)

        if not mod_a or not mod_b:
            logger.error("One or both modules not found")
            return []

        hints_a = await mod_a.get_correlations(module_b)
        hints_b = await mod_b.get_correlations(module_a)

        correlations = await self._analyze_correlations(mod_a, mod_b, hints_a, hints_b)

        self._cache[cache_key] = (datetime.now(), correlations)
        self.correlations[cache_key] = correlations

        logger.info(f"✅ Found {len(correlations)} correlations")
        return correlations

    async def _analyze_correlations(
        self, mod_a: Any, mod_b: Any, hints_a: List[Dict], hints_b: List[Dict]
    ) -> List[Dict[str, Any]]:
        """Analyze and score correlations"""
        correlations = []

        for hint in hints_a:
            correlation = {
                "module_a": mod_a.metadata.name,
                "module_b": mod_b.metadata.name,
                "field_a": hint["field"],
                "field_b": hint["other_field"],
                "type": hint["correlation_type"],
                "strength": hint["strength"],
                "description": hint["description"],
                "discovered_at": datetime.now(),
            }
            correlations.append(correlation)

        for hint in hints_b:
            if not any(c["field_a"] == hint["other_field"] and c["field_b"] == hint["field"] for c in correlations):
                correlation = {
                    "module_a": mod_b.metadata.name,
                    "module_b": mod_a.metadata.name,
                    "field_a": hint["field"],
                    "field_b": hint["other_field"],
                    "type": hint["correlation_type"],
                    "strength": hint["strength"],
                    "description": hint["description"],
                    "discovered_at": datetime.now(),
                }
                correlations.append(correlation)

        correlations.sort(key=lambda x: x["strength"], reverse=True)
        return correlations

    async def get_all_correlations(self) -> Dict[str, List[Dict]]:
        """Get all discovered correlations"""
        return self.correlations

    async def find_anomaly_patterns(self, module: str, anomaly_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Find patterns in anomalies across modules"""
        mod = await self.registry.get_module(module)
        if not mod:
            return []

        anomalies = await mod.get_anomalies(severity="high", limit=1000)

        patterns = []
        for anomaly in anomalies:
            for other_module_name, _ in self.registry.modules.items():
                if other_module_name == module:
                    continue

                other_module = await self.registry.get_module(other_module_name)
                if other_module:
                    other_anomalies = await other_module.get_anomalies(severity="high", limit=100)

                    for other_anomaly in other_anomalies:
                        time_diff = abs((anomaly["detected_at"] - other_anomaly["detected_at"]).total_seconds())

                        if time_diff < 300:
                            patterns.append(
                                {
                                    "type": "temporal_anomaly_cluster",
                                    "modules": [module, other_module_name],
                                    "anomalies": [anomaly, other_anomaly],
                                    "time_difference_seconds": time_diff,
                                    "confidence": max(0, 1 - time_diff / 300),
                                }
                            )

        return sorted(patterns, key=lambda x: x["confidence"], reverse=True)
