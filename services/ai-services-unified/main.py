"""
Minder AI Services (Unified)
Combines RAG Pipeline, Model Management, and TTS/STT functionality
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

# Import version variables
OLLAMA_VERSION = "0.5.7"
QDRANT_VERSION = "1.12.0"
NEO4J_VERSION = "5.26.0"
REDIS_VERSION = "5.4.2"
FASTAPI_VERSION = "0.115.0"
PYDANTIC_VERSION = "2.10.0"
HTTPX_VERSION = "0.28.0"
ASYNCPG_VERSION = "0.30.0"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events"""
    logger.info(f"Starting Unified AI Services v{OLLAMA_VERSION}")
    logger.info(f"Environment: development")
    logger.info(f"Components:")
    logger.info(f"  - Ollama v{OLLAMA_VERSION}")
    logger.info(f"  - Qdrant v{QDRANT_VERSION}")
    logger.info(f"  - Neo4j v{NEO4J_VERSION}")
    logger.info(f"  - Redis v{REDIS_VERSION}")
    logger.info(f"  - FastAPI v{FASTAPI_VERSION}")
    logger.info(f"  - Pydantic v{PYDANTIC_VERSION}")
    logger.info(f"  - HTTPX v{HTTPX_VERSION}")
    logger.info(f"  - AsyncPG v{ASYNCPG_VERSION}")
    yield
    logger.info("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Minder AI Services",
    description="Unified AI Services combining RAG, Model Management, and TTS/STT",
    version="2.1.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check"""
    return {
        "service": "ai-services-unified",
        "status": "healthy",
        "timestamp": logging.getLogger(__name__).name,
        "version": "2.1.0",
        "component_versions": {
            "ollama": OLLAMA_VERSION,
            "qdrant": QDRANT_VERSION,
            "neo4j": NEO4J_VERSION,
            "redis": REDIS_VERSION,
            "fastapi": FASTAPI_VERSION,
            "pydantic": PYDANTIC_VERSION,
            "httpx": HTTPX_VERSION,
            "asyncpg": ASYNCPG_VERSION
        }
    }


@app.get("/version")
async def get_version():
    """Return current version and component versions"""
    return {
        "api_version": "v2.1.0",
        "service": "ai-services-unified",
        "core_version": "2.1.0",
        "component_versions": {
            "ollama": OLLAMA_VERSION,
            "qdrant": QDRANT_VERSION,
            "neo4j": NEO4J_VERSION,
            "redis": REDIS_VERSION,
            "fastapi": FASTAPI_VERSION,
            "pydantic": PYDANTIC_VERSION,
            "httpx": HTTPX_VERSION,
            "asyncpg": ASYNCPG_VERSION
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8004,
        reload=True
    )
