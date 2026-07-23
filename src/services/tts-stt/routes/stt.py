"""Speech-to-Text routes (SpeechRecognition). Engine logic lives in core/stt_engine."""

import asyncio
import logging

from core.stt_engine import STT_AVAILABLE, transcribe
from fastapi import APIRouter, File, HTTPException, UploadFile
from models import STTResponse
from prometheus_client import Counter

from config import DEFAULT_STT_LANG, SUPPORTED_LANGUAGES

logger = logging.getLogger("minder.tts-stt")

stt_requests_total = Counter(
    "stt_requests_total", "Total STT requests", ["language", "status"]
)

router = APIRouter()


@router.post("/stt", response_model=STTResponse, tags=["STT"])
async def speech_to_text(
    file: UploadFile = File(...), language: str = DEFAULT_STT_LANG
):
    """Convert speech to text"""
    if not STT_AVAILABLE:
        raise HTTPException(status_code=503, detail="STT not available")

    try:
        audio_bytes = await file.read()

        # Transcription is blocking (CPU + network); run it off the event loop so a
        # single request can't stall the service.
        text, confidence = await asyncio.to_thread(transcribe, audio_bytes, language)

        stt_requests_total.labels(language=language, status="success").inc()

        return STTResponse(text=text, language=language, confidence=confidence)

    except Exception as e:
        stt_requests_total.labels(language=language, status="error").inc()
        logger.error(f"❌ STT failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stt/languages", tags=["STT"])
async def get_stt_languages():
    """Get supported languages"""
    return {
        "languages": SUPPORTED_LANGUAGES,
        "auto_detect": True,
        "default": DEFAULT_STT_LANG,
        "available": STT_AVAILABLE,
    }
