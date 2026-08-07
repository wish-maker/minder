"""Text-to-Speech routes (gTTS). Engine logic lives in core/tts_engine."""

import asyncio
import logging

from core.tts_engine import TTS_AVAILABLE, synthesize
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from models import TTSRequest
from prometheus_client import Counter

from config import SUPPORTED_LANGUAGES, settings
from shared.errors import backend_http_error

logger = logging.getLogger("minder.tts-stt")

tts_requests_total = Counter(
    "tts_requests_total", "Total TTS requests", ["language", "status"]
)

router = APIRouter()


@router.post(
    "/v1/tts",
    tags=["TTS"],
    responses={
        200: {
            "content": {"audio/wav": {}, "audio/mpeg": {}},
            "description": (
                "Synthesised audio — WAV (Piper, offline) or MP3 (gTTS fallback). "
                "The engine/format is reported in the X-Language header and the "
                "Content-Type. Binary body, so there is no JSON response_model (#147/C9)."
            ),
        }
    },
)
@router.post(
    "/tts",
    tags=["TTS"],
    include_in_schema=False,  # deprecated unversioned alias
    responses={
        200: {
            "content": {"audio/wav": {}, "audio/mpeg": {}},
            "description": (
                "Synthesised audio — WAV (Piper, offline) or MP3 (gTTS fallback). "
                "The engine/format is reported in the X-Language header and the "
                "Content-Type. Binary body, so there is no JSON response_model (#147/C9)."
            ),
        }
    },
)
async def text_to_speech(request: TTSRequest):
    """Convert text to speech (Piper → WAV offline, or gTTS → MP3 fallback).

    Served at both /v1/tts and the legacy /tts directly — the old /tts
    used a 301 redirect, which drops the method/body on non-GET clients (#147).
    """
    if not TTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="TTS not available")

    # Language is validated by TTSRequest (422 with the valid set) before we get here.
    try:
        # Synthesis + file I/O are blocking; run off the event loop so concurrent
        # requests aren't stalled. media_type/ext depend on the engine (Piper=WAV,
        # gTTS=MP3), chosen inside synthesize().
        audio_bytes, media_type, ext = await asyncio.to_thread(
            synthesize, request.text, request.language, request.slow
        )

        # Count success only after synthesis actually succeeds — otherwise a failure
        # increments both success (here) and error (except) and double-counts.
        tts_requests_total.labels(language=request.language, status="success").inc()

        # Estimate duration
        duration = len(request.text) / 15  # Rough estimate

        return Response(
            content=audio_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename=speech.{ext}",
                "X-Duration": str(duration),
                "X-Language": request.language,
            },
        )

    except Exception as e:
        tts_requests_total.labels(language=request.language, status="error").inc()
        logger.error(f"❌ TTS failed: {e}")
        raise backend_http_error(e, "Text-to-speech")


@router.get("/v1/tts/languages", tags=["TTS"])
@router.get(
    "/tts/languages", tags=["TTS"], include_in_schema=False
)  # deprecated unversioned alias
async def get_tts_languages():
    """Get supported languages.

    Served at both /v1/tts/languages and the legacy /tts/languages directly — the old
    /tts/languages used a 301 redirect, which drops the method/body on non-GET clients (#147).
    """
    return {
        "languages": SUPPORTED_LANGUAGES,
        "default": settings.DEFAULT_TTS_LANG,
        "available": TTS_AVAILABLE,
    }
