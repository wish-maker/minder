"""
API Routes for Graph RAG Service

All FastAPI endpoints for entity extraction, graph construction, and retrieval.
"""
import logging
from typing import Dict

from fastapi import HTTPException

from models.schemas import (
    EntityContextRequest,
    EntityContextResponse,
    EntityExtractionRequest,
    EntityExtractionResponse,
    GraphRetrievalRequest,
    GraphRetrievalResponse,
    KnowledgeGraphRequest,
    KnowledgeGraphResponse,
)

from core.entity_extractor import EntityExtractor
from core.graph_constructor import KnowledgeGraphConstructor
from core.graph_retriever import GraphRetriever

logger = logging.getLogger(__name__)


async def extract_entities_handler(
    request: EntityExtractionRequest,
    entity_extractor: EntityExtractor
) -> EntityExtractionResponse:
    """Handle entity extraction requests"""
    try:
        result = entity_extractor.extract_entities(
            text=request.text,
            extract_relationships=request.extract_relationships
        )

        return EntityExtractionResponse(
            success=True,
            entities=result["entities"],
            relationships=result["relationships"],
            entity_count=result["entity_count"],
            relationship_count=result["relationship_count"]
        )

    except Exception as e:
        logger.error(f"❌ Entity extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def construct_knowledge_graph_handler(
    request: KnowledgeGraphRequest,
    entity_extractor: EntityExtractor,
    graph_constructor: KnowledgeGraphConstructor
) -> KnowledgeGraphResponse:
    """Handle knowledge graph construction requests"""
    try:
        # Extract entities first
        extraction_result = entity_extractor.extract_entities(
            text=request.text,
            extract_relationships=True
        )

        # Create document node
        await graph_constructor.create_document_node(
            document_id=request.document_id,
            title=request.title,
            source=request.source,
            metadata=request.metadata
        )

        # Create entity nodes
        entity_ids = await graph_constructor.create_entity_nodes(
            document_id=request.document_id,
            entities=extraction_result["entities"]
        )

        # Create relationship nodes
        relationship_count = await graph_constructor.create_relationship_nodes(
            document_id=request.document_id,
            relationships=extraction_result["relationships"]
        )

        # Link document to entities
        await graph_constructor.link_document_to_entities(
            document_id=request.document_id,
            entity_ids=entity_ids
        )

        return KnowledgeGraphResponse(
            success=True,
            document_id=request.document_id,
            entity_count=len(extraction_result["entities"]),
            relationship_count=relationship_count,
            message=f"Knowledge graph constructed with {len(extraction_result['entities'])} entities"
        )

    except Exception as e:
        logger.error(f"❌ Knowledge graph construction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def retrieve_with_graph_handler(
    request: GraphRetrievalRequest,
    entity_extractor: EntityExtractor,
    graph_retriever: GraphRetriever
) -> GraphRetrievalResponse:
    """Handle graph-based retrieval requests"""
    try:
        import time
        start_time = time.time()

        # Extract entities from query
        extraction_result = entity_extractor.extract_entities(request.query)

        if extraction_result["entity_count"] == 0:
            return GraphRetrievalResponse(
                success=True,
                query=request.query,
                related_entities=[],
                entity_count=0,
                retrieval_time_ms=(time.time() - start_time) * 1000
            )

        # DEBUG: Log extracted entities
        extracted_entity_names = [e["text"] for e in extraction_result["entities"]]
        logger.info(f"🔍 Extracted entities from query: {extracted_entity_names}")

        # Split query into tokens and search for each significant token
        # This handles cases like "Bill Gates Microsoft" where spaCy extracts multi-word entities
        import re
        tokens = re.findall(r'\b[A-Z][a-z]+\b', request.query)  # Extract capitalized words
        tokens = list(set(tokens))  # Remove duplicates

        if len(tokens) == 0:
            logger.warning("⚠️ No significant tokens found in query")
            return GraphRetrievalResponse(
                success=True,
                query=request.query,
                related_entities=[],
                entity_count=0,
                retrieval_time_ms=(time.time() - start_time) * 1000
            )

        logger.info(f"🔍 Split query into tokens: {tokens}")

        # Get related entities via graph traversal for each token
        related_entities = []
        seen_entities = set()

        for token in tokens[:5]:  # Limit to top 5 tokens
            logger.info(f"🔍 Searching for related entities to: '{token}'")
            entities = await graph_retriever.find_related_entities(
                entity_name=token,
                max_depth=request.traversal_depth,
                limit=request.limit
            )
            logger.info(f"🔍 Found {len(entities)} related entities for '{token}'")
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
            retrieval_time_ms=retrieval_time_ms
        )

    except Exception as e:
        logger.error(f"❌ Graph retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_entity_context_handler(
    request: EntityContextRequest,
    graph_retriever: GraphRetriever
) -> EntityContextResponse:
    """Handle entity context retrieval requests"""
    try:
        context_result = await graph_retriever.get_entity_context(
            entity_text=request.entity_text,
            include_neighbors=request.include_neighbors
        )

        if "error" in context_result:
            raise HTTPException(status_code=404, detail=context_result["error"])

        return EntityContextResponse(
            success=True,
            entity=context_result.get("entity", {}),
            related_entities=context_result.get("related_entities", []),
            documents=context_result.get("documents", []),
            context_window=context_result.get("context_window", 3)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Entity context retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))