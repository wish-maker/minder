"""Unit tests for the STT transcription outcome handling (tts-stt/core/stt_engine.py, #272).

`transcribe()` wraps the optional `speech_recognition` dependency's three
outcomes (recognized text, ambiguous silence/noise, backend API error) into a
uniform (text, confidence) contract for routes/stt.py -- these lock that
mapping, since #272 flagged this module as having zero regression coverage.

Loaded by path: stt_engine.py imports `speech_recognition as sr` (optional,
gated by STT_AVAILABLE) -- stub it in sys.modules before loading so the test
doesn't need the real package installed, then load the module fresh by path
to avoid colliding with any other service's same-named module already cached
in sys.modules within the shared conftest.py test process (see
test_rag_ollama_failover_error.py for the established precedent).
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "tts-stt"


class _FakeUnknownValueError(Exception):
    pass


class _FakeRequestError(Exception):
    pass


def _install_fake_sr():
    """A minimal stand-in for the `speech_recognition` package's public surface
    stt_engine.py touches: Recognizer, AudioFile, UnknownValueError, RequestError."""
    fake_sr = types.ModuleType("speech_recognition")
    fake_sr.UnknownValueError = _FakeUnknownValueError
    fake_sr.RequestError = _FakeRequestError

    class _FakeAudioFile:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return MagicMock()

        def __exit__(self, *exc):
            return False

    fake_sr.AudioFile = _FakeAudioFile
    fake_sr.Recognizer = MagicMock  # replaced per-test via monkeypatch
    sys.modules["speech_recognition"] = fake_sr
    return fake_sr


_fake_sr = _install_fake_sr()

_spec = importlib.util.spec_from_file_location(
    "tts_stt_stt_engine", _SERVICE_DIR / "core" / "stt_engine.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["tts_stt_stt_engine"] = _mod
_spec.loader.exec_module(_mod)


def _recognizer_returning(*, text=None, raises=None):
    """Build a fake `sr.Recognizer()` instance for one transcribe() call."""
    recognizer = MagicMock()
    recognizer.record.return_value = "recorded-audio"
    if raises is not None:
        recognizer.recognize_google.side_effect = raises
    else:
        recognizer.recognize_google.return_value = text
    return recognizer


@pytest.fixture
def stub_to_wav(monkeypatch, tmp_path):
    """transcribe() now normalizes input audio via `_to_wav()` (real ffmpeg
    subprocess, #583's STT fix) before ever touching `sr.AudioFile` -- stub it
    for tests exercising transcribe()'s OWN logic (recognizer outcomes,
    cleanup) so they don't need a real ffmpeg binary or real audio bytes.
    `_to_wav`'s own conversion-failure behavior is tested directly, below."""
    fake_wav = tmp_path / "fake.wav"
    fake_wav.write_bytes(b"")
    monkeypatch.setattr(_mod, "_to_wav", lambda audio_bytes: str(fake_wav))


def test_transcribe_success_returns_text_and_confidence(monkeypatch, stub_to_wav):
    monkeypatch.setattr(
        _mod.sr, "Recognizer", lambda: _recognizer_returning(text="merhaba")
    )
    text, confidence = _mod.transcribe(b"fake-wav-bytes", "tr-TR")
    assert text == "merhaba"
    assert confidence == 0.9


def test_transcribe_unknown_value_returns_empty_zero_confidence(
    monkeypatch, stub_to_wav
):
    monkeypatch.setattr(
        _mod.sr,
        "Recognizer",
        lambda: _recognizer_returning(raises=_FakeUnknownValueError()),
    )
    text, confidence = _mod.transcribe(b"silence", "tr-TR")
    assert text == ""
    assert confidence == 0.0


def test_transcribe_request_error_surfaces_api_error_message(monkeypatch, stub_to_wav):
    monkeypatch.setattr(
        _mod.sr,
        "Recognizer",
        lambda: _recognizer_returning(raises=_FakeRequestError("quota exceeded")),
    )
    text, confidence = _mod.transcribe(b"fake-wav-bytes", "tr-TR")
    assert text == "[API Error: quota exceeded]"
    assert confidence == 0.0


def test_transcribe_bad_audio_raises_valueerror(monkeypatch, stub_to_wav):
    # #536: an empty / non-WAV / truncated upload fails to open as audio; that's
    # a client error → transcribe raises a ValueError the route maps to 400,
    # NOT a bare exception the route would 500 on.
    class _BadAudioFile:
        def __init__(self, path):
            pass

        def __enter__(self):
            raise RuntimeError("file does not start with RIFF id")

        def __exit__(self, *exc):
            return False

    unlinked = []
    monkeypatch.setattr(_mod.sr, "AudioFile", _BadAudioFile)
    monkeypatch.setattr(_mod.os, "unlink", lambda p: unlinked.append(p))

    with pytest.raises(ValueError, match="could not decode audio"):
        _mod.transcribe(b"not-audio", "tr-TR")
    assert len(unlinked) == 1  # temp file still cleaned up on the error path


def test_transcribe_cleans_up_temp_file(monkeypatch, stub_to_wav):
    """The normalized WAV file is unlinked even on success -- assert the
    module's own os.unlink is actually invoked (no leaked temp files)."""
    calls = []
    monkeypatch.setattr(_mod.os, "unlink", lambda path: calls.append(path))
    monkeypatch.setattr(_mod.sr, "Recognizer", lambda: _recognizer_returning(text="ok"))

    _mod.transcribe(b"fake-wav-bytes", "tr-TR")

    assert len(calls) == 1


# ── _to_wav (#583: ffmpeg normalization, added so mic recordings --
# always WebM/Opus from the browser's MediaRecorder, never WAV -- actually
# decode instead of always 400ing) ──────────────────────────────────────────


def test_to_wav_converts_via_ffmpeg_and_cleans_up_input(monkeypatch, tmp_path):
    written = {}

    class _FakeInputFile:
        name = str(tmp_path / "input-tmp")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def write(self, data):
            written["data"] = data

    run_calls = []
    unlinked = []
    monkeypatch.setattr(
        _mod.tempfile, "NamedTemporaryFile", lambda delete: _FakeInputFile()
    )
    monkeypatch.setattr(
        _mod.subprocess,
        "run",
        lambda cmd, **kw: run_calls.append(cmd),
    )
    monkeypatch.setattr(_mod.os, "unlink", lambda p: unlinked.append(p))

    result = _mod._to_wav(b"webm-bytes")

    assert written["data"] == b"webm-bytes"
    assert result == f"{_FakeInputFile.name}.wav"
    assert run_calls[0][0] == "ffmpeg"
    assert "-i" in run_calls[0]
    assert unlinked == [_FakeInputFile.name]  # input cleaned up, NOT the output


def test_to_wav_raises_valueerror_on_ffmpeg_failure(monkeypatch, tmp_path):
    import subprocess

    class _FakeInputFile:
        name = str(tmp_path / "input-tmp")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def write(self, data):
            pass

    def _raise(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd)

    unlinked = []
    monkeypatch.setattr(
        _mod.tempfile, "NamedTemporaryFile", lambda delete: _FakeInputFile()
    )
    monkeypatch.setattr(_mod.subprocess, "run", _raise)
    monkeypatch.setattr(_mod.os, "unlink", lambda p: unlinked.append(p))

    with pytest.raises(ValueError, match="could not decode audio"):
        _mod._to_wav(b"not-really-audio")
    assert len(unlinked) == 1  # input temp file still cleaned up on failure
