"""
Minder TTS/STT Service - Minimal Working Version
Simple text-to-speech and speech-to-text functionality
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import Response as FastAPIResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from routes.stt import STT_AVAILABLE
from routes.stt import router as stt_router
from routes.tts import TTS_AVAILABLE
from routes.tts import router as tts_router

logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
logger = logging.getLogger("minder.tts-stt")


# ============================================================================
# FastAPI App
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle for the TTS/STT service."""
    logger.info("🚀 Starting TTS/STT service...")
    logger.info(f"TTS Available: {TTS_AVAILABLE}")
    logger.info(f"STT Available: {STT_AVAILABLE}")
    yield


app = FastAPI(
    title="Minder TTS/STT",
    description="Text-to-Speech and Speech-to-Text service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(tts_router)
app.include_router(stt_router)


# ============================================================================
# Health & Metrics
# ============================================================================


@app.get("/health", tags=["Health"])
async def health_check():
    """Service health check"""
    return {
        "service": "tts-stt",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": app.version,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "tts_available": TTS_AVAILABLE,
        "stt_available": STT_AVAILABLE,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return FastAPIResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "name": "Minder TTS/STT Service",
        "version": "1.0.0",
        "status": "operational",
        "tts_available": TTS_AVAILABLE,
        "stt_available": STT_AVAILABLE,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)  # nosec B104
