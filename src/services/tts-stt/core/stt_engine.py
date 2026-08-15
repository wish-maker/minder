"""Speech-to-Text engine (SpeechRecognition) — extracted from routes/stt.py.

Owns the optional `speech_recognition` dependency and the blocking transcription
call so the domain/engine logic lives outside the HTTP handler (service-structure
standard: thin routes + core/). routes/stt.py keeps the HTTP concerns (upload,
metrics, error mapping).
"""

import logging
import os
import subprocess
import tempfile

logger = logging.getLogger("minder.tts-stt")

# STT library (optional — gated by STT_AVAILABLE)
try:
    import speech_recognition as sr

    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False
    logging.warning("SpeechRecognition not installed")

_FFMPEG_TIMEOUT_S = 30


def _to_wav(audio_bytes: bytes) -> str:
    """Normalize arbitrary input audio to a 16kHz mono WAV file via `ffmpeg`
    (already bundled in the Docker image, previously unused for this).

    `sr.AudioFile` only natively parses WAV/AIFF/FLAC containers — it cannot
    read the browser's own recording format at all. The Voice page's "Record"
    button uses `MediaRecorder`, which every browser emits as WebM/Opus (there
    is no browser API to record raw WAV directly); every mic recording was
    therefore guaranteed to fail here with "could not decode audio" (found
    live: recording always 400'd, only a manually-uploaded real .wav file
    ever worked). ffmpeg probes the actual container from its content, not
    the caller-supplied filename, so this also normalizes non-WAV uploads
    (mp3, ogg, ...) the same way. Returns the WAV path; caller owns cleanup.
    """
    with tempfile.NamedTemporaryFile(delete=False) as input_file:
        input_file.write(audio_bytes)
        input_path = input_file.name
    output_path = f"{input_path}.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-ar", "16000", "-ac", "1", output_path],
            capture_output=True,
            timeout=_FFMPEG_TIMEOUT_S,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        # ffmpeg writes its output incrementally, so a timeout or a failure after
        # it has already created the file leaves a real, partially-written
        # output_path on disk -- the caller never receives this path to clean up
        # since we raise here instead of returning it, so nothing else will ever
        # unlink it. Repeated bad/slow uploads would otherwise accumulate
        # unboundedly and exhaust disk.
        if os.path.exists(output_path):
            os.unlink(output_path)
        raise ValueError("could not decode audio; unsupported or corrupt format") from e
    finally:
        os.unlink(input_path)
    return output_path


def transcribe(audio_bytes: bytes, language: str) -> tuple[str, float]:
    """Transcribe audio bytes (any ffmpeg-decodable format) to (text, confidence).

    Blocking (subprocess + file I/O + Google recognition network call) — call via
    asyncio.to_thread so a single transcription can't stall the event loop.
    Owns the temp-file lifecycle end to end.
    """
    wav_path = _to_wav(audio_bytes)
    recognizer = sr.Recognizer()
    try:
        try:
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
        except Exception as e:
            # An empty/zero-duration conversion result fails to decode here.
            # Raise a distinct ValueError so the route can return a 400 (client
            # sent bad audio) instead of a 500 (#536) — real recognizer-service
            # failures surface separately as sr.RequestError below.
            raise ValueError("could not decode audio; expected a valid WAV file") from e
        try:
            text = recognizer.recognize_google(audio_data, language=language)
            return text, 0.9
        except sr.UnknownValueError:
            return "", 0.0
        except sr.RequestError as e:
            # The recognition backend itself is unreachable/erroring -- this used to
            # come back as a fake 200 success with the raw exception string embedded
            # as if it were the transcript (e.g. a user seeing "[API Error:
            # HTTPSConnectionPool(...): Read timed out]" quoted as their own speech).
            # Re-raise so routes/stt.py's existing `except Exception ->
            # backend_http_error` path handles it the same way every other backend
            # outage in this codebase is handled: a sanitized 503, not a misleading
            # "successful" transcription.
            logger.warning(f"Speech recognition API error: {e}")
            raise
    finally:
        os.unlink(wav_path)
