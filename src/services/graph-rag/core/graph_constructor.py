"""
Knowledge Graph Construction Module for Graph RAG

Manages Neo4j knowledge graph construction and operations.
"""

import logging
from typing import Any, Dict, List

from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)


class KnowledgeGraphConstructor:
    """Construct and manage knowledge graph in Neo4j"""

    def __init__(self, uri: str, user: str, password: str, auth_enabled: bool = True):
        """Initialize Neo4j connection"""
        # Neo4j requires authentication by default
        # Use provided credentials for authentication
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        logger.info(f"✅ Connected to Neo4j at {uri} (user: {user})")

    async def close(self):
        """Close Neo4j connection"""
        await self.driver.close()

    async def create_document_node(
        self,
        document_id: str,
        title: str = None,
        source: str = None,
        metadata: Dict[str, Any] = None,
    ) -> bool:
        """
        Create a document node in Neo4j

        Args:
            document_id: Document identifier
            title: Document title
            source: Document source
            metadata: Additional metadata

        Returns:
            True if successful
        """
        async with self.driver.session() as session:
            try:
                query = """
                MERGE (d:Document {id: $document_id})
                ON CREATE SET d.created_at = datetime(),
                              d.title = $title,
                              d.source = $source,
                              d.metadata = $metadata
                RETURN d
                """

                result = await session.run(
                    query,
                    document_id=document_id,
                    title=title,
                    source=source,
                    metadata=metadata,
                )

                return await result.single() is not None

            except Exception as e:
                logger.warning(f"⚠️  Failed to create document node: {e}")
                return False

    async def create_entity_nodes(
        self, document_id: str, entities: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Create entity nodes in Neo4j

        Returns:
            List of created entity IDs
        """
        entity_ids = []

        async with self.driver.session() as session:
            for entity in entities:
                try:
                    query = """
                    MERGE (e:Entity {text: $text, label: $label})
                    ON CREATE SET e.created_at = datetime(),
                                e.description = $description,
                                e.document_ids = [$document_id]
                    ON MATCH SET e.document_ids = [doc_id IN e.document_ids WHERE doc_id <> $document_id] + $document_id
                    RETURN e.text as entity_id
                    """

                    result = await session.run(
                        query,
                        text=entity["text"],
                        label=entity["label"],
                        description=entity.get("description", ""),
                        document_id=document_id,
                    )

                    record = await result.single()
                    if record:
                        entity_ids.append(record["entity_id"])

                except Exception as e:
                    logger.warning(
                        f"⚠️  Failed to create entity {entity.get('text')}: {e}"
                    )

        logger.info(f"✅ Created {len(entity_ids)} entity nodes")
        return entity_ids

    async def create_relationship_nodes(
        self, document_id: str, relationships: List[Dict[str, Any]]
    ) -> int:
        """
        Create relationship nodes in Neo4j

        Returns:
            Number of created relationships
        """
        count = 0

        async with self.driver.session() as session:
            for rel in relationships:
                try:
                    query = """
                    MATCH (s:Entity {text: $subject})
                    MATCH (o:Entity {text: $object})
                    MERGE (s)-[r:RELATES_TO {predicate: $predicate, document_id: $document_id}]->(o)
                    ON CREATE SET r.type = $type,
                                  r.created_at = datetime()
                    RETURN r
                    """

                    result = await session.run(
                        query,
                        subject=rel["subject"],
                        object=rel["object"],
                        predicate=rel["predicate"],
                        type=rel.get("type", "UNKNOWN"),
                        document_id=document_id,
                    )

                    if await result.single():
                        count += 1

                except Exception as e:
                    logger.warning(f"⚠️  Failed to create relationship: {e}")

        logger.info(f"✅ Created {count} relationship nodes")
        return count

    async def link_document_to_entities(
        self, document_id: str, entity_ids: List[str]
    ) -> int:
        """
        Link document to entities

        Args:
            document_id: Document identifier
            entity_ids: List of entity IDs

        Returns:
            Number of document-entity links created
        """
        count = 0

        async with self.driver.session() as session:
            for entity_id in entity_ids:
                try:
                    query = """
                    MATCH (d:Document {id: $document_id})
                    MATCH (e:Entity {text: $entity_id})
                    MERGE (d)-[r:MENTIONS]->(e)
                    ON CREATE SET r.created_at = datetime()
                    RETURN r
                    """

                    result = await session.run(
                        query, document_id=document_id, entity_id=entity_id
                    )

                    if await result.single():
                        count += 1

                except Exception as e:
                    logger.warning(f"⚠️  Failed to link document to entity: {e}")

        logger.info(f"✅ Linked document to {count} entities")
        return count

    async def delete_document(self, document_id: str) -> Dict[str, int]:
        """Delete a document's graph: its RELATES_TO edges (tagged with this
        document_id), the Document node and its MENTIONS edges, and any Entity left
        with no edges afterwards. Entities still shared with other documents are
        kept. Returns the deletion counts."""
        async with self.driver.session() as session:
            rels = await session.run(
                "MATCH ()-[r:RELATES_TO {document_id: $document_id}]->() DELETE r",
                document_id=document_id,
            )
            rels_deleted = (await rels.consume()).counters.relationships_deleted

            doc = await session.run(
                "MATCH (d:Document {id: $document_id}) DETACH DELETE d",
                document_id=document_id,
            )
            docs_deleted = (await doc.consume()).counters.nodes_deleted

            orphans = await session.run("MATCH (e:Entity) WHERE NOT (e)--() DELETE e")
            orphans_deleted = (await orphans.consume()).counters.nodes_deleted

        logger.info(
            f"✅ Deleted document graph {document_id}: {docs_deleted} document, "
            f"{rels_deleted} relationships, {orphans_deleted} orphaned entities"
        )
        return {
            "document_deleted": docs_deleted,
            "relationships_deleted": rels_deleted,
            "orphan_entities_deleted": orphans_deleted,
        }

    async def get_graph_statistics(self) -> Dict[str, int]:
        """
        Get graph statistics

        Returns:
            Dict with node and relationship counts
        """
        async with self.driver.session() as session:
            # Count nodes
            node_result = await session.run("MATCH (n) RETURN count(n) as count")
            node_record = await node_result.single()
            node_count = node_record["count"] if node_record else 0

            # Count relationships
            rel_result = await session.run("MATCH ()-[r]->() RETURN count(r) as count")
            rel_record = await rel_result.single()
            rel_count = rel_record["count"] if rel_record else 0

            # Count documents
            doc_result = await session.run(
                "MATCH (d:Document) RETURN count(d) as count"
            )
            doc_record = await doc_result.single()
            doc_count = doc_record["count"] if doc_record else 0

        return {"nodes": node_count, "relationships": rel_count, "documents": doc_count}
