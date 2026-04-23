"""
Minder Knowledge Graph
Manages knowledge graph and entity relationships
"""

from typing import List, Dict, Any
from datetime import datetime


class KnowledgeGraph:
    """Knowledge graph for storing entity relationships"""

    def __init__(self):
        self.entities: Dict[str, Dict] = {}
        self.relationships: List[Dict] = []

    def add_entity(self, entity_id: str, entity_type: str, properties: Dict = None):
        """Add an entity to the knowledge graph"""
        self.entities[entity_id] = {
            "id": entity_id,
            "type": entity_type,
            "properties": properties or {},
            "created_at": datetime.now().isoformat(),
        }

    def add_relationship(
        self, source_id: str, target_id: str, relationship_type: str, properties: Dict = None
    ):
        """Add a relationship between two entities"""
        self.relationships.append(
            {
                "source": source_id,
                "target": target_id,
                "type": relationship_type,
                "properties": properties or {},
                "created_at": datetime.now().isoformat(),
            }
        )

    def get_entity(self, entity_id: str) -> Dict:
        """Get entity by ID"""
        return self.entities.get(entity_id)

    def get_relationships(self, entity_id: str = None, relationship_type: str = None) -> List[Dict]:
        """Get relationships from the knowledge graph"""
        result = []
        for rel in self.relationships:
            if entity_id and rel["source"] != entity_id:
                continue
            if relationship_type and rel["type"] != relationship_type:
                continue
            result.append(rel)
        return result

    def query(self, query_type: str, **kwargs) -> List[Dict]:
        """Query the knowledge graph"""
        # Simple query implementation
        if query_type == "entities_by_type":
            entity_type = kwargs.get("entity_type")
            return [e for e in self.entities.values() if e["type"] == entity_type]
        elif query_type == "related_entities":
            entity_id = kwargs.get("entity_id")
            relationships = self.get_relationships(entity_id)
            return [self.entities.get(rel["target"]) for rel in relationships]
        else:
            return []


# Global knowledge graph instance
knowledge_graph = KnowledgeGraph()
