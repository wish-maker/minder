"""Pydantic request/response models for the TTS/STT service."""

from pydantic import BaseModel, field_validator

from config import DEFAULT_TTS_LANG, SUPPORTED_LANGUAGES


class TTSRequest(BaseModel):
    """Text-to-Speech request"""

    text: str
    language: str = DEFAULT_TTS_LANG
    slow: bool = False

    @field_validator("language")
    @classmethod
    def _validate_language(cls, v: str) -> str:
        # Reject an unsupported language with a 422 (listing valid codes) at parse time
        # instead of the route's ad-hoc 400 — and STT now mirrors this (#143).
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"unsupported language '{v}'; valid values: "
                f"{sorted(SUPPORTED_LANGUAGES)}"
            )
        return v


class STTResponse(BaseModel):
    """STT response"""

    text: str
    language: str
    confidence: float
