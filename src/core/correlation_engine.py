"""
Minder Correlation Engine
Provides correlation analysis between modules
"""

from typing import List, Dict, Any
from datetime import datetime


class CorrelationEngine:
    """Correlation analysis engine for cross-module insights"""

    def __init__(self):
        self.correlations: Dict[str, List[Dict]] = {}

    def add_correlation(
        self,
        source_module: str,
        target_module: str,
        correlation_type: str,
        strength: float,
        metadata: Dict = None,
    ):
        """Add a correlation between two modules"""
        key = f"{source_module}:{target_module}"
        if key not in self.correlations:
            self.correlations[key] = []

        self.correlations[key].append(
            {
                "type": correlation_type,
                "strength": strength,
                "metadata": metadata or {},
                "timestamp": datetime.now().isoformat(),
            }
        )

    def get_correlations(self, source_module: str, target_module: str = None) -> List[Dict]:
        """Get correlations for a module"""
        if target_module:
            key = f"{source_module}:{target_module}"
            return self.correlations.get(key, [])
        else:
            # Return all correlations for source module
            result = []
            for key, correlations in self.correlations.items():
                if key.startswith(f"{source_module}:"):
                    result.extend(correlations)
            return result

    def calculate_correlation(self, data1: List[float], data2: List[float]) -> float:
        """Calculate correlation coefficient between two datasets"""
        import statistics

        if len(data1) != len(data2) or len(data1) < 2:
            return 0.0

        try:
            mean1 = statistics.mean(data1)
            mean2 = statistics.mean(data2)

            numerator = sum((x - mean1) * (y - mean2) for x, y in zip(data1, data2))
            denominator = (
                sum((x - mean1) ** 2 for x in data1) ** 0.5
                * sum((y - mean2) ** 2 for y in data2) ** 0.5
            )

            if denominator == 0:
                return 0.0

            return numerator / denominator
        except:
            return 0.0


# Global correlation engine instance
correlation_engine = CorrelationEngine()
