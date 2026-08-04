"""Settings for the TTS/STT service."""

import sys

# MinderBaseSettings + shared packages live under /app/src (#267). tts-stt holds
# no secrets of its own (no DB/Redis/JWT usage) but adopts the shared base for
# platform-wide consistency; DB_PASSWORD/REDIS_PASSWORD/JWT_SECRET are required
# by the base and simply go unused here.
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.config import MinderBaseSettings  # noqa: E402


class Settings(MinderBaseSettings):
    """TTS/STT Settings"""

    APP_VERSION: str = "1.0.0"
    PORT: int = 8006

    DEFAULT_TTS_LANG: str = "tr"
    DEFAULT_STT_LANG: str = "tr-TR"

    # TTS engine (#18). Piper (rhasspy/piper) runs fully OFFLINE on CPU — Pi-friendly,
    # permissive voices — and is the default; gTTS (online, Google) is the fallback
    # for languages without a bundled Piper voice or if Piper isn't installed.
    TTS_ENGINE: str = "piper"  # "piper" | "gtts"
    TTS_VOICES_DIR: str = "/app/voices"
    # Bundled Piper voices per language (downloaded at image build → offline).
    # Languages absent here fall back to gTTS. Runtime-overridable via env for
    # other voices.
    TTS_PIPER_VOICE_EN: str = "en_US-lessac-low"
    TTS_PIPER_VOICE_TR: str = "tr_TR-dfki-medium"


settings = Settings()

PIPER_VOICES = {
    "en": settings.TTS_PIPER_VOICE_EN,
    "tr": settings.TTS_PIPER_VOICE_TR,
}

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
