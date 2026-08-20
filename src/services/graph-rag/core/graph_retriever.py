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
        owner_id: str,
        relationship_type: Optional[str] = None,
        max_depth: int = 2,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find entities related to a given entity

        Args:
            entity_name: Name of the entity to find relations for
            owner_id: Tenant scope (#782) — traversal is confined to this owner's
                own Entity nodes, so it can never surface another tenant's entities
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
                    # toLower() on both sides: entity text case in the graph reflects
                    # however it was originally extracted, which won't always match a
                    # query's casing (e.g. a lowercase query against a capitalized
                    # stored entity) - exact case-sensitive matching silently found
                    # nothing for anything but an exact case match (#248).
                    # #782: both endpoints owner-scoped.
                    query = """
                    MATCH (e:Entity {owner_id: $owner_id})
                          -[r:RELATES_TO {predicate: $rel_type}]->
                          (related:Entity {owner_id: $owner_id})
                    WHERE toLower(e.text) = toLower($entity_name)
                    RETURN related.text as entity, related.label as label,
                           r.predicate as predicate, r.type as type
                    LIMIT $limit
                    """
                    params: Dict[str, Any] = {
                        "entity_name": entity_name,
                        "rel_type": relationship_type,
                        "limit": limit,
                        "owner_id": owner_id,
                    }
                else:
                    # Neo4j 5.x doesn't support parameterized path lengths
                    # Use string formatting for depth value -- clamp/cast first since
                    # this value goes straight into the query string, not a bound
                    # parameter; not currently reachable with an unsafe value (the
                    # only caller bounds it via Pydantic ge=1,le=4) but this function
                    # has its own callers in the future, so don't rely on that alone.
                    safe_depth = max(1, min(int(max_depth), 4))
                    # Case-insensitive CONTAINS for partial matching (e.g., "apple"
                    # matches "Apple Computer") - see the case-sensitivity note above.
                    # Traverse RELATES_TO only (not the untyped `-[*..]-` this used to
                    # be): that matched ANY relationship including MENTIONS, so a path
                    # could pass through a Document node - nodes(path) then included
                    # it, and a Document has no .text/.label, producing a null entry
                    # in every multi-hop result set.
                    # #782: start node AND the traversed related node owner-scoped
                    # (the [:RELATES_TO] edges are already only ever between one
                    # owner's entities, so the whole path stays within the tenant).
                    query = f"""
                    MATCH (e:Entity {{owner_id: $owner_id}})
                    WHERE toLower(e.text) CONTAINS toLower($entity_name)
                    MATCH path = (e)-[:RELATES_TO*1..{safe_depth}]-
                                 (related:Entity {{owner_id: $owner_id}})
                    WHERE related.text <> e.text
                    WITH nodes(path) as entities, e.text as start_text
                    UNWIND entities as entity
                    WITH entity, start_text
                    WHERE entity.text <> start_text
                    RETURN DISTINCT entity.text as entity, entity.label as label
                    LIMIT $limit
                    """
                    params = {
                        "entity_name": entity_name,
                        "limit": limit,
                        "owner_id": owner_id,
                    }

                result = await session.run(query, **params)

                async for record in result:
                    related_entities.append(
                        {
                            "text": record["entity"],
                            "label": record["label"],
                            "predicate": record.get("predicate", "RELATED"),
                            "type": record.get("type", "RELATION"),
                        }
                    )

        except Exception as e:
            logger.error(f"❌ Graph retrieval failed: {e}")

        logger.info(
            f"🔍 Found {len(related_entities)} related entities for '{entity_name}'"
        )
        return related_entities

    async def get_entity_context(
        self, entity_name: str, owner_id: str, context_window: int = 3
    ) -> Dict[str, Any]:
        """
        Get contextual information about an entity

        Args:
            entity_name: Name of the entity
            owner_id: Tenant scope (#782) — resolves the entity, its neighbours,
                and the mentioning documents only within this owner's graph
            context_window: Number of related entities to include

        Returns:
            Dict with entity context including related entities and documents
        """
        try:
            async with self.driver.session() as session:
                # Get entity details (case-insensitive - see find_related_entities;
                # LIMIT 1 since text alone isn't unique across different labels,
                # e.g. a PERSON and a NOUN_PHRASE node can share the same text).
                # #782: owner-scoped.
                entity_query = """
                MATCH (e:Entity {owner_id: $owner_id})
                WHERE toLower(e.text) = toLower($entity_name)
                RETURN e.text as text, e.label as label, e.description as description
                LIMIT 1
                """
                entity_result = await session.run(
                    entity_query, entity_name=entity_name, owner_id=owner_id
                )
                entity_record = await entity_result.single()

                if not entity_record:
                    return {"error": "Entity not found"}

                # Get related entities
                related_query = """
                MATCH (e:Entity {owner_id: $owner_id})-[r:RELATES_TO]->
                      (related:Entity {owner_id: $owner_id})
                WHERE toLower(e.text) = toLower($entity_name)
                RETURN related.text as text, related.label as label, r.predicate as predicate
                LIMIT $context_window
                """
                related_result = await session.run(
                    related_query,
                    entity_name=entity_name,
                    context_window=context_window,
                    owner_id=owner_id,
                )

                related_entities = []
                async for record in related_result:
                    related_entities.append(
                        {
                            "text": record["text"],
                            "label": record["label"],
                            "predicate": record["predicate"],
                        }
                    )

                # Get documents that mention this entity (owner-scoped).
                docs_query = """
                MATCH (e:Entity {owner_id: $owner_id})<-[:MENTIONS]-
                      (d:Document {owner_id: $owner_id})
                WHERE toLower(e.text) = toLower($entity_name)
                RETURN DISTINCT d.id as doc_id, d.title as title
                LIMIT 5
                """
                docs_result = await session.run(
                    docs_query, entity_name=entity_name, owner_id=owner_id
                )

                documents = []
                async for record in docs_result:
                    documents.append({"id": record["doc_id"], "title": record["title"]})

                return {
                    "entity": {
                        "text": entity_record["text"],
                        "label": entity_record["label"],
                        "description": entity_record["description"],
                    },
                    "related_entities": related_entities,
                    "documents": documents,
                    "context_window": context_window,
                }

        except Exception as e:
            logger.error(f"❌ Entity context retrieval failed: {e}")
            return {"error": f"Failed to get context: {e}"}

    async def graph_search(
        self, query: str, owner_id: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search graph for entities matching query

        Args:
            query: Search query
            owner_id: Tenant scope (#782) — searches only this owner's entities
            limit: Maximum number of results

        Returns:
            List of matching entities with their context
        """
        try:
            async with self.driver.session() as session:
                search_query = """
                MATCH (e:Entity {owner_id: $owner_id})
                WHERE toLower(e.text) CONTAINS toLower($search_term)
                   OR toLower(e.label) CONTAINS toLower($search_term)
                RETURN e.text as text, e.label as label, e.description as description
                LIMIT $limit
                """

                # Cypher param can't be named "query" -- AsyncSession.run's own
                # first positional parameter is ALSO named "query", so
                # `query=query` here would crash every call with "run() got
                # multiple values for argument 'query'" (confirmed live).
                result = await session.run(
                    search_query, search_term=query, limit=limit, owner_id=owner_id
                )

                entities = []
                async for record in result:
                    entities.append(
                        {
                            "text": record["text"],
                            "label": record["label"],
                            "description": record["description"],
                        }
                    )

                logger.info(
                    f"🔍 Graph search found {len(entities)} entities for '{query}'"
                )
                return entities

        except Exception as e:
            logger.error(f"❌ Graph search failed: {e}")
            return []
