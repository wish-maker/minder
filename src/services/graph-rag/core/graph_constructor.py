"""
Knowledge Graph Construction Module for Graph RAG

Manages Neo4j knowledge graph construction and operations.
"""

import json
import logging
from typing import Any, Dict, List, Optional

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

    async def construct_graph(
        self,
        document_id: str,
        owner_id: str,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        title: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        kb_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """Build (or rebuild) a document's contribution to the graph atomically.

        Everything runs in ONE write transaction (#668, following delete_document's
        precedent) so a mid-sequence failure can't leave a half-built graph —
        entities written but no relationships/links, indistinguishable from a
        clean "constructed with zero relationships". This deliberately supersedes
        the earlier per-item best-effort behavior (#351): a failure now aborts the
        whole construct and surfaces as an error, rather than silently committing a
        partial graph. (Extraction yields plain string text/label values, so the
        only realistic failure here is an infra one — exactly when atomicity is
        wanted.)

        Re-ingest is a FULL REPLACE of this document's edges (#668 item 2, matching
        the #639 hard-delete precedent): the document's existing RELATES_TO and
        MENTIONS edges are dropped first, so re-processing an edited document (a
        removed paragraph) drops entities/relationships that are no longer present
        instead of leaving them permanently attributed. Entities shared with other
        documents survive; entities left orphaned are cleaned up (scoped to the ones
        this document previously touched, like delete_document).

        Document metadata is upserted with COALESCE (#668 item 3): a re-POST that
        omits title/source/metadata keeps the previously-set values instead of
        blanking them with the request-model defaults.

        Returns {entity_count, relationship_count, mentions_count} — the counts
        actually committed.

        #782: every node/edge is scoped to ``owner_id`` (the authenticated
        caller). Document and Entity nodes both carry an ``owner_id`` and are
        MERGEd on it, so two tenants extracting the same term (or reusing the
        same document_id) get SEPARATE nodes — one tenant's private content
        never merges into another's, and one tenant's re-ingest/delete can never
        touch another's edges. All MATCHes below are likewise owner-scoped.
        """

        async def _construct_in_one_transaction(tx):
            # Capture the entities this document currently mentions BEFORE dropping
            # its edges, so the post-rebuild orphan check only re-checks these
            # (delete_document's scoped-orphan precedent) rather than scanning the
            # whole graph. Owner-scoped: only THIS owner's document/entities.
            mentioned = await tx.run(
                "MATCH (:Document {id: $document_id, owner_id: $owner_id})"
                "-[:MENTIONS]->(e:Entity {owner_id: $owner_id}) "
                "RETURN e.text AS text, e.label AS label",
                document_id=document_id,
                owner_id=owner_id,
            )
            previously_mentioned = [
                (record["text"], record["label"]) async for record in mentioned
            ]

            # Full-replace: drop this document's old edges before rebuilding. Both
            # endpoints owner-scoped so a document_id another tenant happens to
            # reuse can't have its edges deleted here.
            await (
                await tx.run(
                    "MATCH (:Entity {owner_id: $owner_id})"
                    "-[r:RELATES_TO {document_id: $document_id}]->"
                    "(:Entity {owner_id: $owner_id}) DELETE r",
                    document_id=document_id,
                    owner_id=owner_id,
                )
            ).consume()
            await (
                await tx.run(
                    "MATCH (:Document {id: $document_id, owner_id: $owner_id})"
                    "-[m:MENTIONS]->() DELETE m",
                    document_id=document_id,
                    owner_id=owner_id,
                )
            ).consume()

            # Upsert the Document node (keyed by id + owner_id). COALESCE keeps a
            # previously-set title/source/metadata/kb_id when the current request
            # omits it (passes None), instead of the old blind ON MATCH SET that
            # overwrote with request-model defaults. metadata is JSON-encoded:
            # Neo4j rejects a raw Map property.
            await (
                await tx.run(
                    """
                    MERGE (d:Document {id: $document_id, owner_id: $owner_id})
                    ON CREATE SET d.created_at = datetime(),
                                  d.title = $title,
                                  d.source = $source,
                                  d.metadata = $metadata,
                                  d.kb_id = $kb_id
                    ON MATCH SET d.title = COALESCE($title, d.title),
                                 d.source = COALESCE($source, d.source),
                                 d.metadata = COALESCE($metadata, d.metadata),
                                 d.kb_id = COALESCE($kb_id, d.kb_id)
                    """,
                    document_id=document_id,
                    owner_id=owner_id,
                    title=title,
                    source=source,
                    metadata=json.dumps(metadata) if metadata else None,
                    kb_id=kb_id,
                )
            ).consume()

            # Entities (MERGE by {text,label,owner_id}; re-add this document_id to
            # the array). owner_id in the MERGE key keeps each tenant's entities
            # distinct even for identical text/label.
            created_entities: List[tuple] = []
            for entity in entities:
                result = await tx.run(
                    """
                    MERGE (e:Entity {text: $text, label: $label,
                                     owner_id: $owner_id})
                    ON CREATE SET e.created_at = datetime(),
                                  e.description = $description,
                                  e.document_ids = [$document_id]
                    ON MATCH SET e.document_ids =
                        [doc_id IN e.document_ids WHERE doc_id <> $document_id]
                        + $document_id
                    RETURN e.text AS text, e.label AS label
                    """,
                    text=entity["text"],
                    label=entity["label"],
                    description=entity.get("description", ""),
                    document_id=document_id,
                    owner_id=owner_id,
                )
                record = await result.single()
                if record:
                    created_entities.append((record["text"], record["label"]))

            # Document -> Entity MENTIONS edges (rebuilt from the fresh entities).
            mentions_count = 0
            for text, label in created_entities:
                result = await tx.run(
                    """
                    MATCH (d:Document {id: $document_id, owner_id: $owner_id})
                    MATCH (e:Entity {text: $text, label: $label,
                                     owner_id: $owner_id})
                    MERGE (d)-[r:MENTIONS]->(e)
                    ON CREATE SET r.created_at = datetime()
                    RETURN r
                    """,
                    document_id=document_id,
                    owner_id=owner_id,
                    text=text,
                    label=label,
                )
                if await result.single():
                    mentions_count += 1

            # Relationships (tagged with this document_id so re-ingest can scope
            # them). Both entities owner-scoped.
            relationship_count = 0
            for rel in relationships:
                result = await tx.run(
                    """
                    MATCH (s:Entity {text: $subject, owner_id: $owner_id})
                    MATCH (o:Entity {text: $object, owner_id: $owner_id})
                    MERGE (s)-[r:RELATES_TO {predicate: $predicate,
                                             document_id: $document_id}]->(o)
                    ON CREATE SET r.type = $type,
                                  r.created_at = datetime()
                    RETURN r
                    """,
                    subject=rel["subject"],
                    object=rel["object"],
                    predicate=rel["predicate"],
                    type=rel.get("type", "UNKNOWN"),
                    document_id=document_id,
                    owner_id=owner_id,
                )
                if await result.single():
                    relationship_count += 1

            # Orphan cleanup: an entity this document PREVIOUSLY mentioned but that
            # is no longer connected to anything after the rebuild (dropped from the
            # new extraction and not shared with another document) is deleted —
            # scoped to previously-touched entities, mirroring delete_document.
            for text, label in previously_mentioned:
                await (
                    await tx.run(
                        "MATCH (e:Entity {text: $text, label: $label, "
                        "owner_id: $owner_id}) "
                        "WHERE NOT (e)--() DELETE e",
                        text=text,
                        label=label,
                        owner_id=owner_id,
                    )
                ).consume()

            return len(created_entities), relationship_count, mentions_count

        async with self.driver.session() as session:
            (
                entity_count,
                relationship_count,
                mentions_count,
            ) = await session.execute_write(_construct_in_one_transaction)

        logger.info(
            f"✅ Constructed graph for {document_id}: {entity_count} entities, "
            f"{relationship_count} relationships, {mentions_count} mentions"
        )
        return {
            "entity_count": entity_count,
            "relationship_count": relationship_count,
            "mentions_count": mentions_count,
        }

    async def delete_document(self, document_id: str, owner_id: str) -> Dict[str, int]:
        """Delete a document's graph: its RELATES_TO edges (tagged with this
        document_id), the Document node and its MENTIONS edges, and any Entity left
        with no edges afterwards. Entities still shared with other documents are
        kept. Returns the deletion counts.

        #782: owner-scoped — only the caller's own Document/Entity nodes are
        touched, so a caller can't delete (or even affect the orphan-cleanup of)
        another tenant's graph by naming a document_id they don't own. A
        document_id that exists only under another owner deletes nothing
        (document_deleted == 0)."""

        async def _delete_in_one_transaction(tx):
            # Capture which entities THIS document actually touches before deleting
            # anything -- the orphan check below must only re-check these, not scan
            # the whole graph (see the comment on that step for why).
            mentioned = await tx.run(
                "MATCH (:Document {id: $document_id, owner_id: $owner_id})"
                "-[:MENTIONS]->(e:Entity {owner_id: $owner_id}) "
                "RETURN e.text AS text, e.label AS label",
                document_id=document_id,
                owner_id=owner_id,
            )
            touched_entities = [
                (record["text"], record["label"]) async for record in mentioned
            ]

            rels = await tx.run(
                "MATCH (:Entity {owner_id: $owner_id})"
                "-[r:RELATES_TO {document_id: $document_id}]->"
                "(:Entity {owner_id: $owner_id}) DELETE r",
                document_id=document_id,
                owner_id=owner_id,
            )
            rels_deleted = (await rels.consume()).counters.relationships_deleted

            doc = await tx.run(
                "MATCH (d:Document {id: $document_id, owner_id: $owner_id}) "
                "DETACH DELETE d",
                document_id=document_id,
                owner_id=owner_id,
            )
            docs_deleted = (await doc.consume()).counters.nodes_deleted

            # Scoped to entities this document touched, not a global `MATCH (e:Entity)
            # WHERE NOT (e)--() DELETE e` scan: that used to delete ANY currently-
            # orphaned entity anywhere in the graph, including ones a concurrent
            # construct-graph call had just MERGEd a fresh edge onto a moment earlier
            # in an interleaved auto-commit statement (the TOCTOU this transaction
            # closes) -- and it did needless work reprocessing entities untouched by
            # this delete at all.
            orphans_deleted = 0
            for text, label in touched_entities:
                result = await tx.run(
                    "MATCH (e:Entity {text: $text, label: $label, "
                    "owner_id: $owner_id}) "
                    "WHERE NOT (e)--() DELETE e",
                    text=text,
                    label=label,
                    owner_id=owner_id,
                )
                orphans_deleted += (await result.consume()).counters.nodes_deleted

            return rels_deleted, docs_deleted, orphans_deleted

        async with self.driver.session() as session:
            rels_deleted, docs_deleted, orphans_deleted = await session.execute_write(
                _delete_in_one_transaction
            )

        logger.info(
            f"✅ Deleted document graph {document_id}: {docs_deleted} document, "
            f"{rels_deleted} relationships, {orphans_deleted} orphaned entities"
        )
        return {
            "document_deleted": docs_deleted,
            "relationships_deleted": rels_deleted,
            "orphan_entities_deleted": orphans_deleted,
        }

    async def get_graph_statistics(self, owner_id: str) -> Dict[str, Any]:
        """
        Get graph statistics — an overview of what's in the caller's knowledge graph.

        #782: every count is scoped to ``owner_id`` — a caller sees only the size
        of their OWN graph, never a global total that would leak the existence /
        volume of other tenants' data. ``nodes``/``relationships`` count this
        owner's Document+Entity nodes and their MENTIONS/RELATES_TO edges.

        Returns:
            Dict with total node/relationship counts, the Document and Entity node
            counts, and the per-NER-label entity distribution (``entity_types``).
        """
        async with self.driver.session() as session:
            # Nodes = this owner's Document + Entity nodes.
            node_result = await session.run(
                "MATCH (n) WHERE (n:Document OR n:Entity) AND n.owner_id = $owner_id "
                "RETURN count(n) as count",
                owner_id=owner_id,
            )
            node_record = await node_result.single()
            node_count = node_record["count"] if node_record else 0

            # Relationships = edges between this owner's nodes (MENTIONS from the
            # owner's Document, RELATES_TO between the owner's Entities).
            rel_result = await session.run(
                "MATCH (a)-[r]->(b) "
                "WHERE a.owner_id = $owner_id AND b.owner_id = $owner_id "
                "RETURN count(r) as count",
                owner_id=owner_id,
            )
            rel_record = await rel_result.single()
            rel_count = rel_record["count"] if rel_record else 0

            # Count documents
            doc_result = await session.run(
                "MATCH (d:Document {owner_id: $owner_id}) RETURN count(d) as count",
                owner_id=owner_id,
            )
            doc_record = await doc_result.single()
            doc_count = doc_record["count"] if doc_record else 0

            # Count entities + break them down by NER label so a caller can see what
            # kind of things the graph holds (PERSON/ORG/GPE/…), most common first.
            entity_result = await session.run(
                "MATCH (e:Entity {owner_id: $owner_id}) RETURN count(e) as count",
                owner_id=owner_id,
            )
            entity_record = await entity_result.single()
            entity_count = entity_record["count"] if entity_record else 0

            types_result = await session.run(
                "MATCH (e:Entity {owner_id: $owner_id}) "
                "RETURN e.label as label, count(e) as count "
                "ORDER BY count DESC",
                owner_id=owner_id,
            )
            entity_types = {
                record["label"]: record["count"]
                async for record in types_result
                if record["label"] is not None
            }

        return {
            "nodes": node_count,
            "relationships": rel_count,
            "documents": doc_count,
            "entities": entity_count,
            "entity_types": entity_types,
        }

    async def list_documents(self, owner_id: str) -> List[Dict[str, Any]]:
        """List the caller's Document nodes (id/title/source + how many entities
        each mentions), newest first — so a caller can browse what's in their own
        graph and pick a document to inspect or delete without knowing its id up
        front. #782: owner-scoped, so a caller never sees another tenant's document
        titles/sources (the enumeration+delete leak in the issue)."""
        async with self.driver.session() as session:
            result = await session.run(
                "MATCH (d:Document {owner_id: $owner_id}) "
                "OPTIONAL MATCH (d)-[:MENTIONS]->(e:Entity) "
                "RETURN d.id AS id, d.title AS title, d.source AS source, "
                "d.kb_id AS kb_id, "
                "d.created_at AS created_at, count(e) AS entity_count "
                "ORDER BY d.created_at DESC",
                owner_id=owner_id,
            )
            documents = []
            async for record in result:
                created_at = record["created_at"]
                documents.append(
                    {
                        "id": record["id"],
                        "title": record["title"],
                        "source": record["source"],
                        "kb_id": record["kb_id"],
                        # Neo4j DateTime isn't JSON-serializable — stringify it.
                        "created_at": str(created_at)
                        if created_at is not None
                        else None,
                        "entity_count": record["entity_count"],
                    }
                )
        return documents
