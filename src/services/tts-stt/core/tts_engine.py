"""Text-to-Speech engine (gTTS) — extracted from routes/tts.py.

Owns the optional `gtts` dependency and the blocking synthesis call so the
domain/engine logic lives outside the HTTP handler (service-structure standard:
thin routes + core/). routes/tts.py keeps the HTTP concerns (validation, metrics,
Response construction).
"""

import logging
import os
import tempfile

logger = logging.getLogger("minder.tts-stt")

# TTS library (optional — gated by TTS_AVAILABLE)
try:
    from gtts import gTTS

    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    logging.warning("gTTS not installed")


def synthesize(text: str, language: str, slow: bool) -> bytes:
    """Synthesize text to MP3 bytes.

    Blocking (gTTS synthesis + file I/O) — call via asyncio.to_thread so concurrent
    requests aren't stalled. Owns the temp-file lifecycle end to end.
    """
    tts = gTTS(text=text, lang=language, slow=slow)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
        tts.save(temp_file.name)
        temp_path = temp_file.name
    try:
        with open(temp_path, "rb") as audio_file:
            return audio_file.read()
    finally:
        os.unlink(temp_path)
