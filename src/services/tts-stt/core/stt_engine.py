"""Speech-to-Text engine (SpeechRecognition) — extracted from routes/stt.py.

Owns the optional `speech_recognition` dependency and the blocking transcription
call so the domain/engine logic lives outside the HTTP handler (service-structure
standard: thin routes + core/). routes/stt.py keeps the HTTP concerns (upload,
metrics, error mapping).
"""

import logging
import os
import tempfile

logger = logging.getLogger("minder.tts-stt")

# STT library (optional — gated by STT_AVAILABLE)
try:
    import speech_recognition as sr

    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False
    logging.warning("SpeechRecognition not installed")


def transcribe(audio_bytes: bytes, language: str) -> tuple[str, float]:
    """Transcribe WAV audio bytes to (text, confidence).

    Blocking (file I/O + Google recognition network call) — call via
    asyncio.to_thread so a single transcription can't stall the event loop.
    Owns the temp-file lifecycle end to end.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        temp_file.write(audio_bytes)
        temp_path = temp_file.name

    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(temp_path) as source:
            audio_data = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio_data, language=language)
            return text, 0.9
        except sr.UnknownValueError:
            return "", 0.0
        except sr.RequestError as e:
            logger.warning(f"Speech recognition API error: {e}")
            return f"[API Error: {str(e)}]", 0.0
    finally:
        os.unlink(temp_path)
