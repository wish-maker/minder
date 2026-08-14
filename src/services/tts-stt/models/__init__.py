"""Pydantic request/response models for the TTS/STT service."""

from pydantic import BaseModel, Field, field_validator

from config import SUPPORTED_LANGUAGES, settings


class TTSRequest(BaseModel):
    """Text-to-Speech request"""

    # min_length=1 so empty text is a clean 422 at the edge instead of a 500 from
    # failing deep in the Piper/gTTS engine with nothing to synthesize (#534) —
    # matches the language field's edge validation below.
    text: str = Field(min_length=1)
    language: str = settings.DEFAULT_TTS_LANG
    slow: bool = False
    # Which Piper voice to use for `language` (see config.PIPER_VOICES), e.g.
    # "male"/"female"/"default" (#588) -- unset or unknown-for-this-language
    # silently falls back to that language's default rather than erroring
    # (tts_engine._resolve_voice_id), since a caller's exact voice choice not
    # landing is a much smaller problem than a synthesis request 422ing over
    # it. Ignored entirely for gTTS-only languages (no per-voice selection).
    voice: str | None = None

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
