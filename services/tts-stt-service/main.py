"""
Minder TTS/STT Service - Minimal Working Version
Simple text-to-speech and speech-to-text functionality
"""

import logging
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException
from fastapi import Response as FastAPIResponse
from fastapi import UploadFile
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

# TTS/STT libraries
try:
    from gtts import gTTS

    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    logging.warning("gTTS not installed")

try:
    import speech_recognition as sr

    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False
    logging.warning("SpeechRecognition not installed")

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_TTS_LANG = "tr"
DEFAULT_STT_LANG = "tr-TR"

SUPPORTED_LANGUAGES = {
    "tr": "Turkish",
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
}

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Minder TTS/STT Service",
    description="Text-to-Speech and Speech-to-Text service",
    version="1.0.0",
)

# ============================================================================
# Prometheus Metrics
# ============================================================================

tts_requests_total = Counter("tts_requests_total", "Total TTS requests", ["language", "status"])

stt_requests_total = Counter("stt_requests_total", "Total STT requests", ["language", "status"])

# ============================================================================
# Pydantic Models
# ============================================================================


class TTSRequest(BaseModel):
    """Text-to-Speech request"""

    text: str
    language: str = DEFAULT_TTS_LANG
    slow: bool = False


class STTResponse(BaseModel):
    """STT response"""

    text: str
    language: str
    confidence: float


# ============================================================================
# TTS Endpoints
# ============================================================================


@app.post("/tts", tags=["TTS"])
async def text_to_speech(request: TTSRequest):
    """Convert text to speech (MP3 format)"""
    if not TTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="TTS not available")

    # Validate language
    if request.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {request.language}")

    try:
        tts_requests_total.labels(language=request.language, status="success").inc()

        # Generate speech using gTTS
        tts = gTTS(text=request.text, lang=request.language, slow=request.slow)

        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
            tts.save(temp_file.name)
            temp_path = temp_file.name

        # Read audio file
        with open(temp_path, "rb") as audio_file:
            audio_bytes = audio_file.read()

        # Clean up temp file
        os.unlink(temp_path)

        # Estimate duration
        duration = len(request.text) / 15  # Rough estimate

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"attachment; filename=speech.mp3",
                "X-Duration": str(duration),
                "X-Language": request.language,
            },
        )

    except Exception as e:
        tts_requests_total.labels(language=request.language, status="error").inc()
        logger.error(f"❌ TTS failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tts/languages", tags=["TTS"])
async def get_tts_languages():
    """Get supported languages"""
    return {
        "languages": SUPPORTED_LANGUAGES,
        "default": DEFAULT_TTS_LANG,
        "available": TTS_AVAILABLE,
    }


# ============================================================================
# STT Endpoints
# ============================================================================


@app.post("/stt", response_model=STTResponse, tags=["STT"])
async def speech_to_text(file: UploadFile = File(...), language: str = DEFAULT_STT_LANG):
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

        # Transcribe
        recognizer = sr.Recognizer()

        with sr.AudioFile(temp_path) as source:
            audio_data = recognizer.record(source)

            try:
                # Try Google Speech Recognition first
                text = recognizer.recognize_google(audio_data, language=language)
                confidence = 0.9
            except sr.UnknownValueError:
                text = ""
                confidence = 0.0
            except sr.RequestError as e:
                logger.warning(f"Speech recognition API error: {e}")
                text = f"[API Error: {str(e)}]"
                confidence = 0.0

        # Clean up temp file
        os.unlink(temp_path)

        stt_requests_total.labels(language=language, status="success").inc()

        return STTResponse(text=text, language=language, confidence=confidence)

    except Exception as e:
        stt_requests_total.labels(language=language, status="error").inc()
        logger.error(f"❌ STT failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stt/languages", tags=["STT"])
async def get_stt_languages():
    """Get supported languages"""
    return {
        "languages": SUPPORTED_LANGUAGES,
        "auto_detect": True,
        "default": DEFAULT_STT_LANG,
        "available": STT_AVAILABLE,
    }


# ============================================================================
# Health & Metrics
# ============================================================================


@app.get("/health", tags=["Health"])
async def health_check():
    """Service health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
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


# ============================================================================
# Startup Event
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("🚀 Starting TTS/STT service...")
    logger.info(f"TTS Available: {TTS_AVAILABLE}")
    logger.info(f"STT Available: {STT_AVAILABLE}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)
