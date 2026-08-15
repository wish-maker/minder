"""Unit tests for tts-stt's TTSRequest edge validation (#534).

Empty `text` must be a 422 at the request boundary, not a 500 from failing deep
in the Piper/gTTS engine with nothing to synthesize. Loaded by path (the models
module imports `config`, which the service puts on sys.path at runtime).
"""

import importlib
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "tts-stt"


def _load_models():
    saved_path = list(sys.path)
    saved = {k: sys.modules[k] for k in ("config", "models") if k in sys.modules}
    for k in ("config", "models"):
        sys.modules.pop(k, None)
    sys.path.insert(0, str(_SERVICE_DIR))
    try:
        return importlib.import_module("models")
    finally:
        sys.path[:] = saved_path
        for k in ("config", "models"):
            sys.modules.pop(k, None)
        sys.modules.update(saved)


def test_empty_text_rejected():
    models = _load_models()
    with pytest.raises(ValidationError):
        models.TTSRequest(text="")


def test_whitespace_only_text_rejected():
    """Found in a background audit: min_length=1 rejects "" but a whitespace-
    only string ("   ", "\\n") still passed it, then reached gTTS with nothing
    real to speak -- gTTS raises its own "no text to send" error there, caught
    only by the route's generic `except Exception` and turned into a
    sanitized 500 instead of the clean 422 #534 already established for a
    plain empty string."""
    models = _load_models()
    with pytest.raises(ValidationError):
        models.TTSRequest(text="   ")
    with pytest.raises(ValidationError):
        models.TTSRequest(text="\n\t")


def test_nonempty_text_accepted_with_default_language():
    models = _load_models()
    req = models.TTSRequest(text="Merhaba")
    assert req.text == "Merhaba"


def test_unsupported_language_still_rejected():
    models = _load_models()
    with pytest.raises(ValidationError):
        models.TTSRequest(text="hi", language="zz")


def test_text_over_max_length_rejected():
    """Neither Piper nor gTTS has a size ceiling of its own -- without this,
    an unbounded `text` field is synthesized in full regardless of size,
    consuming a to_thread worker and unbounded memory for as long as that
    takes."""
    models = _load_models()
    with pytest.raises(ValidationError):
        models.TTSRequest(text="x" * (models.settings.TTS_MAX_TEXT_LENGTH + 1))


def test_text_at_max_length_accepted():
    models = _load_models()
    req = models.TTSRequest(text="x" * models.settings.TTS_MAX_TEXT_LENGTH)
    assert len(req.text) == models.settings.TTS_MAX_TEXT_LENGTH
