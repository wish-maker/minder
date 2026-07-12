"""Pydantic request/response models for the TTS/STT service."""

from pydantic import BaseModel

from config import DEFAULT_TTS_LANG


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
