"""
Graph-Based Retrieval Module for Graph RAG

Implements graph-based retrieval with context enhancement.
"""

import logging
from typing import Any, Dict, List, Optional

from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)


class GraphRetriever:
    """Graph-based retrieval with context enhancement"""

    def __init__(self, uri: str, user: str, password: str, auth_enabled: bool = True):
        """Initialize Neo4j connection for retrieval"""
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        logger.info(f"✅ Graph Retriever connected to Neo4j at {uri}")

    async def close(self):
        """Close Neo4j connection"""
        await self.driver.close()

    async def find_related_entities(
        self,
        entity_name: str,
        relationship_type: Optional[str] = None,
        max_depth: int = 2,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find entities related to a given entity

        Args:
            entity_name: Name of the entity to find relations for
            relationship_type: Filter by relationship type (optional)
            max_depth: Maximum depth of graph traversal
            limit: Maximum number of related entities to return

        Returns:
            List of related entities with relationships
        """
        related_entities = []

        try:
            async with self.driver.session() as session:
                if relationship_type:
                    query = """
                    MATCH (e:Entity {text: $entity_name})-[r:RELATES_TO {predicate: $rel_type}]->(related:Entity)
                    RETURN related.text as entity, related.label as label,
                           r.predicate as predicate, r.type as type
                    LIMIT $limit
                    """
                    params = {"entity_name": entity_name, "rel_type": relationship_type, "limit": limit}
                else:
                    query = """
                    MATCH path = (e:Entity {text: $entity_name})-[*1..$max_depth]-(related:Entity)
                    WITH nodes(path) as entities
                    UNWIND entities as entity
                    RETURN entity.text as entity, entity.label as label
                    LIMIT $limit
                    """
                    params = {"entity_name": entity_name, "max_depth": max_depth, "limit": limit}

                result = await session.run(query, **params)

                async for record in result:
                    related_entities.append({
                        "text": record["entity"],
                        "label": record["label"],
                        "predicate": record.get("predicate", "RELATED"),
                        "type": record.get("type", "RELATION")
                    })

        except Exception as e:
            logger.error(f"❌ Graph retrieval failed: {e}")

        logger.info(f"🔍 Found {len(related_entities)} related entities for '{entity_name}'")
        return related_entities

    async def get_entity_context(
        self,
        entity_name: str,
        context_window: int = 3
    ) -> Dict[str, Any]:
        """
        Get contextual information about an entity

        Args:
            entity_name: Name of the entity
            context_window: Number of related entities to include

        Returns:
            Dict with entity context including related entities and documents
        """
        try:
            async with self.driver.session() as session:
                # Get entity details
                entity_query = """
                MATCH (e:Entity {text: $entity_name})
                RETURN e.text as text, e.label as label, e.description as description
                """
                entity_result = await session.run(entity_query, entity_name=entity_name)
                entity_record = await entity_result.single()

                if not entity_record:
                    return {"error": "Entity not found"}

                # Get related entities
                related_query = """
                MATCH (e:Entity {text: $entity_name})-[r:RELATES_TO]->(related:Entity)
                RETURN related.text as text, related.label as label, r.predicate as predicate
                LIMIT $context_window
                """
                related_result = await session.run(related_query, entity_name=entity_name, context_window=context_window)

                related_entities = []
                async for record in related_result:
                    related_entities.append({
                        "text": record["text"],
                        "label": record["label"],
                        "predicate": record["predicate"]
                    })

                # Get documents that mention this entity
                docs_query = """
                MATCH (e:Entity {text: $entity_name})<-[:MENTIONS]-(d:Document)
                RETURN d.id as doc_id, d.title as title
                LIMIT 5
                """
                docs_result = await session.run(docs_query, entity_name=entity_name)

                documents = []
                async for record in docs_result:
                    documents.append({
                        "id": record["doc_id"],
                        "title": record["title"]
                    })

                return {
                    "entity": {
                        "text": entity_record["text"],
                        "label": entity_record["label"],
                        "description": entity_record["description"]
                    },
                    "related_entities": related_entities,
                    "documents": documents,
                    "context_window": context_window
                }

        except Exception as e:
            logger.error(f"❌ Entity context retrieval failed: {e}")
            return {"error": f"Failed to get context: {e}"}

    async def graph_search(
        self,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search graph for entities matching query

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching entities with their context
        """
        try:
            async with self.driver.session() as session:
                search_query = """
                MATCH (e:Entity)
                WHERE e.text CONTAINS $query OR e.label CONTAINS $query
                RETURN e.text as text, e.label as label, e.description as description
                LIMIT $limit
                """

                result = await session.run(search_query, query=query, limit=limit)

                entities = []
                async for record in result:
                    entities.append({
                        "text": record["text"],
                        "label": record["label"],
                        "description": record["description"]
                    })

                logger.info(f"🔍 Graph search found {len(entities)} entities for '{query}'")
                return entities

        except Exception as e:
            logger.error(f"❌ Graph search failed: {e}")
            return []
