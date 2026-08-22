"""
API Routes for Graph RAG Service

All FastAPI endpoints for entity extraction, graph construction, and retrieval.
"""

import asyncio
import logging

from core.entity_extractor import EntityExtractor
from core.graph_constructor import KnowledgeGraphConstructor
from core.graph_retriever import GraphRetriever
from fastapi import APIRouter, Depends, HTTPException
from models.schemas import (
    EntityContextRequest,
    EntityContextResponse,
    EntityExtractionRequest,
    EntityExtractionResponse,
    GraphDocumentsResponse,
    GraphRetrievalRequest,
    GraphRetrievalResponse,
    GraphSearchRequest,
    GraphSearchResponse,
    GraphStatsResponse,
    KnowledgeGraphRequest,
    KnowledgeGraphResponse,
)

from shared.auth.jwt_middleware import get_current_user_or_service
from shared.errors import backend_http_error
from shared.tenancy import resolve_owner_id

logger = logging.getLogger(__name__)

# The tenant scope for #782 is now the platform-wide canonical helper
# shared.tenancy.resolve_owner_id (behaviour-identical to the old local _owner_id:
# sub required, service token -> "internal-service", 401 on a missing subject).
# Unifies ownership with rag-pipeline/marketplace on one column name + predicate;
# see docs/architecture/tenancy-and-correlation.md.


async def extract_entities_handler(
    request: EntityExtractionRequest, entity_extractor: EntityExtractor
) -> EntityExtractionResponse:
    """Handle entity extraction requests"""
    try:
        # spaCy NER is synchronous, CPU-bound work — run it off the event loop so
        # one extraction can't stall every other in-flight request (same class of
        # fix as rag-pipeline's Qdrant offload, #211).
        result = await asyncio.to_thread(
            entity_extractor.extract_entities,
            text=request.text,
            extract_relationships=request.extract_relationships,
        )

        return EntityExtractionResponse(
            success=True,
            entities=result["entities"],
            relationships=result["relationships"],
            entity_count=result["entity_count"],
            relationship_count=result["relationship_count"],
        )

    except Exception as e:
        logger.error(f"❌ Entity extraction failed: {e}")
        raise backend_http_error(e, "Entity extraction")


async def construct_knowledge_graph_handler(
    request: KnowledgeGraphRequest,
    owner_id: str,
    entity_extractor: EntityExtractor,
    graph_constructor: KnowledgeGraphConstructor,
) -> KnowledgeGraphResponse:
    """Handle knowledge graph construction requests"""
    try:
        # Extract entities first (honour the request's flag instead of forcing True).
        # Offloaded: spaCy NER is blocking CPU work (see extract_entities_handler).
        extraction_result = await asyncio.to_thread(
            entity_extractor.extract_entities,
            text=request.text,
            extract_relationships=request.extract_relationships,
        )

        # Build the graph in ONE transaction (#668): document node + entities +
        # relationships + MENTIONS links, with a full-replace of this document's
        # prior edges first so a re-ingest drops content no longer present. Either
        # the whole thing commits or it raises (no half-built graph, #351 spirit
        # preserved — the committed counts below are exactly what's in Neo4j).
        result = await graph_constructor.construct_graph(
            document_id=request.document_id,
            owner_id=owner_id,
            entities=extraction_result["entities"],
            relationships=extraction_result["relationships"],
            title=request.title,
            source=request.source,
            metadata=request.metadata,
            kb_id=request.kb_id,
        )
        entity_count = result["entity_count"]
        if result["mentions_count"] < entity_count:
            logger.warning(
                f"⚠️  Only linked {result['mentions_count']}/{entity_count} "
                f"entities to document '{request.document_id}'"
            )

        return KnowledgeGraphResponse(
            success=True,
            document_id=request.document_id,
            entity_count=entity_count,
            relationship_count=result["relationship_count"],
            message=f"Knowledge graph constructed with {entity_count} entities",
        )

    except Exception as e:
        logger.error(f"❌ Knowledge graph construction failed: {e}")
        raise backend_http_error(e, "Knowledge graph construction")


async def delete_document_graph_handler(
    document_id: str,
    owner_id: str,
    graph_constructor: KnowledgeGraphConstructor,
):
    """Delete a document's knowledge-graph nodes/relationships from Neo4j.

    #782: owner-scoped — deleting a document_id that exists only under another
    tenant is a no-op (``document_deleted == 0``), so a caller can't remove
    another tenant's graph by guessing/enumerating ids."""
    if graph_constructor is None:
        raise HTTPException(status_code=503, detail="graph constructor not initialized")
    try:
        counts = await graph_constructor.delete_document(document_id, owner_id)
        return {"success": True, "document_id": document_id, **counts}
    except Exception as e:
        logger.error(f"❌ Failed to delete document graph {document_id}: {e}")
        raise backend_http_error(e, "Knowledge graph deletion")


async def list_graph_documents_handler(
    owner_id: str,
    graph_constructor: KnowledgeGraphConstructor,
) -> GraphDocumentsResponse:
    """List the caller's own Document nodes so they can browse/pick one (e.g. to
    delete) without knowing its id up front. #782: owner-scoped."""
    if graph_constructor is None:
        raise HTTPException(status_code=503, detail="graph constructor not initialized")
    try:
        documents = await graph_constructor.list_documents(owner_id)
        return GraphDocumentsResponse(
            success=True, documents=documents, count=len(documents)
        )
    except Exception as e:
        logger.error(f"❌ Failed to list graph documents: {e}")
        raise backend_http_error(e, "Graph document listing")


async def get_graph_stats_handler(
    owner_id: str,
    graph_constructor: KnowledgeGraphConstructor,
) -> GraphStatsResponse:
    """Overview of the caller's knowledge graph: node/relationship/document/entity
    counts + the per-NER-label entity distribution, so a caller can confirm a
    construct-graph actually populated their graph and see what it holds. #782:
    owner-scoped — counts never include other tenants' data."""
    if graph_constructor is None:
        raise HTTPException(status_code=503, detail="graph constructor not initialized")
    try:
        stats = await graph_constructor.get_graph_statistics(owner_id)
        return GraphStatsResponse(success=True, **stats)
    except Exception as e:
        logger.error(f"❌ Failed to get graph statistics: {e}")
        raise backend_http_error(e, "Graph statistics")


async def retrieve_with_graph_handler(
    request: GraphRetrievalRequest,
    owner_id: str,
    entity_extractor: EntityExtractor,
    graph_retriever: GraphRetriever,
) -> GraphRetrievalResponse:
    """Handle graph-based retrieval requests"""
    try:
        import time

        start_time = time.time()

        # Extract entities from query (offloaded — blocking spaCy NER).
        extraction_result = await asyncio.to_thread(
            entity_extractor.extract_entities, request.query
        )

        if extraction_result["entity_count"] == 0:
            return GraphRetrievalResponse(
                success=True,
                query=request.query,
                related_entities=[],
                entity_count=0,
                retrieval_time_ms=(time.time() - start_time) * 1000,
            )

        # Search the graph by the spaCy-extracted entity names. The previous code
        # re-derived capitalized-ASCII tokens via `re.findall(r"\b[A-Z][a-z]+\b")` and
        # searched those instead — so lowercase / ALL-CAPS / Turkish/non-Latin queries
        # matched nothing even though NER had already found the entities. Use the NER
        # output we already computed (entity_count > 0 is guaranteed here).
        search_terms = list(
            dict.fromkeys(e["text"] for e in extraction_result["entities"])
        )
        logger.info(f"🔍 Searching graph for extracted entities: {search_terms}")

        # Get related entities via graph traversal for each extracted entity
        related_entities = []
        seen_entities = set()

        for term in search_terms[:5]:  # Limit to top 5 entities
            entities = await graph_retriever.find_related_entities(
                entity_name=term,
                owner_id=owner_id,
                max_depth=request.traversal_depth,
                limit=request.limit,
            )
            logger.info(f"🔍 Found {len(entities)} related entities for '{term}'")
            for e in entities:
                if e["text"] not in seen_entities:
                    related_entities.append(e)
                    seen_entities.add(e["text"])

        retrieval_time_ms = (time.time() - start_time) * 1000

        logger.info(f"🔍 Graph retrieval completed in {retrieval_time_ms:.2f}ms")

        return GraphRetrievalResponse(
            success=True,
            query=request.query,
            related_entities=related_entities,
            entity_count=len(related_entities),
            retrieval_time_ms=retrieval_time_ms,
        )

    except Exception as e:
        logger.error(f"❌ Graph retrieval failed: {e}")
        raise backend_http_error(e, "Graph retrieval")


async def get_entity_context_handler(
    request: EntityContextRequest, owner_id: str, graph_retriever: GraphRetriever
) -> EntityContextResponse:
    """Handle entity context retrieval requests (#782: owner-scoped)."""
    try:
        context_result = await graph_retriever.get_entity_context(
            entity_name=request.entity_text,
            owner_id=owner_id,
            context_window=request.context_window,
        )

        if "error" in context_result:
            raise HTTPException(status_code=404, detail=context_result["error"])

        # Honour include_neighbors (was accepted but ignored, #147): drop connected
        # entities when the caller doesn't want them.
        related = (
            context_result.get("related_entities", [])
            if request.include_neighbors
            else []
        )
        return EntityContextResponse(
            success=True,
            entity=context_result.get("entity", {}),
            related_entities=related,
            documents=context_result.get("documents", []),
            context_window=context_result.get("context_window", 3),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Entity context retrieval failed: {e}")
        raise backend_http_error(e, "Entity context retrieval")


async def graph_search_handler(
    request: GraphSearchRequest, owner_id: str, graph_retriever: GraphRetriever
) -> GraphSearchResponse:
    """Handle free-text entity search over the knowledge graph.

    Exposes GraphRetriever.graph_search, which was implemented but wired to no route
    — a ready capability for "search the graph for entities matching X" (matches on
    entity text OR label, case-insensitive). #782: owner-scoped."""
    try:
        entities = await graph_retriever.graph_search(
            request.query, owner_id=owner_id, limit=request.limit
        )
        return GraphSearchResponse(
            success=True,
            query=request.query,
            entities=entities,
            entity_count=len(entities),
        )
    except Exception as e:  # graph_search itself swallows errors → []; defensive
        logger.error(f"❌ Graph search failed: {e}")
        raise backend_http_error(e, "Graph search")


def build_graph_router(
    *,
    entity_extractor: EntityExtractor,
    graph_constructor: KnowledgeGraphConstructor,
    graph_retriever: GraphRetriever,
) -> APIRouter:
    """Assemble the Graph RAG business endpoints as an APIRouter with the service
    instances injected — same factory pattern as the other services' route modules
    (thin main + routes/). The handlers above hold the logic; this only wires them."""
    router = APIRouter()

    @router.post(
        "/v1/extract",
        response_model=EntityExtractionResponse,
        tags=["Entity Extraction"],
    )
    @router.post(
        "/extract",
        response_model=EntityExtractionResponse,
        tags=["Entity Extraction"],
        include_in_schema=False,  # deprecated unversioned alias
    )
    async def extract_entities(request: EntityExtractionRequest):
        """Extract entities and relationships from text.

        Served at both /v1/extract and the legacy /extract directly — the old
        /extract used a 301 redirect, which drops the method/body on non-GET
        clients (#147).
        """
        return await extract_entities_handler(request, entity_extractor)

    @router.post(
        "/v1/construct-graph",
        response_model=KnowledgeGraphResponse,
        tags=["Knowledge Graph"],
    )
    @router.post(
        "/construct-graph",
        response_model=KnowledgeGraphResponse,
        tags=["Knowledge Graph"],
        include_in_schema=False,  # deprecated unversioned alias
    )
    async def construct_knowledge_graph(
        request: KnowledgeGraphRequest,
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Build a knowledge graph from a document.

        Idempotent on `document_id`: the document, entity, and relationship writes all
        use Cypher MERGE, so re-POSTing the same id upserts rather than duplicating
        nodes/edges (#147).

        Served at both /v1/construct-graph and the legacy /construct-graph directly —
        the old /construct-graph used a 301 redirect, which drops the method/body on
        non-GET clients (#147).
        """
        return await construct_knowledge_graph_handler(
            request, resolve_owner_id(current_user), entity_extractor, graph_constructor
        )

    @router.delete("/v1/graph/document/{document_id}", tags=["Knowledge Graph"])
    @router.delete(
        "/graph/document/{document_id}",
        tags=["Knowledge Graph"],
        include_in_schema=False,  # deprecated unversioned alias
    )
    async def delete_document_graph(
        document_id: str,
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Delete a document's knowledge-graph nodes/relationships from Neo4j.

        Served at both /v1/graph/document/{document_id} and the legacy
        /graph/document/{document_id} directly — the old path used a 301 redirect,
        which drops the method/body on non-GET clients (#147).

        #782: scoped to the caller — deleting a document owned by another tenant
        is a no-op, never an error, and never touches their graph.
        """
        return await delete_document_graph_handler(
            document_id, resolve_owner_id(current_user), graph_constructor
        )

    @router.get(
        "/v1/graph/stats",
        response_model=GraphStatsResponse,
        tags=["Knowledge Graph"],
    )
    @router.get(
        "/graph/stats",
        response_model=GraphStatsResponse,
        tags=["Knowledge Graph"],
        include_in_schema=False,  # deprecated unversioned alias
    )
    async def get_graph_stats(
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Overview of the caller's knowledge graph (counts + entity-type
        distribution).

        Served at both /v1/graph/stats and the legacy /graph/stats. #782: now
        requires a JWT and is scoped to the caller — a global count would leak the
        existence/volume of other tenants' data, so per-tenant scoping requires
        knowing the tenant.
        """
        return await get_graph_stats_handler(
            resolve_owner_id(current_user), graph_constructor
        )

    @router.get(
        "/v1/graph/documents",
        response_model=GraphDocumentsResponse,
        tags=["Knowledge Graph"],
    )
    @router.get(
        "/graph/documents",
        response_model=GraphDocumentsResponse,
        tags=["Knowledge Graph"],
        include_in_schema=False,  # deprecated unversioned alias
    )
    async def list_graph_documents(
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """List the caller's own Document nodes (browse what they've built). #782:
        now requires a JWT and is scoped to the caller — this endpoint used to let
        any logged-in user enumerate every tenant's document titles/sources and
        then delete them by id."""
        return await list_graph_documents_handler(
            resolve_owner_id(current_user), graph_constructor
        )

    @router.post(
        "/v1/retrieve",
        response_model=GraphRetrievalResponse,
        tags=["Graph Retrieval"],
    )
    @router.post(
        "/retrieve",
        response_model=GraphRetrievalResponse,
        tags=["Graph Retrieval"],
        include_in_schema=False,  # deprecated unversioned alias
    )
    async def retrieve_with_graph(
        request: GraphRetrievalRequest,
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Graph-based retrieval for RAG enhancement.

        Served at both /v1/retrieve and the legacy /retrieve directly — the old
        /retrieve used a 301 redirect, which drops the method/body on non-GET
        clients (#147).

        #782: scoped to the caller — traversal only ever visits the caller's own
        entities, so retrieval can't surface another tenant's graph.
        """
        return await retrieve_with_graph_handler(
            request, resolve_owner_id(current_user), entity_extractor, graph_retriever
        )

    @router.post(
        "/v1/entity-context",
        response_model=EntityContextResponse,
        tags=["Entity Context"],
    )
    @router.post(
        "/entity-context",
        response_model=EntityContextResponse,
        tags=["Entity Context"],
        include_in_schema=False,  # deprecated unversioned alias
    )
    async def get_entity_context(
        request: EntityContextRequest,
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Get detailed context for an entity.

        Served at both /v1/entity-context and the legacy /entity-context directly —
        the old /entity-context used a 301 redirect, which drops the method/body on
        non-GET clients (#147).

        #782: scoped to the caller — resolves the entity only within their graph.
        """
        return await get_entity_context_handler(
            request, resolve_owner_id(current_user), graph_retriever
        )

    @router.post(
        "/v1/graph/search",
        response_model=GraphSearchResponse,
        tags=["Knowledge Graph"],
    )
    @router.post(
        "/graph/search",
        response_model=GraphSearchResponse,
        tags=["Knowledge Graph"],
        include_in_schema=False,  # deprecated unversioned alias
    )
    async def graph_search(
        request: GraphSearchRequest,
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Free-text search the knowledge graph for entities whose text or label
        matches the query (case-insensitive). Exposes the previously-unwired
        GraphRetriever.graph_search capability. #782: scoped to the caller."""
        return await graph_search_handler(
            request, resolve_owner_id(current_user), graph_retriever
        )

    return router
