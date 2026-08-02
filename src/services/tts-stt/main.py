"""
Minder TTS/STT Service - Minimal Working Version
Simple text-to-speech and speech-to-text functionality
"""

import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

# Shared library (needs src/ on the path) — must happen before routes.stt /
# routes.tts below, since those import from `shared.*` at their own top level.
sys.path.insert(0, "/app/src")

from core.stt_engine import STT_AVAILABLE  # noqa: E402
from core.tts_engine import TTS_AVAILABLE  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from routes.stt import router as stt_router  # noqa: E402
from routes.tts import router as tts_router  # noqa: E402

from shared.health import DependencyCheck, evaluate_dependencies  # noqa: E402
from shared.log import setup_logging  # noqa: E402
from shared.metrics import setup_metrics  # noqa: E402

logger = setup_logging("tts-stt")


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

# Prometheus metrics: request-tracking middleware + /metrics endpoint
setup_metrics(app)

app.include_router(tts_router)
app.include_router(stt_router)


# ============================================================================
# Health & Metrics
# ============================================================================


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check — degraded if one engine is unavailable, 503 if BOTH are.

    tts-stt has no remote backend; its "dependencies" are the two offline engines.
    """

    def _tts():
        if not TTS_AVAILABLE:
            raise RuntimeError("TTS engine unavailable")

    def _stt():
        if not STT_AVAILABLE:
            raise RuntimeError("STT engine unavailable")

    def _any_engine():
        if not (TTS_AVAILABLE or STT_AVAILABLE):
            raise RuntimeError("no speech engine available")

    status, code, checks = await evaluate_dependencies(
        [
            DependencyCheck("tts_engine", _tts, critical=False),
            DependencyCheck("stt_engine", _stt, critical=False),
            DependencyCheck("engines", _any_engine, critical=True),
        ]
    )
    return JSONResponse(
        status_code=code,
        content={
            "service": "tts-stt",
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": app.version,
            "environment": os.getenv("ENVIRONMENT", "development"),
            "tts_available": TTS_AVAILABLE,
            "stt_available": STT_AVAILABLE,
            "checks": checks,
        },
    )


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
