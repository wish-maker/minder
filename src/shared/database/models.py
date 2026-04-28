"""
Database data models for Minder.
Defines dataclasses for database optimization.
"""

from dataclasses import dataclass
from typing import List, Any, Optional


@dataclass
class QueryPlan:
    """Represents a query execution plan"""
    query: str
    plan: str
    estimated_cost: float
    actual_cost: Optional[float] = None


@dataclass
class IndexRecommendation:
    """Represents an index recommendation"""
    table: str
    columns: List[str]
    index_type: str
    estimated_impact: str
    reason: str


@dataclass
class SlowQuery:
    """Represents a slow query"""
    query: str
    calls: int
    total_time_ms: float
    mean_time_ms: float
    max_time_ms: float
    rows: int


@dataclass
class TableStatistics:
    """Represents table statistics"""
    schema_name: str
    table_name: str
    row_count: int
    index_count: int
    vacuum_needed: bool
    analyze_needed: bool
