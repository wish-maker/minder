"""Text-to-Speech routes (gTTS). Engine logic lives in core/tts_engine."""

import asyncio
import logging

from core.tts_engine import TTS_AVAILABLE, synthesize
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from models import TTSRequest
from prometheus_client import Counter

from config import DEFAULT_TTS_LANG, SUPPORTED_LANGUAGES

logger = logging.getLogger("minder.tts-stt")

tts_requests_total = Counter(
    "tts_requests_total", "Total TTS requests", ["language", "status"]
)

router = APIRouter()


@router.post("/tts", tags=["TTS"])
async def text_to_speech(request: TTSRequest):
    """Convert text to speech (MP3 format)"""
    if not TTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="TTS not available")

    # Validate language
    if request.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400, detail=f"Unsupported language: {request.language}"
        )

    try:
        tts_requests_total.labels(language=request.language, status="success").inc()

        # Synthesis + file I/O are blocking; run off the event loop so concurrent
        # requests aren't stalled.
        audio_bytes = await asyncio.to_thread(
            synthesize, request.text, request.language, request.slow
        )

        # Estimate duration
        duration = len(request.text) / 15  # Rough estimate

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "attachment; filename=speech.mp3",
                "X-Duration": str(duration),
                "X-Language": request.language,
            },
        )

    except Exception as e:
        tts_requests_total.labels(language=request.language, status="error").inc()
        logger.error(f"❌ TTS failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tts/languages", tags=["TTS"])
async def get_tts_languages():
    """Get supported languages"""
    return {
        "languages": SUPPORTED_LANGUAGES,
        "default": DEFAULT_TTS_LANG,
        "available": TTS_AVAILABLE,
    }
