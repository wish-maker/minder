"""Configuration constants for the TTS/STT service."""

import os

DEFAULT_TTS_LANG = "tr"
DEFAULT_STT_LANG = "tr-TR"

# TTS engine (#18). Piper (rhasspy/piper) runs fully OFFLINE on CPU — Pi-friendly,
# permissive voices — and is the default; gTTS (online, Google) is the fallback for
# languages without a bundled Piper voice or if Piper isn't installed.
TTS_ENGINE = os.getenv("TTS_ENGINE", "piper")  # "piper" | "gtts"
TTS_VOICES_DIR = os.getenv("TTS_VOICES_DIR", "/app/voices")
# Bundled Piper voices per language (downloaded at image build → offline). Languages
# absent here fall back to gTTS. Runtime-overridable via env for other voices.
PIPER_VOICES = {
    "en": os.getenv("TTS_PIPER_VOICE_EN", "en_US-lessac-low"),
    "tr": os.getenv("TTS_PIPER_VOICE_TR", "tr_TR-dfki-medium"),
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
