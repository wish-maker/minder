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


def test_transcribe_success_returns_text_and_confidence(monkeypatch):
    monkeypatch.setattr(
        _mod.sr, "Recognizer", lambda: _recognizer_returning(text="merhaba")
    )
    text, confidence = _mod.transcribe(b"fake-wav-bytes", "tr-TR")
    assert text == "merhaba"
    assert confidence == 0.9


def test_transcribe_unknown_value_returns_empty_zero_confidence(monkeypatch):
    monkeypatch.setattr(
        _mod.sr,
        "Recognizer",
        lambda: _recognizer_returning(raises=_FakeUnknownValueError()),
    )
    text, confidence = _mod.transcribe(b"silence", "tr-TR")
    assert text == ""
    assert confidence == 0.0


def test_transcribe_request_error_surfaces_api_error_message(monkeypatch):
    monkeypatch.setattr(
        _mod.sr,
        "Recognizer",
        lambda: _recognizer_returning(raises=_FakeRequestError("quota exceeded")),
    )
    text, confidence = _mod.transcribe(b"fake-wav-bytes", "tr-TR")
    assert text == "[API Error: quota exceeded]"
    assert confidence == 0.0


def test_transcribe_cleans_up_temp_file(monkeypatch, tmp_path):
    """The temp WAV file is written then unlinked even on success -- assert the
    module's own os.unlink is actually invoked (no leaked temp files)."""
    calls = []
    monkeypatch.setattr(_mod.os, "unlink", lambda path: calls.append(path))
    monkeypatch.setattr(_mod.sr, "Recognizer", lambda: _recognizer_returning(text="ok"))

    _mod.transcribe(b"fake-wav-bytes", "tr-TR")

    assert len(calls) == 1
