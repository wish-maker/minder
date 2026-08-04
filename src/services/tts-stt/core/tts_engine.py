"""Text-to-Speech engines — Piper (offline, default) with gTTS fallback (#18).

Piper (rhasspy/piper) runs fully offline on CPU (Raspberry-Pi-friendly, permissive
voices) and is the default; gTTS (online, Google) is the fallback for languages
without a bundled Piper voice, or if piper-tts isn't installed. Engine logic lives
here (service-structure standard: thin routes + core/); routes/tts.py keeps the HTTP
concerns.

`synthesize()` returns ``(audio_bytes, media_type, extension)`` so the route can set
the right Content-Type / filename regardless of engine — Piper emits WAV, gTTS MP3.
The design is intentionally pluggable: a heavier engine (e.g. an XTTS-class model)
could be added as another branch for a GPU deployment without touching the Pi path.
"""

import io
import logging
import os
import tempfile
import wave
from typing import Any, Dict, Optional, Tuple

from config import PIPER_VOICES, settings

logger = logging.getLogger("minder.tts-stt")

# gTTS (online fallback)
try:
    from gtts import gTTS

    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logger.warning("gTTS not installed")

# Piper (offline, default)
try:
    from piper import PiperVoice

    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    logger.warning("piper-tts not installed")

# TTS is usable if EITHER engine is present.
TTS_AVAILABLE = GTTS_AVAILABLE or PIPER_AVAILABLE

# Loaded PiperVoice instances, cached per language (loading the ONNX is expensive).
_piper_cache: Dict[str, Any] = {}


def _piper_voice_path(language: str) -> Optional[str]:
    """Absolute path to the bundled Piper .onnx for `language`, or None if absent."""
    name = PIPER_VOICES.get(language)
    if not name:
        return None
    path = os.path.join(settings.TTS_VOICES_DIR, f"{name}.onnx")
    return path if os.path.isfile(path) else None


def _load_piper(language: str) -> Optional[Any]:
    if language not in _piper_cache:
        path = _piper_voice_path(language)
        if not path:
            return None
        _piper_cache[language] = PiperVoice.load(path)
    return _piper_cache[language]


def _synthesize_piper(text: str, language: str, slow: bool) -> Optional[bytes]:
    """WAV bytes via Piper, or None when no bundled voice exists for `language`."""
    voice = _load_piper(language)
    if voice is None:
        return None
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        try:
            from piper import SynthesisConfig

            # slow → stretch the audio (higher length_scale = slower speech).
            cfg = SynthesisConfig(length_scale=1.5) if slow else None
            voice.synthesize_wav(text, wf, syn_config=cfg)
        except (ImportError, TypeError):
            voice.synthesize_wav(text, wf)
    return buf.getvalue()


def _synthesize_gtts(text: str, language: str, slow: bool) -> bytes:
    """MP3 bytes via gTTS (online). Owns the temp-file lifecycle end to end."""
    tts = gTTS(text=text, lang=language, slow=slow)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
        tts.save(temp_file.name)
        temp_path = temp_file.name
    try:
        with open(temp_path, "rb") as audio_file:
            return audio_file.read()
    finally:
        os.unlink(temp_path)


def synthesize(text: str, language: str, slow: bool) -> Tuple[bytes, str, str]:
    """Synthesize `text` → ``(audio_bytes, media_type, extension)``.

    Prefers Piper (offline) when TTS_ENGINE allows it and a voice is bundled for
    `language`; otherwise falls back to gTTS (online). Blocking (synthesis + I/O) —
    call via ``asyncio.to_thread`` so concurrent requests aren't stalled.
    """
    if settings.TTS_ENGINE != "gtts" and PIPER_AVAILABLE:
        data = _synthesize_piper(text, language, slow)
        if data is not None:
            return data, "audio/wav", "wav"
    if GTTS_AVAILABLE:
        return _synthesize_gtts(text, language, slow), "audio/mpeg", "mp3"
    raise RuntimeError("No TTS engine available (neither Piper nor gTTS)")
