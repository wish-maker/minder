"""Minder Graph RAG Service — entity extraction + knowledge-graph construction.

Thin app wiring: create the service instances, mount the business endpoints from
routes/api.py (APIRouter), keep health + root here. Domain logic lives in core/,
env config in config.py (service-structure standard: thin main + routes/ + core/).
"""

import sys
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI

from config import NEO4J_PASSWORD, NEO4J_USER, settings

# Shared library (needs src/ on the path); core/ + routes/ are service-local.
sys.path.insert(0, "/app/src")
from core.entity_extractor import EntityExtractor  # noqa: E402
from core.graph_constructor import KnowledgeGraphConstructor  # noqa: E402
from core.graph_retriever import GraphRetriever  # noqa: E402
from routes.api import build_graph_router  # noqa: E402

from shared.log import setup_logging  # noqa: E402
from shared.metrics import setup_metrics  # noqa: E402

logger = setup_logging("graph-rag", level=settings.LOG_LEVEL)

# Service instances — the Neo4j driver is created lazily (connects on first query)
# and the spaCy model loads here; created at module scope so the routes bind to them.
entity_extractor = EntityExtractor(settings.SPACY_MODEL)
graph_constructor = KnowledgeGraphConstructor(
    uri=settings.NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD
)
graph_retriever = GraphRetriever(
    uri=settings.NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log startup; close the Neo4j drivers on shutdown."""
    logger.info("🚀 Graph RAG Service initialized")
    yield
    await graph_constructor.close()
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

# Prometheus metrics: request-tracking middleware + /metrics endpoint.
setup_metrics(app)

# Business endpoints (extract / construct-graph / retrieve / entity-context / delete).
app.include_router(
    build_graph_router(
        entity_extractor=entity_extractor,
        graph_constructor=graph_constructor,
        graph_retriever=graph_retriever,
    )
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check — service status + component availability."""
    checks = {
        "entity_extractor": "initialized" if entity_extractor else "not_initialized",
        "graph_constructor": "initialized" if graph_constructor else "not_initialized",
        "graph_retriever": "initialized" if graph_retriever else "not_initialized",
        "neo4j": settings.NEO4J_URI,
        "spacy_model": settings.SPACY_MODEL,
    }
    overall_status = "healthy"
    if not all([entity_extractor, graph_constructor, graph_retriever]):
        overall_status = "degraded"
    return {
        "service": "graph-rag",
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "version": app.version,
        "environment": settings.ENVIRONMENT,
        "checks": checks,
    }


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8008)
