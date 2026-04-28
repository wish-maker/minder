"""
Minder AI Services (Unified)
Combines RAG Pipeline, Model Management, and TTS/STT functionality
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events"""
    logger.info(f"Starting {settings.api_title} v{settings.api_version}")
    logger.info(f"Environment: {settings.environment}")
    logger.info("Unified AI Services: RAG + Model Management + TTS/STT")
    yield
    logger.info("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="Unified AI Services combining RAG, Model Management, and TTS/STT",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.api_title,
        "version": settings.api_version,
        "environment": settings.environment,
        "unified_services": [
            "RAG Pipeline",
            "Model Management",
            "TTS/STT"
        ],
        "endpoints": {
            "rag": "/rag/*",
            "models": "/models/*",
            "tts": "/tts/*",
            "health": "/health",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """Health check"""
    return {
        "service": "ai-services-unified",
        "status": "healthy",
        "timestamp": logging.getLogger(__name__).name,
        "version": settings.api_version,
        "unified_components": {
            "rag": "available",
            "model_management": "available",
            "tts_stt": "available"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8004,
        reload=settings.environment == "development"
    )
