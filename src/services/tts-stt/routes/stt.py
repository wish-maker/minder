"""Speech-to-Text routes (SpeechRecognition). Engine logic lives in core/stt_engine."""

import asyncio
import logging

from core.stt_engine import STT_AVAILABLE, transcribe
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from models import STTResponse
from prometheus_client import Counter

from config import SUPPORTED_STT_LANGUAGES, settings
from shared.errors import backend_http_error

logger = logging.getLogger("minder.tts-stt")

stt_requests_total = Counter(
    "stt_requests_total", "Total STT requests", ["language", "status"]
)

router = APIRouter()


@router.post("/v1/stt", response_model=STTResponse, tags=["STT"])
@router.post(
    "/stt",
    response_model=STTResponse,
    tags=["STT"],
    include_in_schema=False,  # deprecated unversioned alias
)
async def speech_to_text(
    file: UploadFile = File(...), language: str = Form(settings.DEFAULT_STT_LANG)
):
    """Convert speech to text.

    Served at both /v1/stt and the legacy /stt directly — the old /stt
    used a 301 redirect, which drops the method/body on non-GET clients (#147).
    """
    if not STT_AVAILABLE:
        raise HTTPException(status_code=503, detail="STT not available")

    # Mirror TTS's language validation — STT previously accepted any string (#143).
    # Validated against SUPPORTED_STT_LANGUAGES (BCP-47, e.g. "tr-TR"), NOT
    # TTS's bare-code SUPPORTED_LANGUAGES ("tr") -- recognize_google() needs
    # the locale-qualified form; validating against the wrong set used to
    # reject DEFAULT_STT_LANG itself.
    if language not in SUPPORTED_STT_LANGUAGES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"unsupported language '{language}'; valid values: "
                f"{sorted(SUPPORTED_STT_LANGUAGES)}"
            ),
        )

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
        raise backend_http_error(e, "Speech-to-text")


@router.get("/v1/stt/languages", tags=["STT"])
@router.get(
    "/stt/languages", tags=["STT"], include_in_schema=False
)  # deprecated unversioned alias
async def get_stt_languages():
    """Get supported languages.

    Served at both /v1/stt/languages and the legacy /stt/languages directly — the old
    /stt/languages used a 301 redirect, which drops the method/body on non-GET clients (#147).
    """
    return {
        "languages": SUPPORTED_STT_LANGUAGES,
        "auto_detect": True,
        "default": settings.DEFAULT_STT_LANG,
        "available": STT_AVAILABLE,
    }
