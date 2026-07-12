"""Speech-to-Text routes (SpeechRecognition)."""

import asyncio
import logging
import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from models import STTResponse
from prometheus_client import Counter

from config import DEFAULT_STT_LANG, SUPPORTED_LANGUAGES

logger = logging.getLogger("minder.tts-stt")

# STT library
try:
    import speech_recognition as sr

    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False
    logging.warning("SpeechRecognition not installed")

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
        # Read audio file
        audio_bytes = await file.read()

        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name

        # Recording + Google recognition are blocking (CPU + network); run them
        # off the event loop so a single transcription can't stall the service.
        def _transcribe() -> tuple[str, float]:
            recognizer = sr.Recognizer()
            try:
                with sr.AudioFile(temp_path) as source:
                    audio_data = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio_data, language=language)
                    return text, 0.9
                except sr.UnknownValueError:
                    return "", 0.0
                except sr.RequestError as e:
                    logger.warning(f"Speech recognition API error: {e}")
                    return f"[API Error: {str(e)}]", 0.0
            finally:
                os.unlink(temp_path)

        text, confidence = await asyncio.to_thread(_transcribe)

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
