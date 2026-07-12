"""
Minder Graph RAG Service - Modular Architecture

Entity extraction and knowledge graph construction for RAG enhancement.
This refactored version uses clean separation of concerns.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime

# Import core modules
from core.entity_extractor import EntityExtractor
from core.graph_constructor import KnowledgeGraphConstructor
from core.graph_retriever import GraphRetriever
from fastapi import FastAPI

# Import request/response models
from models.schemas import (
    EntityContextRequest,
    EntityExtractionRequest,
    GraphRetrievalRequest,
    KnowledgeGraphRequest,
)

# Import API routes
from routes.api import (
    construct_knowledge_graph_handler,
    extract_entities_handler,
    get_entity_context_handler,
    retrieve_with_graph_handler,
)

# Shared library (needs src/ on the path)
sys.path.insert(0, "/app/src")
from shared.metrics import setup_metrics  # noqa: E402

# Configure logging
logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
logger = logging.getLogger("minder.graph-rag")

# ============================================================================
# Configuration
# ============================================================================

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")

# NEO4J_AUTH is required — fail-fast if not set
NEO4J_AUTH = os.getenv("NEO4J_AUTH")
if not NEO4J_AUTH:
    raise ValueError(
        "NEO4J_AUTH must be set via environment variable (format: neo4j/password)"
    )

# Parse NEO4J_AUTH to extract password (format: "user/password")
if "/" in NEO4J_AUTH:
    NEO4J_USER, NEO4J_PASSWORD = NEO4J_AUTH.split("/", 1)
else:
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

SPACY_MODEL = os.getenv("SPACY_MODEL", "en_core_web_sm")

# ============================================================================
# Global Service Instances
# ============================================================================

entity_extractor: EntityExtractor = None
graph_constructor: KnowledgeGraphConstructor = None
graph_retriever: GraphRetriever = None

# ============================================================================
# Startup/Shutdown Events
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize service instances on startup; close Neo4j drivers on shutdown."""
    global entity_extractor, graph_constructor, graph_retriever

    logger.info("🚀 Starting Graph RAG Service...")

    # Initialize entity extractor
    entity_extractor = EntityExtractor()

    # Initialize graph constructor
    graph_constructor = KnowledgeGraphConstructor(
        uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD
    )

    # Initialize graph retriever
    graph_retriever = GraphRetriever(
        uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD
    )

    logger.info("✅ Graph RAG Service initialized")

    yield

    if graph_constructor:
        await graph_constructor.close()
    if graph_retriever:
        await graph_retriever.close()
    logger.info("🛑 Graph RAG Service shut down")


app = FastAPI(
    title="Minder Graph RAG",
    description="Entity extraction and knowledge graph construction for RAG",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Prometheus metrics: request-tracking middleware + /metrics endpoint
setup_metrics(app)


# ============================================================================
# Health Check Endpoints
# ============================================================================


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint

    Returns service status and component availability
    """
    checks = {
        "entity_extractor": "initialized" if entity_extractor else "not_initialized",
        "graph_constructor": "initialized" if graph_constructor else "not_initialized",
        "graph_retriever": "initialized" if graph_retriever else "not_initialized",
        "neo4j": NEO4J_URI,
        "spacy_model": SPACY_MODEL,
    }

    overall_status = "healthy"
    if not all([entity_extractor, graph_constructor, graph_retriever]):
        overall_status = "degraded"

    return {
        "service": "graph-rag",
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "version": app.version,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "checks": checks,
    }


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "service": "Minder Graph RAG Service",
        "version": "1.0.0",
        "status": "operational",
        "capabilities": [
            "Entity extraction (spaCy)",
            "Knowledge graph construction",
            "Graph-based retrieval",
            "Entity context enhancement",
        ],
        "docs": "/docs",
        "health": "/health",
    }


@app.post("/extract", tags=["Entity Extraction"])
async def extract_entities(request: EntityExtractionRequest):
    """Extract entities and relationships from text"""
    return await extract_entities_handler(request, entity_extractor)


@app.post("/construct-graph", tags=["Knowledge Graph"])
async def construct_knowledge_graph(request: KnowledgeGraphRequest):
    """Build knowledge graph from document"""
    return await construct_knowledge_graph_handler(
        request, entity_extractor, graph_constructor
    )


@app.post("/retrieve", tags=["Graph Retrieval"])
async def retrieve_with_graph(request: GraphRetrievalRequest):
    """Graph-based retrieval for RAG enhancement"""
    return await retrieve_with_graph_handler(request, entity_extractor, graph_retriever)


@app.post("/entity-context", tags=["Entity Context"])
async def get_entity_context(request: EntityContextRequest):
    """Get detailed context for an entity"""
    return await get_entity_context_handler(request, graph_retriever)


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8008)
