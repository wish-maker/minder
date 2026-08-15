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
import threading
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
# `synthesize()` runs via asyncio.to_thread, so concurrent requests can call
# _load_piper from separate real OS threads -- a bare check-then-set on a plain
# dict lets two concurrent first-use requests for the same voice both miss the
# cache and both pay for a full PiperVoice.load(), wasting CPU/RAM on a Pi-class
# host. threading.Lock (not asyncio.Lock, which isn't meaningful across threads)
# guards the check-and-populate below.
_piper_cache: Dict[str, Any] = {}
_piper_cache_lock = threading.Lock()


def _resolve_voice_id(language: str, voice: Optional[str]) -> Optional[str]:
    """The voice_id to actually use: `voice` if it's a real option for
    `language`, else that language's "default" entry. An unknown/unsupported
    voice_id is a silent fallback, not an error -- a caller's voice choice
    being ignored is a much smaller problem than a synthesis request 422ing
    over a cosmetic mismatch."""
    voices = PIPER_VOICES.get(language)
    if not voices:
        return None
    if voice and voice in voices:
        return voice
    return "default" if "default" in voices else next(iter(voices), None)


def _piper_voice_path(language: str, voice: Optional[str]) -> Optional[str]:
    """Absolute path to the bundled Piper .onnx for `language`/`voice`, or None
    if no such voice is configured or its .onnx wasn't actually downloaded."""
    voices = PIPER_VOICES.get(language)
    if not voices:
        return None
    voice_id = _resolve_voice_id(language, voice)
    if voice_id is None:
        return None
    name = voices[voice_id]["model"]
    path = os.path.join(settings.TTS_VOICES_DIR, f"{name}.onnx")
    return path if os.path.isfile(path) else None


def _load_piper(language: str, voice: Optional[str]) -> Optional[Any]:
    cache_key = f"{language}:{_resolve_voice_id(language, voice)}"
    if cache_key in _piper_cache:
        return _piper_cache[cache_key]
    with _piper_cache_lock:
        # Re-check inside the lock: another thread may have already finished
        # loading this exact voice while we were waiting to acquire it.
        if cache_key not in _piper_cache:
            path = _piper_voice_path(language, voice)
            if not path:
                return None
            _piper_cache[cache_key] = PiperVoice.load(path)
        return _piper_cache[cache_key]


def list_voices(language: str) -> list:
    """Voice choices actually available for `language` right now -- only ones
    whose .onnx is really present on disk, so the UI never offers a voice this
    deployment can't actually synthesize. Empty for any gTTS-only language
    (gTTS has no per-voice selection at all)."""
    voices = PIPER_VOICES.get(language, {})
    return [
        {"id": voice_id, "label": entry["label"]}
        for voice_id, entry in voices.items()
        if os.path.isfile(
            os.path.join(settings.TTS_VOICES_DIR, f"{entry['model']}.onnx")
        )
    ]


def _synthesize_piper(
    text: str, language: str, slow: bool, voice: Optional[str]
) -> Optional[bytes]:
    """WAV bytes via Piper, or None when no bundled voice exists for `language`."""
    voice_obj = _load_piper(language, voice)
    if voice_obj is None:
        return None
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        try:
            from piper import SynthesisConfig

            # slow → stretch the audio (higher length_scale = slower speech).
            cfg = SynthesisConfig(length_scale=1.5) if slow else None
            voice_obj.synthesize_wav(text, wf, syn_config=cfg)
        except (ImportError, TypeError):
            voice_obj.synthesize_wav(text, wf)
    return buf.getvalue()


def _synthesize_gtts(text: str, language: str, slow: bool) -> bytes:
    """MP3 bytes via gTTS (online). Owns the temp-file lifecycle end to end.

    The temp file is created (delete=False) before tts.save() -- a network
    call to Google Translate that can raise (DNS failure, rate-limiting, any
    outage) -- so the whole lifecycle from creation to unlink must be one
    try/finally. It used to only wrap the read, leaving every failed gTTS
    call (exactly the failure mode most likely to recur repeatedly) leak one
    file into /tmp with no cleanup.
    """
    tts = gTTS(text=text, lang=language, slow=slow)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
        temp_path = temp_file.name
    try:
        tts.save(temp_path)
        with open(temp_path, "rb") as audio_file:
            return audio_file.read()
    finally:
        os.unlink(temp_path)


def synthesize(
    text: str, language: str, slow: bool, voice: Optional[str] = None
) -> Tuple[bytes, str, str]:
    """Synthesize `text` → ``(audio_bytes, media_type, extension)``.

    Prefers Piper (offline) when TTS_ENGINE allows it and a voice is bundled for
    `language`; otherwise falls back to gTTS (online, no voice selection). Blocking
    (synthesis + I/O) — call via ``asyncio.to_thread`` so concurrent requests aren't
    stalled. `voice` picks among PIPER_VOICES[language]'s entries (#588); an
    unset/unknown value silently falls back to that language's "default" voice
    rather than erroring.
    """
    if settings.TTS_ENGINE != "gtts" and PIPER_AVAILABLE:
        data = _synthesize_piper(text, language, slow, voice)
        if data is not None:
            return data, "audio/wav", "wav"
    if GTTS_AVAILABLE:
        return _synthesize_gtts(text, language, slow), "audio/mpeg", "mp3"
    raise RuntimeError("No TTS engine available (neither Piper nor gTTS)")
