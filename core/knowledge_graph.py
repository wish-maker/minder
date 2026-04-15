"""
Minder Knowledge Graph
Stores and queries entity relationships across modules
"""
from typing import Dict, List, Set, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)

class EntityType(Enum):
    """Types of entities in the graph"""
    FUND = "fund"
    NETWORK = "network"
    WEATHER = "weather"
    CRYPTO = "crypto"
    NEWS = "news"
    STOCK = "stock"
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    EVENT = "event"
    CONCEPT = "concept"
    CUSTOM = "custom"

class RelationType(Enum):
    """Types of relationships"""
    CORRELATES = "correlates"
    CAUSES = "causes"
    PRECEDES = "precedes"
    CONTAINS = "contains"
    DEPENDS_ON = "depends_on"
    RELATED_TO = "related_to"
    SAME_AS = "same_as"
    PART_OF = "part_of"
    AFFECTS = "affects"

@dataclass
class Entity:
    """Node in knowledge graph"""
    id: str
    type: EntityType
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    module: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Entity) and self.id == other.id

@dataclass
class Relation:
    """Edge in knowledge graph"""
    source: Entity
    target: Entity
    relation_type: RelationType
    weight: float = 1.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def __hash__(self):
        return hash((self.source.id, self.target.id, self.relation_type))

    def __eq__(self, other):
        return (
            isinstance(other, Relation) and
            self.source.id == other.source.id and
            self.target.id == other.target.id and
            self.relation_type == other.relation_type
        )

class KnowledgeGraph:
    """
    Distributed knowledge graph for cross-module insights

    Features:
    - Multi-module entity resolution
    - Relationship inference
    - Graph traversal and pathfinding
    - Temporal relationship tracking
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.entities: Dict[str, Entity] = {}
        self.relations: Set[Relation] = set()
        self.entity_index: Dict[EntityType, Set[str]] = {}
        self._lock = asyncio.Lock()

    async def add_entity(self, entity: Entity) -> bool:
        """Add entity to graph"""
        async with self._lock:
            if entity.id in self.entities:
                self.entities[entity.id].attributes.update(entity.attributes)
                return True

            self.entities[entity.id] = entity

            if entity.type not in self.entity_index:
                self.entity_index[entity.type] = set()
            self.entity_index[entity.type].add(entity.id)

            return True

    async def add_relation(self, relation: Relation) -> bool:
        """Add relationship to graph"""
        async with self._lock:
            if relation.source.id not in self.entities:
                await self.add_entity(relation.source)
            if relation.target.id not in self.entities:
                await self.add_entity(relation.target)

            self.relations.add(relation)
            return True

    async def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID"""
        return self.entities.get(entity_id)

    async def get_relations(
        self,
        entity_id: str,
        relation_type: Optional[RelationType] = None,
        direction: str = "both"
    ) -> List[Relation]:
        """Get relations for entity"""
        relations = []

        for relation in self.relations:
            if relation_type and relation.relation_type != relation_type:
                continue

            if direction in ["out", "both"] and relation.source.id == entity_id:
                relations.append(relation)

            if direction in ["in", "both"] and relation.target.id == entity_id:
                relations.append(relation)

        return relations

    async def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5
    ) -> Optional[List[Relation]]:
        """Find shortest path between entities using BFS"""
        if source_id not in self.entities or target_id not in self.entities:
            return None

        if source_id == target_id:
            return []

        from collections import deque

        queue = deque([(source_id, [])])
        visited = {source_id}

        while queue:
            current_id, path = queue.popleft()

            if len(path) >= max_depth:
                continue

            relations = await self.get_relations(current_id, direction="out")

            for relation in relations:
                next_id = relation.target.id

                if next_id == target_id:
                    return path + [relation]

                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, path + [relation]))

        return None

    async def query(
        self,
        entity_type: Optional[EntityType] = None,
        attributes: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[Entity]:
        """Query entities by type and attributes"""
        results = []

        candidate_ids = set()
        if entity_type:
            candidate_ids = self.entity_index.get(entity_type, set())
        else:
            candidate_ids = set(self.entities.keys())

        for entity_id in candidate_ids:
            entity = self.entities[entity_id]

            if attributes:
                match = True
                for key, value in attributes.items():
                    if entity.attributes.get(key) != value:
                        match = False
                        break

                if not match:
                    continue

            results.append(entity)

            if len(results) >= limit:
                break

        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get graph statistics"""
        return {
            'total_entities': len(self.entities),
            'total_relations': len(self.relations),
            'entities_by_type': {
                entity_type.value: len(entity_ids)
                for entity_type, entity_ids in self.entity_index.items()
            },
            'relations_by_type': self._count_relations_by_type(),
            'avg_degree': len(self.relations) / max(len(self.entities), 1)
        }

    def _count_relations_by_type(self) -> Dict[str, int]:
        """Count relations by type"""
        counts = {}
        for relation in self.relations:
            rtype = relation.relation_type.value
            counts[rtype] = counts.get(rtype, 0) + 1
        return counts
